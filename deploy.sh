#!/bin/bash
echo "Deploying sync-projects function..."
gcloud functions deploy sync-projects \
  --gen2 \
  --runtime python311 \
  --region us-central1 \
  --source . \
  --entry-point sync_projects \
  --trigger-http \
  --allow-unauthenticated \
  --service-account sync-function-sa@productivity-sync-463008.iam.gserviceaccount.com \
  --set-env-vars GCP_PROJECT=productivity-sync-463008 \
  --timeout 60
echo "Deployment complete!"
