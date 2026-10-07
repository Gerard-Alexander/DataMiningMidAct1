import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Any

import yt_dlp


DEFAULT_URLS = [
    "https://youtu.be/wlEYNQo-ckI",
    "https://youtu.be/ETMM6bexHJE",
    "https://youtu.be/pFkbPeqvDHw",
    "https://youtu.be/cqETXe4f0fw",
    "https://youtu.be/Ne-lmQe1610",
    "https://youtu.be/po5bDXlZjXA",
    "https://youtu.be/3iCHypQnoLk",
    "https://youtu.be/G3YpecW7LBk",
    "https://youtu.be/QKRGwSXiCbU",
    "https://youtu.be/rhAuYZzpfg8",
    "https://youtu.be/ePbdfVo8Ei0",
    "https://youtu.be/YeHAgJN4AuE",
    "https://youtu.be/c0Og3F7zV0o",
    "https://youtu.be/HI5hcU9WrQw",
    "https://youtu.be/SzQLcyWZkqU",
    "https://youtu.be/ighMwj5A-bM",
    "https://youtu.be/xghm-J6avZU",
]


def safe_print(message):
    """Print text safely in the terminal."""
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(
            str(message)
            .encode(encoding, errors="replace")
            .decode(encoding, errors="replace")
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract YouTube video metadata, comments, and replies into single output files."
    )

    parser.add_argument(
        "urls",
        nargs="*",
        default=[],
        help="One or more YouTube video URLs (defaults to preset list if omitted)",
    )

    parser.add_argument(
        "--output-dir",
        default="youtube_results",
        help="Directory for the output files",
    )

    parser.add_argument(
        "--max-comments",
        type=int,
        default=500,
        help="Maximum comments to request per video (default: 500)",
    )

    parser.add_argument(
        "--sort",
        choices=["top", "new"],
        default="top",
        help="Comment sorting order",
    )

    parser.add_argument(
        "--cookies",
        default=None,
        help="Optional path to a Netscape-format cookies.txt file",
    )

    return parser.parse_args()


def extract_video(url, max_comments=500, sort="top", cookies=None):
    """Extract video information and comments using yt-dlp."""

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
                "max_comments": [f"{max_comments},all,all,all,all"],
            }
        },
    }

    if cookies:
        options["cookiefile"] = cookies

    safe_print(f"Extracting video information and comments for: {url}")

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
    """Organize flat comments into parent comments and nested replies."""

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
            root_comments.append(comment)

    for comment in ordered_comments:
        comment.pop("parent", None)

    return root_comments



def safe_filename(title, fallback="youtube_video"):
    """
    Convert a YouTube title into a Windows-safe filename.
    """
    title = str(title or "").strip()

    # Replace characters that Windows does not allow in filenames.
    title = re.sub(r'[<>:"/\\|?*]', "_", title)

    # Remove trailing spaces and periods.
    title = title.rstrip(" .")

    # Avoid an empty filename.
    if not title:
        title = fallback

    # Prevent an excessively long filename.
    return title[:180]


def build_result(info):
    """Build a clean JSON-compatible result."""

    raw_comments = info.get("comments") or []
    comments = organize_comments(raw_comments)

    # Normal YouTube metadata tags.
    tags = info.get("tags") or []
    tags = list(dict.fromkeys(str(tag) for tag in tags if tag))

    # Extract hashtags separately.
    # If yt-dlp provides hashtags, use them.
    # Otherwise, find hashtags in the title and description.
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

    # Make sure every hashtag includes '#'
    hashtags = [
        tag if str(tag).startswith("#") else f"#{tag}"
        for tag in hashtags
        if tag
    ]

    # Remove duplicates while preserving order.
    hashtags = list(dict.fromkeys(hashtags))

    total_replies = sum(len(comment["replies"]) for comment in comments)

    timestamp = info.get("release_timestamp") or info.get("timestamp")

    published_at = None
    if timestamp:
        published_at = (
            datetime.fromtimestamp(timestamp).astimezone().isoformat()
        )

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
        "share_count": None,
        "share_count_note": (
            "Public share count is not provided by standard YouTube video"
            " metadata."
        ),
        "comments_retrieved": len(comments),
        "replies_retrieved": total_replies,
        "raw_comment_records_retrieved": len(raw_comments),
    }

    return {
        "video": video,
        "comments": comments,
    }


def save_combined_json(data_list, filepath):
    """Save array of all video metadata and comment threads into a single JSON file."""

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(data_list, file, ensure_ascii=False, indent=2)


