
import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Any

import yt_dlp

#https://www.youtube.com/watch?v=rYe9wiv2M0I
#https://www.youtube.com/watch?v=UASLAWHqKJA
#https://www.youtube.com/watch?v=n9D3b0K9pko

DEFAULT_URL = "https://www.youtube.com/watch?v=n9D3b0K9pko"


def safe_print(message):
    """Print text safely in the terminal."""
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(str(message).encode(
            encoding, errors="replace"
        ).decode(encoding, errors="replace"))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract YouTube video metadata, comments, and replies."
    )

    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_URL,
        help="YouTube video URL"
    )

    parser.add_argument(
        "--output-dir",
        default="youtube_results",
        help="Directory for the output files"
    )

    parser.add_argument(
        "--max-comments",
        type=int,
        default=500,
        help="Maximum comments to request (default: 500)"
    )

    parser.add_argument(
        "--sort",
        choices=["top", "new"],
        default="top",
        help="Comment sorting order"
    )

    parser.add_argument(
        "--cookies",
        default=None,
        help="Optional path to a Netscape-format cookies.txt file"
    )

    return parser.parse_args()


def extract_video(url, max_comments=500, sort="top", cookies=None):
    """
    Extract video information and comments using yt-dlp.
    Does not download the video itself.
    """

    if max_comments < 1:
        raise ValueError("--max-comments must be at least 1.")

    options = {
        "skip_download": True,
        "getcomments": True,
        "quiet": False,
        "no_warnings": False,
        "noplaylist": True,
        "ignoreerrors": False,

        "extractor_args": {
            "youtube": {
                "comment_sort": [sort],
                "max_comments": [
                    f"{max_comments},all,all,all,all"
                ],
            }
        },
    }

    if cookies:
        options["cookiefile"] = cookies

    safe_print("Extracting video information and comments...")

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError("No video information was returned.")

    return info


def normalize_comment(comment):
    """Keep useful fields from a comment or reply."""

    return {
        "id": comment.get("id"),
        "author": comment.get("author"),
        "author_id": comment.get("author_id"),
        "author_url": comment.get("author_url"),
        "text": comment.get("text") or comment.get("html") or "",
        "likes": comment.get("like_count"),
        "timestamp": comment.get("timestamp"),
        "parent": comment.get("parent"),
        "is_pinned": comment.get("is_pinned"),
        "is_favorited": comment.get("is_favorited"),
    }


def organize_comments(raw_comments):
    """
    Organize flat comments into parent comments and nested replies.

    yt-dlp uses the 'parent' field to identify reply relationships.
    """

    by_id = {}
    ordered_comments = []

    for raw in raw_comments or []:
        comment = normalize_comment(raw)
        comment_id = comment.get("id")

        if not comment_id:
            continue

        comment["replies"] = []
        by_id[comment_id] = comment
        ordered_comments.append(comment)

    root_comments = []

    for comment in ordered_comments:
        parent_id = comment.get("parent")

        if not parent_id or parent_id == "root":
            root_comments.append(comment)
            continue

        parent = by_id.get(parent_id)

        if parent and parent is not comment:
            parent["replies"].append(comment)
        else:
            # Preserve replies whose parent was not retrieved.
            root_comments.append(comment)

    # Remove internal parent field from the exported records.
    for comment in ordered_comments:
        comment.pop("parent", None)

    return root_comments


def build_result(info):
    """Build a clean JSON-compatible result."""

    raw_comments = info.get("comments") or []
    comments = organize_comments(raw_comments)

    # YouTube's normal metadata tags.
    tags = info.get("tags") or []
    tags = list(dict.fromkeys(str(tag) for tag in tags if tag))

    # Extract hashtags separately.
    # Some yt-dlp versions may provide a hashtags field directly.
    # If not, collect hashtags from the title and description.
    hashtags = info.get("hashtags") or []

    if not hashtags:
        hashtag_source = "\n".join([
            str(info.get("title") or ""),
            str(info.get("description") or "")
        ])

        hashtags = re.findall(
            r"(?<!\w)#([\wÀ-ÿ]+)",
            hashtag_source,
            flags=re.UNICODE
        )

    # Add the # symbol and remove duplicates while preserving order.
    hashtags = [
        tag if tag.startswith("#") else f"#{tag}"
        for tag in hashtags
        if tag
    ]
    hashtags = list(dict.fromkeys(hashtags))

    total_replies = sum(
        len(comment["replies"])
        for comment in comments
    )

    timestamp = info.get("release_timestamp") or info.get("timestamp")

    published_at = None
    if timestamp:
        published_at = datetime.fromtimestamp(
            timestamp
        ).astimezone().isoformat()

    video = {
        "video_id": info.get("id"),
        "url": info.get("webpage_url"),
        "title": info.get("title"),

        "channel": info.get("channel"),
        "channel_id": info.get("channel_id"),
        "channel_url": info.get("channel_url"),
        "uploader": info.get("uploader"),

        "views": info.get("view_count"),
        "likes": info.get("like_count"),
        "comment_count": info.get("comment_count"),

        "description": info.get("description") or "",

        "tags": tags,
        "tag_count": len(tags),

        "hashtags": hashtags,
        "hashtag_count": len(hashtags),

        "duration_seconds": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "published_at": published_at,

        "thumbnail": info.get("thumbnail"),

        # Not available as public metadata for arbitrary videos.
        "share_count": None,
        "share_count_note": (
            "Public share count is not provided by standard "
            "YouTube video metadata."
        ),

        "comments_retrieved": len(comments),
        "replies_retrieved": total_replies,
        "raw_comment_records_retrieved": len(raw_comments),
    }

    return {
        "video": video,
        "comments": comments,
    }



