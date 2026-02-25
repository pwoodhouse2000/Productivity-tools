#!/bin/bash
set -e

PROJECT="productivity-sync-463008"
REGION="us-central1"
SA="sync-function-sa@${PROJECT}.iam.gserviceaccount.com"
RUNTIME="python311"
ENV_VARS="GCP_PROJECT=${PROJECT}"

echo "=== Deploying to GCP project: ${PROJECT} ==="

echo ""
echo "-> Deploying sync-projects..."
gcloud functions deploy sync-projects \
  --gen2 \
  --runtime ${RUNTIME} \
  --region ${REGION} \
  --source . \
  --entry-point sync_projects \
  --trigger-http \
  --allow-unauthenticated \
  --service-account ${SA} \
  --set-env-vars ${ENV_VARS} \
  --timeout 60

echo ""
echo "-> Deploying todoist-review..."
gcloud functions deploy todoist-review \
  --gen2 \
  --runtime ${RUNTIME} \
  --region ${REGION} \
  --source . \
  --entry-point todoist_review \
  --trigger-http \
  --allow-unauthenticated \
  --service-account ${SA} \
  --set-env-vars ${ENV_VARS} \
  --timeout 60

echo ""
echo "-> Deploying todoist-execute..."
gcloud functions deploy todoist-execute \
  --gen2 \
  --runtime ${RUNTIME} \
  --region ${REGION} \
  --source . \
  --entry-point todoist_execute \
  --trigger-http \
  --allow-unauthenticated \
  --service-account ${SA} \
  --set-env-vars ${ENV_VARS} \
  --timeout 60

echo ""
echo "=== All deployments complete! ==="
echo "Function URLs:"
echo "  https://${REGION}-${PROJECT}.cloudfunctions.net/todoist-review"
echo "  https://${REGION}-${PROJECT}.cloudfunctions.net/todoist-execute"
