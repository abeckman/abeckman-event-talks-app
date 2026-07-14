"""
processor.py — Simulated OCR and metadata extraction for the document pipeline.

This module downloads a file from GCS and extracts structured metadata via
heuristic/simulated OCR. All extraction logic is clearly marked so it can be
swapped for real implementations (Tesseract, Google Document AI, etc.).
"""

from __future__ import annotations

import hashlib
import os
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from google.cloud import storage

# ---------------------------------------------------------------------------
# Language detection heuristic table
# ---------------------------------------------------------------------------
_LANG_HINTS: dict[str, str] = {
    "fr": "fr",
    "french": "fr",
    "de": "de",
    "german": "de",
    "es": "es",
    "spanish": "es",
    "pt": "pt",
    "portuguese": "pt",
    "it": "it",
    "italian": "it",
    "zh": "zh",
    "chinese": "zh",
    "ja": "ja",
    "japanese": "ja",
    "ar": "ar",
    "arabic": "ar",
}

# Bytes-per-page estimate used for page count heuristic (roughly 2 KB/page)
_BYTES_PER_PAGE: int = 2_048

# Simulated confidence score range
_CONFIDENCE_MIN: float = 0.70
_CONFIDENCE_MAX: float = 1.00


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class DocumentMetadata:
    """Structured metadata extracted from a single document."""

    filename: str
    gcs_path: str
    file_size_bytes: int
    upload_timestamp: Optional[str]  # ISO-8601 string or None
    word_count: int
    page_count: int
    detected_language: str
    tags: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    processed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def process_document(
    bucket_name: str,
    object_name: str,
    upload_timestamp: Optional[str] = None,
) -> DocumentMetadata:
    """
    Download *object_name* from *bucket_name* and extract metadata.

    Parameters
    ----------
    bucket_name:
        GCS bucket that contains the file.
    object_name:
        GCS object path (key) of the file.
    upload_timestamp:
        ISO-8601 timestamp supplied by the GCS event; may be ``None``.

    Returns
    -------
    DocumentMetadata
        Fully populated metadata record ready for BigQuery insertion.
    """
    gcs_path = f"gs://{bucket_name}/{object_name}"
    filename = os.path.basename(object_name)

    # 1. Download file content from GCS
    content, file_size_bytes = _download_from_gcs(bucket_name, object_name)

    # 2. Extract individual fields (simulated / heuristic)
    word_count = _estimate_word_count(content)
    page_count = _estimate_page_count(file_size_bytes)
    detected_language = _detect_language(filename, content)
    tags = _extract_tags(filename)
    confidence_score = _simulate_confidence(content)

    return DocumentMetadata(
        filename=filename,
        gcs_path=gcs_path,
        file_size_bytes=file_size_bytes,
        upload_timestamp=upload_timestamp,
        word_count=word_count,
        page_count=page_count,
        detected_language=detected_language,
        tags=tags,
        confidence_score=confidence_score,
    )


# ---------------------------------------------------------------------------
# Internal helpers — replace these with real implementations as needed
# ---------------------------------------------------------------------------
def _download_from_gcs(bucket_name: str, object_name: str) -> tuple[bytes, int]:
    """Download a GCS object and return (content_bytes, size_bytes)."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    content = blob.download_as_bytes()
    return content, len(content)


def _estimate_word_count(content: bytes) -> int:
    """
    Simulated word count.

    Attempt to decode the content as UTF-8 text and split on whitespace.
    For binary files (images, PDFs with no embedded text, etc.) this falls
    back to 0 rather than raising an exception.

    SWAP: Replace with Tesseract / Document AI OCR output.
    """
    try:
        text = content.decode("utf-8", errors="strict")
        return len(text.split())
    except UnicodeDecodeError:
        # Binary file — estimate from size (one word ≈ 5 bytes on average)
        return max(0, len(content) // 5)


def _estimate_page_count(file_size_bytes: int) -> int:
    """
    Simulated page count using a bytes-per-page heuristic.

    Always returns at least 1.

    SWAP: Replace with PDF page count extraction or Document AI page count.
    """
    return max(1, file_size_bytes // _BYTES_PER_PAGE)


def _detect_language(filename: str, content: bytes) -> str:
    """
    Simulated language detection.

    Checks the filename stem for known language tokens; falls back to 'en'.

    SWAP: Replace with google-cloud-language or langdetect.
    """
    stem = os.path.splitext(filename)[0].lower()
    tokens = re.split(r"[\W_]+", stem)
    for token in tokens:
        if token in _LANG_HINTS:
            return _LANG_HINTS[token]

    # Lightweight content sniff: look for common non-ASCII byte sequences
    try:
        sample = content[:512].decode("utf-8", errors="ignore")
        for keyword, lang in _LANG_HINTS.items():
            if keyword in sample.lower():
                return lang
    except Exception:
        pass

    return "en"


def _extract_tags(filename: str) -> list[str]:
    """
    Derive tags by tokenising the filename stem.

    Rules:
    - Strip the file extension.
    - Split on non-alphanumeric characters (spaces, dashes, underscores, dots).
    - Lowercase, deduplicate, drop tokens shorter than 2 characters.
    - Limit to 10 tags maximum.

    SWAP: Replace with keyword extraction (e.g., spaCy NER, Vertex AI NLP).
    """
    stem = os.path.splitext(filename)[0]
    tokens = re.split(r"[\W_]+", stem)
    seen: set[str] = set()
    tags: list[str] = []
    for token in tokens:
        token = token.lower()
        if len(token) >= 2 and token not in seen:
            seen.add(token)
            tags.append(token)
        if len(tags) >= 10:
            break
    return tags


def _simulate_confidence(content: bytes) -> float:
    """
    Simulate an OCR confidence score deterministically seeded by content hash.

    Using a deterministic seed means the same file always produces the same
    score — useful for reproducible tests.

    SWAP: Return the real confidence value from your OCR engine.
    """
    digest = int(hashlib.md5(content[:256]).hexdigest(), 16)  # noqa: S324
    rng = random.Random(digest)
    raw = rng.random()
    return round(_CONFIDENCE_MIN + raw * (_CONFIDENCE_MAX - _CONFIDENCE_MIN), 4)
