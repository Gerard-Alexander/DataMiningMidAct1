from pathlib import Path

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent

PROJECT_DIR = BASE_DIR.parent.parent
INPUT_FILE = BASE_DIR.parent / "combine datasets" / "combined_dataset.json"
CSV_OUTPUT = BASE_DIR / "preprocessed_documents.csv"
JSON_OUTPUT = BASE_DIR / "preprocessed_dataset.json"


# ============================================================
# ENGLISH STOPWORDS
# ============================================================

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by",
    "could", "did", "do", "does", "doing", "down", "during", "each",
    "few", "for", "from", "further", "had", "has", "have", "having",
    "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "just", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "will", "with", "you", "your",
    "yours", "yourself", "yourselves"
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def as_text(value: Any) -> str:
    """Safely convert a value to text."""
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    return str(value)


def first_value(data: dict, keys: list[str], default=""):
    """Return the first non-empty value from a dictionary."""
    for key in keys:
        if key in data:
            value = data[key]

            if value is not None and value != "":
                return value

    return default


def find_nested_dict(value: Any, possible_keys: list[str]):
    """
    Find the first dictionary stored under one of the supplied keys.
    """
    if not isinstance(value, dict):
        return None

    for key in possible_keys:
        child = value.get(key)

        if isinstance(child, dict):
            return child

    return None


# ============================================================
# TEXT PREPROCESSING
# ============================================================

def clean_text(text: str) -> str:
    """
    Clean a social-media comment/reply.

    Hashtags are retained as words.

    Example:
        #FruitLoveIsland
    becomes:
        fruitloveisland
    """

    text = as_text(text)

    # 1. Normalize Unicode.
    text = unicodedata.normalize("NFKC", text)

    # 2. Lowercase.
    text = text.lower()

    # 3. Remove URLs.
    text = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        text
    )

    # 4. Remove @mentions.
    text = re.sub(
        r"@\w+",
        " ",
        text
    )

    # 5. Keep hashtag words.
    text = re.sub(
        r"#([a-zA-Z0-9_]+)",
        r" \1 ",
        text
    )

    # 6. Remove HTML entities.
    text = re.sub(
        r"&[a-zA-Z0-9#]+;",
        " ",
        text
    )

    # 7. Remove punctuation and emoji/symbol noise.
    #    English letters, numbers, underscore and whitespace remain.
    text = re.sub(
        r"[^a-z0-9_\s]",
        " ",
        text
    )

    # 8. Collapse repeated whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    # 9. Tokenize.
    tokens = text.split()

    cleaned_tokens = []

    for token in tokens:

        # 10. Stopword removal.
        if token in STOPWORDS:
            continue

        # 11. Remove very short tokens.
        if len(token) < 3:
            continue

        # 12. Remove numbers only.
        if token.isdigit():
            continue

        cleaned_tokens.append(token)

    return " ".join(cleaned_tokens)


# ============================================================
# CONTENT METADATA
# ============================================================

def get_content_id(record: dict) -> str:
    """Find the ID of the video/post."""

    value = first_value(
        record,
        [
            "video_id",
            "videoId",
            "aweme_id",
            "awemeId",
            "item_id",
            "itemId",
            "post_id",
            "postId"
        ]
    )

    if value:
        return as_text(value)

    # Some YouTube records store metadata under "video".
    video = record.get("video")

    if isinstance(video, dict):
        value = first_value(
            video,
            [
                "video_id",
                "videoId",
                "id"
            ]
        )

        if value:
            return as_text(value)

    return ""


def get_title(record: dict) -> str:
    """Find the video/post title or description."""

    value = first_value(
        record,
        [
            "title",
            "video_title",
            "videoTitle"
        ]
    )

    if value:
        return as_text(value)

    video = record.get("video")

    if isinstance(video, dict):
        value = first_value(
            video,
            [
                "title",
                "video_title",
                "videoTitle"
            ]
        )

        if value:
            return as_text(value)

    return ""


