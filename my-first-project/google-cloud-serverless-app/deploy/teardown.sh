#!/usr/bin/env bash
# =============================================================================
# teardown.sh — Destroy all GCP resources created by setup.sh.
#
# Usage:
#   export PROJECT_ID=your-gcp-project-id
#   bash deploy/teardown.sh
#
# WARNING: This is irreversible. All data in the BigQuery table and GCS bucket
#          will be permanently deleted.
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
# Configuration — must match setup.sh
# ---------------------------------------------------------------------------
REGION="${REGION:-us-east1}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-doc-ingestion}"
PUBSUB_TOPIC="${PUBSUB_TOPIC:-doc-processing}"
PUBSUB_DLQ_TOPIC="${PUBSUB_DLQ_TOPIC:-doc-processing-dlq}"
PUBSUB_SUB="${PUBSUB_SUB:-doc-processing-sub}"
SERVICE_NAME="${SERVICE_NAME:-doc-processor}"
BQ_DATASET="${BQ_DATASET:-docs_meta}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-doc-processor-sa}"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "============================================================"
echo " Document Processing Pipeline — Teardown"
echo "============================================================"
echo "  Project  : ${PROJECT_ID}"
echo "  Region   : ${REGION}"
echo ""
echo "  WARNING: This will permanently delete all resources and data."
echo "============================================================"
read -r -p "  Type 'yes' to confirm: " CONFIRM
if [[ "${CONFIRM}" != "yes" ]]; then
  echo "Teardown cancelled."
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 1 — Delete Pub/Sub subscription
# ---------------------------------------------------------------------------
echo ""
echo "[1/7] Deleting Pub/Sub subscription '${PUBSUB_SUB}'..."
if gcloud pubsub subscriptions describe "${PUBSUB_SUB}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud pubsub subscriptions delete "${PUBSUB_SUB}" --project="${PROJECT_ID}" --quiet
else
  echo "  Not found — skipping."
fi

# ---------------------------------------------------------------------------
# Step 2 — Delete Pub/Sub topics
# ---------------------------------------------------------------------------
echo ""
echo "[2/7] Deleting Pub/Sub topics..."
for TOPIC in "${PUBSUB_TOPIC}" "${PUBSUB_DLQ_TOPIC}"; do
  if gcloud pubsub topics describe "${TOPIC}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud pubsub topics delete "${TOPIC}" --project="${PROJECT_ID}" --quiet
    echo "  Deleted topic: ${TOPIC}"
  else
    echo "  Topic '${TOPIC}' not found — skipping."
  fi
done

# ---------------------------------------------------------------------------
# Step 3 — Delete Cloud Run service
# ---------------------------------------------------------------------------
echo ""
echo "[3/7] Deleting Cloud Run service '${SERVICE_NAME}'..."
if gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud run services delete "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --quiet
else
  echo "  Not found — skipping."
fi

# ---------------------------------------------------------------------------
# Step 4 — Delete BigQuery dataset (and all tables within)
# ---------------------------------------------------------------------------
echo ""
echo "[4/7] Deleting BigQuery dataset '${BQ_DATASET}' (including all tables)..."
if bq --project_id="${PROJECT_ID}" show "${BQ_DATASET}" &>/dev/null; then
  bq --project_id="${PROJECT_ID}" rm -r -f --dataset "${PROJECT_ID}:${BQ_DATASET}"
else
  echo "  Not found — skipping."
fi

# ---------------------------------------------------------------------------
# Step 5 — Delete GCS bucket and all contents
# ---------------------------------------------------------------------------
echo ""
echo "[5/7] Deleting GCS bucket gs://${BUCKET_NAME} and all objects..."
if gsutil ls -b "gs://${BUCKET_NAME}" &>/dev/null; then
  gsutil -m rm -r "gs://${BUCKET_NAME}" || true
else
  echo "  Not found — skipping."
fi

# ---------------------------------------------------------------------------
# Step 6 — Remove IAM bindings for the service account
# ---------------------------------------------------------------------------
echo ""
echo "[6/7] Removing IAM policy bindings for ${SA_EMAIL}..."
for ROLE in "roles/bigquery.dataEditor" "roles/bigquery.jobUser"; do
  gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet 2>/dev/null || echo "  Binding ${ROLE} not found — skipping."
done

# ---------------------------------------------------------------------------
# Step 7 — Delete service account
# ---------------------------------------------------------------------------
echo ""
echo "[7/7] Deleting service account ${SA_EMAIL}..."
if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts delete "${SA_EMAIL}" --project="${PROJECT_ID}" --quiet
else
  echo "  Not found — skipping."
fi

echo ""
echo "============================================================"
echo " Teardown complete. All pipeline resources have been removed."
echo "============================================================"
