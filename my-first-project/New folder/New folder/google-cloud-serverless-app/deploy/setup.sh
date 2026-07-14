#!/usr/bin/env bash
# =============================================================================
# setup.sh — Provision all GCP resources for the document processing pipeline.
#
# Usage:
#   export PROJECT_ID=your-gcp-project-id
#   bash deploy/setup.sh
#
# Optional overrides (export before running):
#   REGION              (default: us-east1)
#   BUCKET_NAME         (default: ${PROJECT_ID}-doc-ingestion)
#   PUBSUB_TOPIC        (default: doc-processing)
#   PUBSUB_DLQ_TOPIC    (default: doc-processing-dlq)
#   PUBSUB_SUB          (default: doc-processing-sub)
#   SERVICE_NAME        (default: doc-processor)
#   BQ_DATASET          (default: docs_meta)
#   BQ_TABLE            (default: metadata)
#   SERVICE_ACCOUNT     (default: doc-processor-sa)
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Validate required inputs
# ---------------------------------------------------------------------------
if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "ERROR: PROJECT_ID environment variable is not set."
  echo "  export PROJECT_ID=your-gcp-project-id"
  exit 1
fi

# ---------------------------------------------------------------------------
# Configuration (with defaults)
# ---------------------------------------------------------------------------
REGION="${REGION:-us-east1}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-doc-ingestion}"
PUBSUB_TOPIC="${PUBSUB_TOPIC:-doc-processing}"
PUBSUB_DLQ_TOPIC="${PUBSUB_DLQ_TOPIC:-doc-processing-dlq}"
PUBSUB_SUB="${PUBSUB_SUB:-doc-processing-sub}"
SERVICE_NAME="${SERVICE_NAME:-doc-processor}"
BQ_DATASET="${BQ_DATASET:-docs_meta}"
BQ_TABLE="${BQ_TABLE:-metadata}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-doc-processor-sa}"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

# Resolve the script directory so schema paths work regardless of CWD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCHEMA_FILE="${REPO_ROOT}/schema/metadata_table.json"
PROCESSOR_DIR="${REPO_ROOT}/processor"

echo "============================================================"
echo " Document Processing Pipeline — Setup"
echo "============================================================"
echo "  Project  : ${PROJECT_ID}"
echo "  Region   : ${REGION}"
echo "  Bucket   : ${BUCKET_NAME}"
echo "  Topic    : ${PUBSUB_TOPIC}"
echo "  DLQ      : ${PUBSUB_DLQ_TOPIC}"
echo "  Service  : ${SERVICE_NAME}"
echo "  Dataset  : ${BQ_DATASET}.${BQ_TABLE}"
echo "============================================================"

# ---------------------------------------------------------------------------
# Step 1 — Enable required APIs
# ---------------------------------------------------------------------------
echo ""
echo "[1/9] Enabling required GCP APIs..."
gcloud services enable \
  storage.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com \
  bigquery.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  --project="${PROJECT_ID}"

# ---------------------------------------------------------------------------
# Step 2 — Create service account
# ---------------------------------------------------------------------------
echo ""
echo "[2/9] Creating service account ${SA_EMAIL}..."
if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "  Service account already exists — skipping creation."
else
  gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
    --display-name="Document Processor Service Account" \
    --project="${PROJECT_ID}"
fi

# Grant the SA access to GCS (object viewer on the ingestion bucket is set after bucket creation)
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataEditor" \
  --condition=None

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser" \
  --condition=None

# ---------------------------------------------------------------------------
# Step 3 — Create GCS ingestion bucket
# ---------------------------------------------------------------------------
echo ""
echo "[3/9] Creating GCS bucket gs://${BUCKET_NAME}..."
if gsutil ls -b "gs://${BUCKET_NAME}" &>/dev/null; then
  echo "  Bucket already exists — skipping creation."
else
  gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET_NAME}"
fi

# Grant the SA read access to objects in the bucket
gsutil iam ch "serviceAccount:${SA_EMAIL}:roles/storage.objectViewer" "gs://${BUCKET_NAME}"

# ---------------------------------------------------------------------------
# Step 4 — Create Pub/Sub topics
# ---------------------------------------------------------------------------
echo ""
echo "[4/9] Creating Pub/Sub topics..."

for TOPIC in "${PUBSUB_TOPIC}" "${PUBSUB_DLQ_TOPIC}"; do
  if gcloud pubsub topics describe "${TOPIC}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "  Topic '${TOPIC}' already exists — skipping."
  else
    gcloud pubsub topics create "${TOPIC}" --project="${PROJECT_ID}"
    echo "  Created topic: ${TOPIC}"
  fi
done

# ---------------------------------------------------------------------------
# Step 5 — Create BigQuery dataset and table
# ---------------------------------------------------------------------------
echo ""
echo "[5/9] Creating BigQuery dataset and table..."

if bq --project_id="${PROJECT_ID}" show "${BQ_DATASET}" &>/dev/null; then
  echo "  Dataset '${BQ_DATASET}' already exists — skipping."