# ============================================================
# COMMENT FIELD DETECTION
# ============================================================

# Exact names that are commonly used by scrapers.
COMMENT_TEXT_KEYS = {
    "text",
    "comment",
    "comment_text",
    "commentText",
    "reply",
    "reply_text",
    "replyText",
    "content",
    "message"
}

COMMENT_CONTAINER_KEYS = {
    "comments",
    "comment",
    "comment_list",
    "commentList",
    "replies",
    "reply",
    "reply_list",
    "replyList"
}


def is_comment_text_key(key: Any) -> bool:
    """
    Determine whether a key is probably a text field.

    We deliberately DO NOT treat every field called 'description'
    or 'desc' as a comment because video descriptions are metadata.
    """

    if not isinstance(key, str):
        return False

    key_lower = key.lower()

    exact_keys = {
        x.lower()
        for x in COMMENT_TEXT_KEYS
    }

    if key_lower in exact_keys:
        return True

    # Catch names such as comment_text or reply_text.
    if "comment" in key_lower and (
        "text" in key_lower
        or "content" in key_lower
        or key_lower == "comment"
    ):
        return True

    if "reply" in key_lower and (
        "text" in key_lower
        or "content" in key_lower
        or key_lower == "reply"
    ):
        return True

    return False


def is_comment_container_key(key: Any) -> bool:
    """Check whether a key probably contains comments or replies."""

    if not isinstance(key, str):
        return False

    return key.lower() in {
        x.lower()
        for x in COMMENT_CONTAINER_KEYS
    }


# ============================================================
# COMMENT/REPLY METADATA
# ============================================================

def get_object_id(data: dict) -> str:
    """Get a comment/reply ID."""

    value = first_value(
        data,
        [
            "comment_id",
            "commentId",
            "reply_id",
            "replyId",
            "cid",
            "id"
        ]
    )

    return as_text(value)


def get_author(data: dict) -> str:
    """Get the comment/reply author if available."""

    value = first_value(
        data,
        [
            "author",
            "username",
            "user_name",
            "nickname",
            "user"
        ]
    )

    # Sometimes user is an object.
    if isinstance(value, dict):
        value = first_value(
            value,
            [
                "username",
                "unique_id",
                "uniqueId",
                "nickname",
                "name"
            ]
        )

    return as_text(value)


def get_likes(data: dict):
    """Get comment/reply like count when available."""

    value = first_value(
        data,
        [
            "likes",
            "like_count",
            "likeCount",
            "digg_count",
            "diggCount"
        ],
        default=None
    )

    return value


def get_timestamp(data: dict):
    """Get the comment/reply timestamp when available."""

    return first_value(
        data,
        [
            "timestamp",
            "create_time",
            "createTime",
            "created_at",
            "createdAt",
            "date"
        ],
        default=""
    )


# ============================================================
# RECURSIVE EXTRACTION
# ============================================================

