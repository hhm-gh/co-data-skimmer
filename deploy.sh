#!/bin/bash
# Deploy co-data-skimmer Streamlit app to GCP Cloud Run.
#
# Usage:
#   ./deploy.sh          # build + deploy
#   ./deploy.sh stop     # route 0% traffic (pause without deleting)
#   ./deploy.sh start    # restore 100% traffic
#   ./deploy.sh delete   # remove the service entirely
#
# Cloud Run scales to zero automatically when idle — no traffic = no cost.
# Use stop/start only if you want to explicitly prevent cold-start invocations.
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project <your-project-id>
#   gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

set -e

PROJECT=$(gcloud config get-value project)
REGION="us-central1"
SERVICE="co-data-skimmer"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${SERVICE}/${SERVICE}"

case "${1:-deploy}" in
  deploy)
    echo "Building and deploying ${SERVICE} to Cloud Run (project: ${PROJECT})..."
    gcloud builds submit --tag "$IMAGE" .
    gcloud run deploy "$SERVICE" \
      --image "$IMAGE" \
      --platform managed \
      --region "$REGION" \
      --allow-unauthenticated \
      --port 8501
    echo ""
    echo "Deployed: $(gcloud run services describe $SERVICE --region $REGION --format 'value(status.url)')"
    ;;
  stop)
    echo "Pausing ${SERVICE} (0% traffic)..."
    gcloud run services update-traffic "$SERVICE" \
      --to-revisions LATEST=0 \
      --region "$REGION"
    echo "Stopped. Run './deploy.sh start' to restore traffic."
    ;;
  start)
    echo "Restoring traffic to ${SERVICE}..."
    gcloud run services update-traffic "$SERVICE" \
      --to-revisions LATEST=100 \
      --region "$REGION"
    echo "Started: $(gcloud run services describe $SERVICE --region $REGION --format 'value(status.url)')"
    ;;
  delete)
    echo "Deleting Cloud Run service ${SERVICE}..."
    gcloud run services delete "$SERVICE" --region "$REGION"
    ;;
  *)
    echo "Usage: $0 [deploy|stop|start|delete]"
    exit 1
    ;;
esac
