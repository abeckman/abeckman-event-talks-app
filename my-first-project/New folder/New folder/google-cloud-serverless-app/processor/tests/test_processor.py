"""
test_processor.py — Unit tests for processor.py.

All GCS I/O is mocked so these tests run fully offline.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Patch the GCS client at import time so processor.py doesn't try to
# authenticate on import.
with patch("google.cloud.storage.Client"):
    import processor
    from processor import (
        DocumentMetadata,
        _detect_language,
        _estimate_page_count,
        _estimate_word_count,
        _extract_tags,
        _simulate_confidence,
        process_document,
    )


# ---------------------------------------------------------------------------
# _estimate_word_count
# ---------------------------------------------------------------------------
class TestWordCount:
    def test_plain_text_exact_count(self):
        content = b"the quick brown fox jumps over the lazy dog"
        assert _estimate_word_count(content) == 9

    def test_single_word(self):
        assert _estimate_word_count(b"hello") == 1

    def test_empty_content(self):
        assert _estimate_word_count(b"") == 0

    def test_whitespace_only(self):
        assert _estimate_word_count(b"   \n\t  ") == 0

    def test_binary_file_fallback(self):
        # Bytes that cannot be decoded as strict UTF-8
        binary = bytes(range(128, 256))
        result = _estimate_word_count(binary)
        # Fallback: len(content) // 5 — must be a non-negative integer
        assert isinstance(result, int)
        assert result >= 0


# ---------------------------------------------------------------------------
# _estimate_page_count
# ---------------------------------------------------------------------------
class TestPageCount:
    def test_small_file_is_one_page(self):
        assert _estimate_page_count(512) == 1

    def test_exact_boundary(self):
        # 2048 bytes == exactly 1 page (2048 // 2048 = 1)
        assert _estimate_page_count(2048) == 1

    def test_two_pages(self):
        assert _estimate_page_count(4096) == 2

    def test_large_file(self):
        # 1 MB → 512 pages
        assert _estimate_page_count(1024 * 1024) == 512

    def test_zero_bytes_returns_one(self):
        assert _estimate_page_count(0) == 1


# ---------------------------------------------------------------------------
# _detect_language
# ---------------------------------------------------------------------------
class TestLanguageDetection:
    def test_english_default(self):
        assert _detect_language("report.pdf", b"Hello world") == "en"

    def test_french_from_filename(self):
        assert _detect_language("rapport_fr.pdf", b"") == "fr"

    def test_german_from_filename(self):
        assert _detect_language("bericht_german_2024.pdf", b"") == "de"

    def test_spanish_from_filename(self):
        assert _detect_language("documento_spanish.docx", b"") == "es"

    def test_unknown_falls_back_to_english(self):
        # bytes(range(128, 256)) are non-ASCII bytes; decoded with errors='ignore'
        # they produce an empty string, so no language keyword can match.
        assert _detect_language("xyz_123.bin", bytes(range(128, 256))) == "en"

    def test_case_insensitive_filename(self):
        # Uppercase token should still match
        assert _detect_language("FRENCH_REPORT.PDF", b"") == "fr"


# ---------------------------------------------------------------------------
# _extract_tags
# ---------------------------------------------------------------------------
class TestTagExtraction:
    def test_simple_filename(self):
        tags = _extract_tags("invoice_2024_final.pdf")
        assert "invoice" in tags
        assert "2024" in tags
        assert "final" in tags

    def test_extension_excluded(self):
        tags = _extract_tags("report.pdf")
        assert "pdf" not in tags

    def test_short_tokens_excluded(self):
        tags = _extract_tags("a_b_report.txt")
        assert "a" not in tags
        assert "b" not in tags
        assert "report" in tags

    def test_duplicate_tokens_deduplicated(self):
        tags = _extract_tags("foo_foo_bar.txt")
        assert tags.count("foo") == 1

    def test_max_ten_tags(self):
        long_name = "_".join(f"word{i}" for i in range(20))
        tags = _extract_tags(f"{long_name}.pdf")
        assert len(tags) <= 10

    def test_hyphen_separator(self):
        tags = _extract_tags("quarterly-report-2024.docx")
        assert "quarterly" in tags
        assert "report" in tags


# ---------------------------------------------------------------------------
# _simulate_confidence
# ---------------------------------------------------------------------------
class TestConfidenceScore:
    def test_within_range(self):
        for content in [b"hello world", b"", bytes(range(256))]:
            score = _simulate_confidence(content)
            assert 0.70 <= score <= 1.00, f"Score {score} out of range for content {content!r}"

    def test_deterministic(self):
        content = b"reproducible content"
        score1 = _simulate_confidence(content)
        score2 = _simulate_confidence(content)
        assert score1 == score2

    def test_different_inputs_may_differ(self):
        # Not guaranteed to differ, but almost certainly will
        scores = {_simulate_confidence(f"doc{i}".encode()) for i in range(10)}
        assert len(scores) > 1


# ---------------------------------------------------------------------------
# process_document — end-to-end with GCS mocked
# ---------------------------------------------------------------------------
class TestProcessDocument:
    @patch("processor._download_from_gcs")
    def test_full_metadata_structure(self, mock_download: MagicMock):
        sample_text = b"This is a sample document with several words for testing."
        mock_download.return_value = (sample_text, len(sample_text))

        result = process_document(
            bucket_name="my-bucket",
            object_name="reports/quarterly_report_en_2024.pdf",
            upload_timestamp="2024-06-01T12:00:00Z",
        )

        assert isinstance(result, DocumentMetadata)
        assert result.filename == "quarterly_report_en_2024.pdf"
        assert result.gcs_path == "gs://my-bucket/reports/quarterly_report_en_2024.pdf"
        assert result.file_size_bytes == len(sample_text)
        assert result.upload_timestamp == "2024-06-01T12:00:00Z"
        assert isinstance(result.word_count, int) and result.word_count >= 0
        assert isinstance(result.page_count, int) and result.page_count >= 1
        assert isinstance(result.detected_language, str) and len(result.detected_language) > 0
        assert isinstance(result.tags, list)
        assert 0.70 <= result.confidence_score <= 1.00
        assert result.processed_at  # non-empty ISO timestamp

    @patch("processor._download_from_gcs")
    def test_binary_file_does_not_raise(self, mock_download: MagicMock):
        binary = bytes(range(256)) * 100
        mock_download.return_value = (binary, len(binary))

        result = process_document("bucket", "image.png")
        assert result.word_count >= 0
        assert result.page_count >= 1

    @patch("processor._download_from_gcs")
    def test_no_upload_timestamp(self, mock_download: MagicMock):
        mock_download.return_value = (b"hello", 5)
        result = process_document("bucket", "file.txt", upload_timestamp=None)
        assert result.upload_timestamp is None