def extract_documents(
    value: Any,
    platform: str,
    source_file: str,
    content_id: str,
    title: str,
    content_type: str = "unknown",
    parent_id: str = "",
    parent_path: str = "root"
) -> list[dict]:

    documents = []

    # --------------------------------------------------------
    # Dictionary
    # --------------------------------------------------------

    if isinstance(value, dict):

        current_id = get_object_id(value)
        current_author = get_author(value)
        current_likes = get_likes(value)
        current_timestamp = get_timestamp(value)

        # Determine whether THIS dictionary is a comment/reply
        # based on its surrounding context.
        for key, field_value in value.items():

            # ------------------------------------------------
            # A. Find comment/reply text.
            # ------------------------------------------------

            if (
                is_comment_text_key(key)
                and isinstance(field_value, str)
            ):

                original_text = field_value.strip()

                if not original_text:
                    continue

                # If the field itself says reply, it is a reply.
                key_lower = key.lower()

                if "reply" in key_lower:
                    detected_type = "reply"

                elif content_type == "reply":
                    detected_type = "reply"

                else:
                    detected_type = "comment"

                cleaned = clean_text(original_text)

                # A document that contains no useful words after
                # preprocessing should not enter topic modeling.
                if not cleaned:
                    continue

                # If this object is a reply and it has its own ID,
                # keep the parent's ID separately.
                document_parent_id = parent_id

                documents.append({
                    "platform": platform,
                    "content_type": detected_type,
                    "content_id": content_id,
                    "video_title": title,
                    "comment_id": current_id,
                    "parent_id": document_parent_id,
                    "author": current_author,
                    "likes": current_likes,
                    "timestamp": current_timestamp,
                    "original_text": original_text,
                    "clean_text": cleaned,
                    "source_file": source_file,
                    "source_path": f"{parent_path}.{key}"
                })

            # ------------------------------------------------
            # B. Search nested comments/replies.
            # ------------------------------------------------

            if isinstance(field_value, (dict, list)):

                key_lower = key.lower()

                child_type = content_type

                if "reply" in key_lower:
                    child_type = "reply"

                elif "comment" in key_lower:
                    child_type = "comment"

                child_parent_id = parent_id

                # A reply nested under this comment gets the
                # current comment ID as its parent.
                if child_type == "reply" and current_id:
                    child_parent_id = current_id

                documents.extend(
                    extract_documents(
                        field_value,
                        platform=platform,
                        source_file=source_file,
                        content_id=content_id,
                        title=title,
                        content_type=child_type,
                        parent_id=child_parent_id,
                        parent_path=f"{parent_path}.{key}"
                    )
                )

    # --------------------------------------------------------
    # List
    # --------------------------------------------------------

    elif isinstance(value, list):

        for index, item in enumerate(value):

            documents.extend(
                extract_documents(
                    item,
                    platform=platform,
                    source_file=source_file,
                    content_id=content_id,
                    title=title,
                    content_type=content_type,
                    parent_id=parent_id,
                    parent_path=f"{parent_path}[{index}]"
                )
            )

    return documents


# ============================================================
# DUPLICATE HANDLING
# ============================================================

