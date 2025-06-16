#!/bin/bash

echo "--- Starting Manual gcloud Installation ---"
# Download and install the Google Cloud SDK silently.
curl -sSL https://sdk.cloud.google.com > install.sh
bash install.sh --disable-prompts --install-dir=~/gcloud

# Add gcloud to the PATH for the current and future terminal sessions.
echo 'source ~/gcloud/google-cloud-sdk/path.bash.inc' >> ~/.bashrc
source ~/gcloud/google-cloud-sdk/path.bash.inc

# Clean up the installer
rm install.sh
echo "--- Manual gcloud Installation Complete ---"
echo ""
echo "--- Authenticating to Google Cloud ---"

# Use the secret we stored in GitHub to log in.
echo ${GCP_SA_KEY} > /tmp/gcp_key.json
gcloud auth activate-service-account --key-file=/tmp/gcp_key.json

# ⚠️ IMPORTANT: Set your Google Cloud Project ID below!
gcloud config set project productivity-sync-463008

# Clean up the key file for security.
rm /tmp/gcp_key.json
echo "--- Authentication complete. Project is set. ---"
echo ""
echo "--- Installing Python packages ---"

# This command will install all packages listed in your requirements.txt file.
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

echo "--- Setup complete! ---"