else
  bq --project_id="${PROJECT_ID}" mk \
    --dataset \
    --location="${REGION}" \
    --description="Document processing pipeline metadata" \
    "${PROJECT_ID}:${BQ_DATASET}"
fi

if bq --project_id="${PROJECT_ID}" show "${BQ_DATASET}.${BQ_TABLE}" &>/dev/null; then
  echo "  Table '${BQ_TABLE}' already exists — skipping."
else
  bq --project_id="${PROJECT_ID}" mk \
    --table \
    --description="Document metadata extracted by the processing pipeline" \
    "${PROJECT_ID}:${BQ_DATASET}.${BQ_TABLE}" \
    "${SCHEMA_FILE}"
fi

# ---------------------------------------------------------------------------
# Step 6 — Deploy Cloud Run service from source (Buildpacks)
# ---------------------------------------------------------------------------
echo ""
echo "[6/9] Deploying Cloud Run service '${SERVICE_NAME}' from source..."
gcloud run deploy "${SERVICE_NAME}" \
  --source="${PROCESSOR_DIR}" \
  --region="${REGION}" \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account="${SA_EMAIL}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET_ID=${BQ_DATASET},BQ_TABLE_ID=${BQ_TABLE}" \
  --project="${PROJECT_ID}"

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo "  Cloud Run URL: ${SERVICE_URL}"

# ---------------------------------------------------------------------------
# Step 7 — Grant Pub/Sub SA permission to invoke Cloud Run
# ---------------------------------------------------------------------------
echo ""
echo "[7/9] Granting Pub/Sub invoker role on Cloud Run service..."
PUBSUB_SA="service-$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/run.invoker" \
  --project="${PROJECT_ID}"

# ---------------------------------------------------------------------------
# Step 8 — Set up GCS → Pub/Sub notification
# ---------------------------------------------------------------------------
echo ""
echo "[8/9] Creating GCS bucket notification → Pub/Sub topic..."
# Remove any existing notifications to stay idempotent
EXISTING=$(gsutil notification list "gs://${BUCKET_NAME}" 2>/dev/null | grep -c "projects/" || true)
if [[ "${EXISTING}" -gt 0 ]]; then
  echo "  Notifications already configured — skipping."
else
  gsutil notification create \
    -t "projects/${PROJECT_ID}/topics/${PUBSUB_TOPIC}" \
    -f json \
    -e OBJECT_FINALIZE \
    "gs://${BUCKET_NAME}"
fi

# ---------------------------------------------------------------------------
# Step 9 — Create Pub/Sub push subscription with dead-letter policy
# ---------------------------------------------------------------------------
echo ""
echo "[9/9] Creating Pub/Sub push subscription '${PUBSUB_SUB}'..."
DLQ_TOPIC_FQN="projects/${PROJECT_ID}/topics/${PUBSUB_DLQ_TOPIC}"

if gcloud pubsub subscriptions describe "${PUBSUB_SUB}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "  Subscription '${PUBSUB_SUB}' already exists — skipping."
else
  gcloud pubsub subscriptions create "${PUBSUB_SUB}" \
    --topic="${PUBSUB_TOPIC}" \
    --push-endpoint="${SERVICE_URL}/ingest" \
    --push-auth-service-account="${PUBSUB_SA}" \
    --ack-deadline=60 \
    --max-delivery-attempts=5 \
    --dead-letter-topic="${DLQ_TOPIC_FQN}" \
    --project="${PROJECT_ID}"
fi

# Grant Pub/Sub SA permission to publish to the DLQ
gcloud pubsub topics add-iam-policy-binding "${PUBSUB_DLQ_TOPIC}" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/pubsub.publisher" \
  --project="${PROJECT_ID}"

# Grant Pub/Sub SA permission to acknowledge on the subscription
gcloud pubsub subscriptions add-iam-policy-binding "${PUBSUB_SUB}" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/pubsub.subscriber" \
  --project="${PROJECT_ID}"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Setup complete!"
echo "============================================================"
echo "  Ingest bucket  : gs://${BUCKET_NAME}"
echo "  Pub/Sub topic  : ${PUBSUB_TOPIC}"
echo "  DLQ topic      : ${PUBSUB_DLQ_TOPIC}"
echo "  Subscription   : ${PUBSUB_SUB}"
echo "  Cloud Run URL  : ${SERVICE_URL}"
echo "  BigQuery table : ${PROJECT_ID}.${BQ_DATASET}.${BQ_TABLE}"
echo ""
echo "  Upload a test file:"
echo "    gsutil cp <your-file> gs://${BUCKET_NAME}/"
echo ""
echo "  Query results:"
echo "    bq query --nouse_legacy_sql \\"
echo "      'SELECT * FROM \`${PROJECT_ID}.${BQ_DATASET}.${BQ_TABLE}\` ORDER BY processed_at DESC LIMIT 5'"
echo "============================================================"