def remove_duplicates(documents: list[dict]) -> list[dict]:
    """
    Remove duplicated scraped records without deleting legitimate
    comments that happen to contain exactly the same text.

    Priority:
    1. If a real comment/reply ID exists, use it.
    2. Otherwise use source file + source path + text.
    """

    unique = []
    seen = set()

    for document in documents:

        comment_id = document["comment_id"]

        if comment_id:
            key = (
                document["platform"],
                document["content_id"],
                document["content_type"],
                comment_id
            )

        else:
            key = (
                document["platform"],
                document["source_file"],
                document["source_path"],
                document["original_text"].strip()
            )

        if key in seen:
            continue

        seen.add(key)
        unique.append(document)

    return unique


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 75)
    print("PREPROCESSING YOUTUBE + TIKTOK DATA")
    print("=" * 75)
    print()

    # --------------------------------------------------------
    # Check input.
    # --------------------------------------------------------

    if not INPUT_FILE.exists():

        print("ERROR:")
        print(f"Could not find: {INPUT_FILE}")
        print()
        print("Run this first:")
        print("python 01_combine_datasets.py")
        return

    # --------------------------------------------------------
    # Read combined dataset.
    # --------------------------------------------------------

    try:

        with INPUT_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            dataset = json.load(file)

    except json.JSONDecodeError as error:

        print("ERROR: combined_dataset.json is not valid JSON.")
        print(error)
        return

    records = dataset.get("records", [])

    if not isinstance(records, list):

        print(
            "ERROR: combined_dataset.json does not contain "
            "a 'records' list."
        )
        return

    print(
        f"Source records found: {len(records)}"
    )
    print()

    # --------------------------------------------------------
    # Extract comments/replies.
    # --------------------------------------------------------

    documents = []

    for number, record in enumerate(
        records,
        start=1
    ):

        if not isinstance(record, dict):
            continue

        platform = as_text(
            record.get(
                "_platform",
                "Unknown"
            )
        )

        source_file = as_text(
            record.get(
                "_source_file",
                "Unknown"
            )
        )

        content_id = get_content_id(record)
        title = get_title(record)

        found = extract_documents(
            record,
            platform=platform,
            source_file=source_file,
            content_id=content_id,
            title=title
        )

        documents.extend(found)

        print(
            f"[{number}/{len(records)}] "
            f"{platform:<8} | "
            f"{source_file} | "
            f"{len(found)} document(s)"
        )

    # --------------------------------------------------------
    # Remove actual duplicate scraped records.
    # --------------------------------------------------------

    before_duplicates = len(documents)

    documents = remove_duplicates(documents)

    duplicates_removed = (
        before_duplicates -
        len(documents)
    )

    # --------------------------------------------------------
    # Assign simple document IDs.
    # --------------------------------------------------------

    for index, document in enumerate(
        documents,
        start=1
    ):

        document["document_id"] = (
            f"DOC_{index:06d}"
        )

    # --------------------------------------------------------
    # Count results.
    # --------------------------------------------------------

    youtube_count = sum(
        1
        for document in documents
        if document["platform"].lower() == "youtube"
    )

    tiktok_count = sum(
        1
        for document in documents
        if document["platform"].lower() == "tiktok"
    )

    comment_count = sum(
        1
        for document in documents
        if document["content_type"] == "comment"
    )

    reply_count = sum(
        1
        for document in documents
        if document["content_type"] == "reply"
    )

    # --------------------------------------------------------
    # Save CSV.
    # --------------------------------------------------------

    columns = [
        "document_id",
        "platform",
        "content_type",
        "content_id",
        "video_title",
        "comment_id",
        "parent_id",
        "author",
        "likes",
        "timestamp",
        "original_text",
        "clean_text",
        "source_file",
        "source_path"
    ]

    with CSV_OUTPUT.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=columns
        )

        writer.writeheader()

        for document in documents:
            writer.writerow(document)

    # --------------------------------------------------------
    # Save JSON.
    # --------------------------------------------------------

    output = {
        "dataset_info": {
            "description": (
                "Preprocessed YouTube and TikTok "
                "comment/reply dataset for topic modeling."
            ),
            "source_file": str(INPUT_FILE.relative_to(PROJECT_DIR)),
            "documents_before_duplicate_removal":
                before_duplicates,
            "duplicates_removed":
                duplicates_removed,
            "final_documents":
                len(documents),
            "youtube_documents":
                youtube_count,
            "tiktok_documents":
                tiktok_count,
            "comments":
                comment_count,
            "replies":
                reply_count
        },
        "documents": documents
    }

    with JSON_OUTPUT.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # Final report.
    # --------------------------------------------------------

    print()
    print("=" * 75)
    print("PREPROCESSING COMPLETE")
    print("=" * 75)
    print()
    print(
        f"Documents before duplicate removal : "
        f"{before_duplicates}"
    )
    print(
        f"Duplicates removed                 : "
        f"{duplicates_removed}"
    )
    print(
        f"Final documents                    : "
        f"{len(documents)}"
    )
    print()
    print(
        f"YouTube documents                  : "
        f"{youtube_count}"
    )
    print(
        f"TikTok documents                   : "
        f"{tiktok_count}"
    )
    print(
        f"Comments                            : "
        f"{comment_count}"
    )
    print(
        f"Replies                             : "
        f"{reply_count}"
    )
    print()
    print(
        f"CSV output  : {CSV_OUTPUT}"
    )
    print(
        f"JSON output : {JSON_OUTPUT}"
    )
    print("=" * 75)


if __name__ == "__main__":
    main()