def save_combined_text(data_list, filepath):
    """Save a single readable report containing all videos."""

    with open(filepath, "w", encoding="utf-8") as file:
        file.write("#" * 80 + "\n")
        file.write(f"COMBINED YOUTUBE REPORT ({len(data_list)} VIDEOS)\n")
        file.write("#" * 80 + "\n\n")

        for idx, data in enumerate(data_list, start=1):
            video = data["video"]

            file.write("=" * 80 + "\n")
            file.write(f"VIDEO {idx}: {video.get('title')}\n")
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
            ]

            for label, key in fields:
                file.write(f"{label}: {video.get(key)}\n")

            file.write("\n" + "-" * 80 + "\n")
            file.write("DESCRIPTION\n")
            file.write("-" * 80 + "\n")
            file.write(video.get("description") or "(No description)")
            file.write("\n\n")

            file.write("-" * 80 + "\n")
            file.write(f"TAGS ({video['tag_count']})\n")
            file.write("-" * 80 + "\n")

            if video["tags"]:
                for tag_idx, tag in enumerate(video["tags"], start=1):
                    file.write(f"{tag_idx}. {tag}\n")
            else:
                file.write("No tags were returned.\n")

            file.write("\n" + "-" * 80 + "\n")
            file.write(f"HASHTAGS ({video['hashtag_count']})\n")
            file.write("-" * 80 + "\n")

            if video["hashtags"]:
                for hashtag_idx, hashtag in enumerate(video["hashtags"], start=1):
                    file.write(f"{hashtag_idx}. {hashtag}\n")
            else:
                file.write("No hashtags were found.\n")

            file.write("\n" + "-" * 80 + "\n")
            file.write("COMMENTS AND REPLIES\n")
            file.write("-" * 80 + "\n\n")

            for comment_idx, comment in enumerate(data["comments"], start=1):
                file.write(f"COMMENT {comment_idx}\n")
                file.write(f"Comment ID: {comment.get('id')}\n")
                file.write(f"Author: {comment.get('author')}\n")
                file.write(f"Likes: {comment.get('likes')}\n")
                file.write(f"Replies retrieved: {len(comment['replies'])}\n")
                file.write(f"Text:\n{comment.get('text', '')}\n\n")

                for reply_idx, reply in enumerate(
                    comment["replies"], start=1
                ):
                    file.write(f"    REPLY {reply_idx}\n")
                    file.write(f"    Reply ID: {reply.get('id')}\n")
                    file.write(f"    Author: {reply.get('author')}\n")
                    file.write(f"    Likes: {reply.get('likes')}\n")
                    file.write(f"    Text: {reply.get('text', '')}\n\n")

            file.write("\n\n" + "#" * 80 + "\n\n")


def main():
    args = parse_args()

    target_urls = args.urls if args.urls else DEFAULT_URLS

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    all_results = []
    failed_urls = []

    for idx, url in enumerate(target_urls, start=1):
        safe_print(
            f"\n--- Extracting [{idx}/{len(target_urls)}]: {url} ---"
        )

        try:
            info = extract_video(
                url=url,
                max_comments=args.max_comments,
                sort=args.sort,
                cookies=args.cookies,
            )

            data = build_result(info)
            all_results.append(data)

            video = data["video"]
            safe_print(f"Success: {video.get('title')}")
            safe_print(
                f"Retrieved {video.get('comments_retrieved')} comments &"
                f" {video.get('replies_retrieved')} replies"
            )

        except KeyboardInterrupt:
            safe_print("\nProcess interrupted by user.")
            sys.exit(1)

        except Exception as error:
            failed_urls.append((url, str(error)))
            safe_print(f"Failed to process {url}: {error}")

    if all_results:
        safe_print("\nWriting individual video output files...")

        # Keep one combined JSON file containing all scraped videos.
        json_path = os.path.join(output_dir, "combined_series.json")
        save_combined_json(all_results, json_path)

        # Create one TXT report for each video.
        created_text_files = []

        for data in all_results:
            video = data["video"]

            title = video.get("title") or video.get("video_id") or "youtube_video"
            filename = safe_filename(title)

            text_path = os.path.join(output_dir, f"{filename}.txt")

            # If two videos have the same title, avoid overwriting the first one.
            if os.path.exists(text_path):
                video_id = video.get("video_id") or "video"
                text_path = os.path.join(
                    output_dir,
                    f"{filename}_{video_id}.txt"
                )

            save_combined_text([data], text_path)
            created_text_files.append(text_path)

            safe_print(f"Text saved to: {text_path}")

        safe_print("\n" + "=" * 60)
        safe_print(
            f"BATCH COMPLETE: {len(all_results)} extracted,"
            f" {len(failed_urls)} failed."
        )
        safe_print(f"Combined JSON saved to: {json_path}")
        safe_print(f"Individual text reports created: {len(created_text_files)}")
        safe_print("=" * 60)
    else:
        safe_print("\nNo video data was successfully retrieved.")


if __name__ == "__main__":
    main()