# Serverless Event-Driven Document Processing Pipeline

A fully serverless, event-driven pipeline on Google Cloud that ingests uploaded files via Cloud Storage, triggers async processing through Pub/Sub, extracts rich metadata via a Python Cloud Run service (simulated OCR), and streams results into BigQuery.

## Architecture

```
User Upload
    │
    ▼
┌─────────────────────┐
│   Cloud Storage     │  (any file type, us-east1)
│   (ingestion bucket)│
└─────────┬───────────┘
          │ GCS Object Notification (OBJECT_FINALIZE)
          ▼
┌─────────────────────┐       ┌──────────────────────┐
│  Pub/Sub Topic      │──────▶│  Dead-Letter Topic   │
│  (doc-processing)   │       │  (doc-processing-dlq)│
└─────────┬───────────┘       └──────────────────────┘
          │ Push Subscription (authenticated HTTPS POST)
          ▼
┌─────────────────────┐
│  Cloud Run Service  │  (Python + Flask, Buildpacks, us-east1)
│  POST /ingest       │
│  GET  /health       │
└─────────┬───────────┘
          │ Streaming Insert
          ▼
┌─────────────────────┐
│     BigQuery        │
│  dataset: docs_meta │
│  table:   metadata  │
└─────────────────────┘
```

## Project Structure

```
.
├── deploy/
│   ├── setup.sh            # Provision all GCP resources
│   └── teardown.sh         # Destroy all GCP resources
├── processor/
│   ├── main.py             # Flask Cloud Run app (/ingest + /health)
│   ├── processor.py        # Simulated OCR + metadata extraction
│   ├── bigquery_client.py  # BigQuery streaming insert
│   ├── requirements.txt    # Python dependencies
│   └── tests/
│       ├── conftest.py     # pytest path setup
│       ├── test_processor.py
│       └── test_main.py
├── schema/
│   └── metadata_table.json # BigQuery table schema
└── README.md
```

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`, `gsutil`, `bq`) installed and authenticated
- A GCP project with **billing enabled**
- Python 3.11+ (for running tests locally)
- `bash` (Git Bash, WSL, or macOS/Linux terminal)

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

## Deployment

### 1. Set your project ID

```bash
export PROJECT_ID=your-gcp-project-id
```

### 2. Run the setup script

```bash
bash deploy/setup.sh
```

The script runs 9 idempotent steps and is safe to re-run:

| Step | Action |
|------|--------|
| 1 | Enable GCP APIs |
| 2 | Create service account + IAM bindings |
| 3 | Create GCS ingestion bucket |
| 4 | Create Pub/Sub topics (main + DLQ) |
| 5 | Create BigQuery dataset + table |
| 6 | Deploy Cloud Run service via Buildpacks |
| 7 | Grant Pub/Sub invoker role on Cloud Run |
| 8 | Create GCS → Pub/Sub object notification |
| 9 | Create push subscription with dead-letter policy |

### 3. Upload a test file

```bash
gsutil cp path/to/any-file.pdf gs://${PROJECT_ID}-doc-ingestion/
```

Any file type is supported — PDFs, images, text files, binaries.

### 4. Watch it process

```bash
# Stream Cloud Run logs
gcloud run services logs tail doc-processor --region us-east1

# Query BigQuery for results
bq query --nouse_legacy_sql \
  "SELECT filename, word_count, page_count, detected_language, tags, confidence_score, processed_at
   FROM \`${PROJECT_ID}.docs_meta.metadata\`
   ORDER BY processed_at DESC
   LIMIT 10"
```

## Configuration

All configuration is passed to Cloud Run as environment variables. You can override them at deploy time with `--set-env-vars` or update them after deployment:

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | *(required)* | Your GCP project ID |
| `BQ_DATASET_ID` | `docs_meta` | BigQuery dataset name |
| `BQ_TABLE_ID` | `metadata` | BigQuery table name |

## BigQuery Schema

| Field | Type | Mode | Description |
|-------|------|------|-------------|
| `filename` | STRING | REQUIRED | Original filename |
| `gcs_path` | STRING | REQUIRED | Full `gs://` URI |
| `file_size_bytes` | INTEGER | NULLABLE | File size in bytes |
| `upload_timestamp` | TIMESTAMP | NULLABLE | When the file was uploaded (from GCS event) |
| `word_count` | INTEGER | NULLABLE | Estimated word count |
| `page_count` | INTEGER | NULLABLE | Estimated page count |
| `detected_language` | STRING | NULLABLE | Detected language code (e.g. `en`, `fr`) |
| `tags` | STRING | REPEATED | Auto-generated tags from filename |
| `confidence_score` | FLOAT | NULLABLE | Simulated OCR confidence (0.70–1.00) |
| `processed_at` | TIMESTAMP | REQUIRED | When the processor handled this document |

## Dead-Letter Handling

If the Cloud Run service returns a non-2xx response (e.g. GCS download fails, BigQuery insert fails), Pub/Sub will **retry up to 5 times** with exponential backoff. After 5 failures, the message is forwarded to the `doc-processing-dlq` topic.

To inspect dead-lettered messages:

```bash
# Pull up to 10 failed messages
gcloud pubsub subscriptions pull doc-processing-dlq-sub \
  --project=${PROJECT_ID} \
  --limit=10 \
  --auto-ack
```

> You'll need to create a subscription on the DLQ topic manually if you want to pull messages from it.

## Running Tests Locally

```bash
cd processor

# Install dependencies (ideally in a virtualenv)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest

# Run the full test suite
pytest tests/ -v
```

Expected output:
```
tests/test_processor.py::TestWordCount::test_plain_text_exact_count PASSED
tests/test_processor.py::TestWordCount::test_single_word PASSED
...
tests/test_main.py::TestHealthEndpoint::test_returns_200 PASSED
...
========================= 28 passed in Xs =========================
```

## Extending the Pipeline

The processor is designed to be easily upgraded to real implementations:

| Feature | Current (Simulated) | Real Implementation |
|---------|--------------------|--------------------|
| Word count | UTF-8 decode + split | [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) / [Document AI](https://cloud.google.com/document-ai) |
| Page count | Bytes ÷ 2 KB heuristic | PDF library (`pypdf`) / Document AI |
| Language detection | Filename token heuristic | [google-cloud-language](https://cloud.google.com/natural-language) / [`langdetect`](https://pypi.org/project/langdetect/) |
| Tags | Filename tokenisation | [spaCy NER](https://spacy.io/) / Vertex AI NLP |
| Confidence score | Deterministic random | OCR engine output |

Each function in `processor.py` is clearly marked with `SWAP:` comments.

## Teardown

```bash
export PROJECT_ID=your-gcp-project-id
bash deploy/teardown.sh
```

⚠️ This permanently deletes all GCP resources **and all data** in the BigQuery table and GCS bucket. A confirmation prompt is shown before deletion.