def safe_filename(title, fallback="youtube_video"):
    """
    Convert the YouTube title into a Windows-safe filename.
    """
    title = str(title or "").strip()

    # Windows does not allow these characters in filenames.
    title = re.sub(r'[<>:"/\\|?*]', "_", title)

    # Remove trailing spaces and periods.
    title = title.rstrip(" .")

    # Avoid an empty filename.
    if not title:
        title = fallback

    # Keep the filename reasonably manageable.
    return title[:180]


def save_json(data, filepath):
    """Save structured metadata, comments, and replies."""

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


def save_text(data, filepath):
    """Save a readable report."""

    video = data["video"]

    with open(filepath, "w", encoding="utf-8") as file:
        file.write("=" * 80 + "\n")
        file.write("YOUTUBE VIDEO REPORT\n")
        file.write("=" * 80 + "\n\n")

        fields = [
            ("Title", "title"),
            ("Video ID", "video_id"),
            ("URL", "url"),
            ("Channel", "channel"),
            ("Channel ID", "channel_id"),
            ("Uploader", "uploader"),
            ("Views", "views"),
            ("Likes", "likes"),
            ("Total comments reported by YouTube", "comment_count"),
            ("Tags count", "tag_count"),
            ("Hashtags count", "hashtag_count"),
            ("Duration (seconds)", "duration_seconds"),
            ("Upload date", "upload_date"),
            ("Published at", "published_at"),
            ("Comments retrieved", "comments_retrieved"),
            ("Replies retrieved", "replies_retrieved"),
            ("Share count", "share_count"),
        ]

        for label, key in fields:
            file.write(f"{label}: {video.get(key)}\n")

        file.write("\n" + "=" * 80 + "\n")
        file.write("DESCRIPTION\n")
        file.write("=" * 80 + "\n")
        file.write(video.get("description") or "(No description)")
        file.write("\n\n")

        file.write("=" * 80 + "\n")
        file.write(f"TAGS ({video['tag_count']})\n")
        file.write("=" * 80 + "\n")

        if video["tags"]:
            for index, tag in enumerate(video["tags"], start=1):
                file.write(f"{index}. {tag}\n")
        else:
            file.write("No tags were returned.\n")

        file.write("\n" + "=" * 80 + "\n")
        file.write(f"HASHTAGS ({video['hashtag_count']})\n")
        file.write("=" * 80 + "\n")

        if video["hashtags"]:
            for index, hashtag in enumerate(video["hashtags"], start=1):
                file.write(f"{index}. {hashtag}\n")
        else:
            file.write("No hashtags were found.\n")

        file.write("\n" + "=" * 80 + "\n")
        file.write("COMMENTS AND REPLIES\n")
        file.write("=" * 80 + "\n\n")

        for index, comment in enumerate(data["comments"], start=1):
            file.write(f"COMMENT {index}\n")
            file.write("-" * 80 + "\n")
            file.write(f"Comment ID: {comment.get('id')}\n")
            file.write(f"Author: {comment.get('author')}\n")
            file.write(f"Likes: {comment.get('likes')}\n")
            file.write(f"Replies retrieved: {len(comment['replies'])}\n")
            file.write(f"Text:\n{comment.get('text', '')}\n\n")

            for reply_index, reply in enumerate(
                comment["replies"], start=1
            ):
                file.write(f"    REPLY {reply_index}\n")
                file.write(f"    Reply ID: {reply.get('id')}\n")
                file.write(f"    Author: {reply.get('author')}\n")
                file.write(f"    Likes: {reply.get('likes')}\n")
                file.write(f"    Text: {reply.get('text', '')}\n\n")

            file.write("\n")


def main():
    args = parse_args()

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    try:
        info = extract_video(
            url=args.url,
            max_comments=args.max_comments,
            sort=args.sort,
            cookies=args.cookies,
        )

        data = build_result(info)

        # Use the YouTube video title for the output filename.
        # Invalid Windows filename characters are replaced with "_".
        video_title = data["video"].get("title") or "youtube_video"
        filename = safe_filename(video_title)

        json_path = os.path.join(
            output_dir, f"{filename}.json"
        )
        text_path = os.path.join(
            output_dir, f"{filename}.txt"
        )

        save_json(data, json_path)
        save_text(data, text_path)

        video = data["video"]

        safe_print("\n" + "=" * 60)
        safe_print("EXTRACTION COMPLETE")
        safe_print("=" * 60)
        safe_print(f"Title: {video.get('title')}")
        safe_print(f"Views: {video.get('views')}")
        safe_print(f"Likes: {video.get('likes')}")
        safe_print(f"Tags: {video.get('tag_count')}")
        safe_print(f"Hashtags: {video.get('hashtag_count')}")
        safe_print(f"Comments reported: {video.get('comment_count')}")
        safe_print(f"Comments retrieved: {video.get('comments_retrieved')}")
        safe_print(f"Replies retrieved: {video.get('replies_retrieved')}")
        safe_print(f"\nJSON saved to: {json_path}")
        safe_print(f"Text saved to: {text_path}")

    except KeyboardInterrupt:
        safe_print("\nExtraction cancelled.")
        sys.exit(1)

    except Exception as error:
        safe_print(f"\nExtraction failed: {error}")
        safe_print(
            "Try updating yt-dlp with: "
            "python -m pip install --upgrade yt-dlp"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()