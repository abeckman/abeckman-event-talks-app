"""
bigquery_client.py — Streaming insert helper for the document metadata pipeline.

Wraps the google-cloud-bigquery client to provide a single-function interface
for inserting one DocumentMetadata row into the pipeline's BigQuery table.
"""

from __future__ import annotations

import os
import logging
from typing import Any

from google.cloud import bigquery

from processor import DocumentMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — sourced from environment variables set at Cloud Run deploy time
# ---------------------------------------------------------------------------
_PROJECT_ID: str = os.environ["GCP_PROJECT_ID"]
_DATASET_ID: str = os.environ.get("BQ_DATASET_ID", "docs_meta")
_TABLE_ID: str = os.environ.get("BQ_TABLE_ID", "metadata")


def stream_metadata(metadata: DocumentMetadata) -> None:
    """
    Stream a single ``DocumentMetadata`` record into BigQuery.

    Uses the BigQuery Storage Write API (streaming insert) for low-latency,
    at-least-once delivery.  Any insertion errors are raised as ``RuntimeError``
    so the Cloud Run handler can return HTTP 500 and trigger a Pub/Sub retry.

    Parameters
    ----------
    metadata:
        The extracted document metadata to insert.

    Raises
    ------
    RuntimeError
        If BigQuery reports any row-level insert errors.
    """
    client = bigquery.Client(project=_PROJECT_ID)
    table_ref = f"{_PROJECT_ID}.{_DATASET_ID}.{_TABLE_ID}"

    row: dict[str, Any] = {
        "filename": metadata.filename,
        "gcs_path": metadata.gcs_path,
        "file_size_bytes": metadata.file_size_bytes,
        "upload_timestamp": metadata.upload_timestamp,
        "word_count": metadata.word_count,
        "page_count": metadata.page_count,
        "detected_language": metadata.detected_language,
        "tags": metadata.tags,
        "confidence_score": metadata.confidence_score,
        "processed_at": metadata.processed_at,
    }

    logger.info(
        "Streaming metadata to BigQuery",
        extra={"table": table_ref, "filename": metadata.filename},
    )

    errors = client.insert_rows_json(table_ref, [row])

    if errors:
        error_detail = str(errors)
        logger.error("BigQuery insert errors: %s", error_detail)
        raise RuntimeError(f"BigQuery streaming insert failed: {error_detail}")

    logger.info(
        "Successfully inserted metadata for '%s' into %s",
        metadata.filename,
        table_ref,
    )
