"""
test_main.py — Unit tests for main.py (Flask routes).

All external dependencies (processor, bigquery_client, GCS) are mocked.
"""

from __future__ import annotations

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Set required env vars before importing main so bigquery_client doesn't fail
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("BQ_DATASET_ID", "docs_meta")
os.environ.setdefault("BQ_TABLE_ID", "metadata")

# Patch GCS + BQ clients before importing anything
with patch("google.cloud.storage.Client"), patch("google.cloud.bigquery.Client"):
    from main import app


@pytest.fixture()
def client():
    """Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_pubsub_body(gcs_event: dict) -> dict:
    """Wrap a GCS event dict in a Pub/Sub push envelope."""
    encoded = base64.b64encode(json.dumps(gcs_event).encode()).decode()
    return {
        "message": {
            "data": encoded,
            "messageId": "1234567890",
            "attributes": {"eventType": "OBJECT_FINALIZE"},
        },
        "subscription": "projects/test-project/subscriptions/doc-processing-sub",
    }


_VALID_GCS_EVENT = {
    "bucket": "my-ingestion-bucket",
    "name": "uploads/invoice_2024.pdf",
    "timeCreated": "2024-06-01T10:00:00.000Z",
    "size": "4096",
}


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
class TestHealthEndpoint:
    def test_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_status_ok(self, client):
        data = response = client.get("/health")
        body = client.get("/health").get_json()
        assert body == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /ingest — success path
# ---------------------------------------------------------------------------
class TestIngestSuccess:
    @patch("main.bigquery_client.stream_metadata")
    @patch("main.processor.process_document")
    def test_valid_message_returns_200(
        self,
        mock_process: MagicMock,
        mock_stream: MagicMock,
        client,
    ):
        from processor import DocumentMetadata

        mock_process.return_value = DocumentMetadata(
            filename="invoice_2024.pdf",
            gcs_path="gs://my-ingestion-bucket/uploads/invoice_2024.pdf",
            file_size_bytes=4096,
            upload_timestamp="2024-06-01T10:00:00.000Z",
            word_count=120,
            page_count=2,
            detected_language="en",
            tags=["invoice", "2024"],
            confidence_score=0.95,
            processed_at="2024-06-01T10:00:01Z",
        )
        mock_stream.return_value = None

        body = _make_pubsub_body(_VALID_GCS_EVENT)
        response = client.post("/ingest", json=body)

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["filename"] == "invoice_2024.pdf"

    @patch("main.bigquery_client.stream_metadata")
    @patch("main.processor.process_document")
    def test_process_document_called_with_correct_args(
        self,
        mock_process: MagicMock,
        mock_stream: MagicMock,
        client,
    ):
        from processor import DocumentMetadata

        mock_process.return_value = DocumentMetadata(
            filename="invoice_2024.pdf",
            gcs_path="gs://my-ingestion-bucket/uploads/invoice_2024.pdf",
            file_size_bytes=4096,
            upload_timestamp="2024-06-01T10:00:00.000Z",
            word_count=0,
            page_count=1,
            detected_language="en",
            tags=[],
            confidence_score=0.80,
            processed_at="2024-06-01T10:00:01Z",
        )

        body = _make_pubsub_body(_VALID_GCS_EVENT)
        client.post("/ingest", json=body)

        mock_process.assert_called_once_with(
            bucket_name="my-ingestion-bucket",
            object_name="uploads/invoice_2024.pdf",
            upload_timestamp="2024-06-01T10:00:00.000Z",
        )


# ---------------------------------------------------------------------------
# POST /ingest — bad request (4xx)
# ---------------------------------------------------------------------------
class TestIngestBadRequest:
    def test_no_body_returns_400(self, client):
        response = client.post("/ingest", data="not json", content_type="text/plain")
        assert response.status_code == 400

    def test_missing_message_key_returns_400(self, client):
        response = client.post("/ingest", json={"subscription": "projects/x/subscriptions/y"})
        assert response.status_code == 400

    def test_invalid_base64_returns_400(self, client):
        body = {
            "message": {"data": "!!!not-base64!!!", "messageId": "1"},
            "subscription": "projects/x/subscriptions/y",
        }
        response = client.post("/ingest", json=body)
        assert response.status_code == 400

    def test_missing_bucket_in_gcs_event_returns_400(self, client):
        event_without_bucket = {"name": "some/file.txt"}
        body = _make_pubsub_body(event_without_bucket)
        response = client.post("/ingest", json=body)
        assert response.status_code == 400

    def test_missing_name_in_gcs_event_returns_400(self, client):
        event_without_name = {"bucket": "my-bucket"}
        body = _make_pubsub_body(event_without_name)
        response = client.post("/ingest", json=body)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /ingest — processor / BQ errors trigger 5xx for Pub/Sub retry
# ---------------------------------------------------------------------------
class TestIngestErrors:
    @patch("main.processor.process_document", side_effect=RuntimeError("GCS download failed"))
    def test_processor_error_returns_500(self, mock_process: MagicMock, client):
        body = _make_pubsub_body(_VALID_GCS_EVENT)
        response = client.post("/ingest", json=body)
        assert response.status_code == 500
        data = response.get_json()
        assert "Processing failed" in data["error"]

    @patch(
        "main.bigquery_client.stream_metadata",
        side_effect=RuntimeError("BQ quota exceeded"),
    )
    @patch("main.processor.process_document")
    def test_bigquery_error_returns_500(
        self,
        mock_process: MagicMock,
        mock_stream: MagicMock,
        client,
    ):
        from processor import DocumentMetadata

        mock_process.return_value = DocumentMetadata(
            filename="file.txt",
            gcs_path="gs://b/file.txt",
            file_size_bytes=100,
            upload_timestamp=None,
            word_count=10,
            page_count=1,
            detected_language="en",
            tags=["file"],
            confidence_score=0.90,
            processed_at="2024-01-01T00:00:00Z",
        )

        body = _make_pubsub_body(_VALID_GCS_EVENT)
        response = client.post("/ingest", json=body)
        assert response.status_code == 500
        data = response.get_json()
        assert "BigQuery insert failed" in data["error"]
