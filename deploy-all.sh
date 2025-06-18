#!/bin/bash
# Complete deployment script for productivity sync

echo "🚀 Starting deployment..."

PROJECT_ID=productivity-sync-463008
REGION=us-central1

# Deploy main sync function
echo "📦 Deploying sync-projects function..."
gcloud functions deploy sync-projects \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=. \
  --entry-point=sync_projects \
  --trigger-http \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT=$PROJECT_ID \
  --timeout=540

# Deploy history function
echo "📦 Deploying get-sync-history function..."
gcloud functions deploy get-sync-history \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=. \
  --entry-point=get_sync_history \
  --trigger-http \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT=$PROJECT_ID \
  --timeout=60

# Upload web dashboard to Cloud Storage
echo "🌐 Uploading web dashboard..."
gsutil mb -p $PROJECT_ID gs://productivity-sync-dashboard-$PROJECT_ID 2>/dev/null || true
gsutil cp sync-dashboard.html gs://productivity-sync-dashboard-$PROJECT_ID/index.html
gsutil iam ch allUsers:objectViewer gs://productivity-sync-dashboard-$PROJECT_ID

echo "✅ Deployment complete!"
echo ""
echo "📍 Function URLs:"
echo "Sync: https://$REGION-$PROJECT_ID.cloudfunctions.net/sync-projects"
echo "History: https://$REGION-$PROJECT_ID.cloudfunctions.net/get-sync-history"
echo ""
echo "🌐 Dashboard URL:"
echo "https://storage.googleapis.com/productivity-sync-dashboard-$PROJECT_ID/index.html"