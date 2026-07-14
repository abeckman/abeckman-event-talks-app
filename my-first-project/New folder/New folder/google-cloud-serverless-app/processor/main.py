"""
main.py — Cloud Run Flask application for the document processing pipeline.

Routes
------
POST /ingest
    Receives a Pub/Sub push message containing a GCS object notification,
    downloads the file, extracts metadata, and streams it to BigQuery.
    Returns HTTP 200 on success; HTTP 4xx/5xx on failure (triggers Pub/Sub retry).

GET /health
    Liveness / readiness probe. Always returns HTTP 200 {"status": "ok"}.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys

from flask import Flask, Response, jsonify, request

import bigquery_client
import processor

# ---------------------------------------------------------------------------
# Logging — structured JSON so Cloud Logging can parse severity automatically
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"severity":"%(levelname)s","message":"%(message)s","logger":"%(name)s"}',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> Response:
    """Liveness / readiness probe for Cloud Run."""
    return jsonify({"status": "ok"})


@app.post("/ingest")
def ingest() -> tuple[Response, int]:
    """
    Pub/Sub push subscription endpoint.

    Expected request body (Pub/Sub push envelope)::

        {
          "message": {
            "data": "<base64-encoded JSON>",   # GCS storage notification
            "messageId": "...",
            "attributes": {...}
          },
          "subscription": "projects/.../subscriptions/..."
        }

    The decoded ``data`` field contains a GCS object notification with at
    minimum ``bucket`` and ``name`` keys.
    """
    body = request.get_json(silent=True)
    if not body:
        logger.warning("Received request with no JSON body")
        return jsonify({"error": "Missing JSON body"}), 400

    # --- Decode Pub/Sub envelope -------------------------------------------
    try:
        message = body["message"]
        raw_data = base64.b64decode(message["data"]).decode("utf-8")
        gcs_event = json.loads(raw_data)
    except (KeyError, ValueError, base64.binascii.Error) as exc:
        logger.warning("Malformed Pub/Sub message: %s", exc)
        return jsonify({"error": f"Malformed Pub/Sub message: {exc}"}), 400

    # --- Extract GCS object details ----------------------------------------
    bucket_name: str | None = gcs_event.get("bucket")
    object_name: str | None = gcs_event.get("name")
    upload_timestamp: str | None = gcs_event.get("timeCreated")

    if not bucket_name or not object_name:
        logger.warning(
            "GCS event missing 'bucket' or 'name': %s", gcs_event
        )
        return jsonify({"error": "GCS event missing 'bucket' or 'name'"}), 400

    logger.info(
        "Processing document: gs://%s/%s", bucket_name, object_name
    )

    # --- Process document and stream to BigQuery ---------------------------
    try:
        metadata = processor.process_document(
            bucket_name=bucket_name,
            object_name=object_name,
            upload_timestamp=upload_timestamp,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Processor failed for gs://%s/%s: %s", bucket_name, object_name, exc
        )
        # Return 500 so Pub/Sub retries delivery
        return jsonify({"error": f"Processing failed: {exc}"}), 500

    try:
        bigquery_client.stream_metadata(metadata)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "BigQuery insert failed for '%s': %s", metadata.filename, exc
        )
        return jsonify({"error": f"BigQuery insert failed: {exc}"}), 500

    logger.info("Successfully processed '%s'", metadata.filename)
    return jsonify({"status": "ok", "filename": metadata.filename}), 200


# ---------------------------------------------------------------------------
# Entrypoint — Gunicorn is used in production via Procfile / Cloud Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
