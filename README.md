# Todoist to Notion Sync

## Overview
This Google Cloud Function syncs projects from Todoist to a specified Notion database. It is a one-way synchronization: new projects in Todoist are added to Notion. Existing projects are identified by their **Todoist Project ID** to prevent duplicates and allow for updates.

## Features
- Fetches all active projects from your Todoist account using the REST API.
- Creates new pages in Notion if a corresponding Todoist Project ID is not found in the database.
- Updates existing Notion pages if changes are detected in the corresponding Todoist project (currently, the project name).
- The "Last Synced" timestamp on the Notion page is updated upon every successful sync of the project.
- A "Description" field in Notion is populated with a generated string containing the Todoist Project's comment count and its ID (e.g., "Contains 5 comments. Todoist Project ID: 123456789.").
- Stores a unique "Todoist ID" (Rich Text property) in Notion for reliable matching between Todoist projects and Notion pages.
- Each Notion page includes the project "Name" (Title), a "Source" (Select property set to "Todoist"), the generated "Description", the "Todoist ID", and the "Last Synced" (Date) timestamp.
- Securely accesses API keys (Todoist, Notion) and Notion Database ID from Google Secret Manager using the `GCP_PROJECT` environment variable to construct secret paths.
- Logs operations, errors, and informational messages to Google Cloud Logging for monitoring and troubleshooting.
- HTTP-triggered for easy invocation via URL, Cloud Scheduler, or other services.

## Prerequisites
- Python 3.11+
- A Google Cloud Platform (GCP) project with billing enabled.
- A Todoist account with an API token.
- A Notion account with an integration token and a database created for project syncing.

## Setup and Configuration

### 1. Clone the Repository
```bash
git clone <repository-url>
cd <repository-directory>
```
Replace `<repository-url>` with the actual URL of this repository.

### 2. Install Dependencies
Ensure you have Python 3.11+ installed. Then, install the required Python packages:
```bash
pip install -r requirements.txt
```

### 3. Environment Variables for the Cloud Function
-   `GCP_PROJECT`: Your Google Cloud Project ID. This environment variable **must be set** for the deployed Cloud Function. It is used by the function to construct the full path to the secrets in Google Secret Manager.

For local development, you would also need to set this environment variable and ensure your local environment is authenticated with GCP (e.g., via `gcloud auth application-default login`) with permissions to access the secrets.

### 4. Google Secret Manager
This function relies on Google Secret Manager to securely store API keys and other sensitive information. You must create the following secrets in your GCP project:

-   `todoist-api-key`: Your Todoist API token.
    -   **How to get**: Go to Todoist settings > Integrations > Developer API Token.
-   `notion-api-key`: Your Notion integration token.
    -   **How to get**: Go to Notion's [My Integrations page](https://www.notion.so/my-integrations), create a new integration, and copy the "Internal Integration Token".
-   `notion-database-id`: The ID of the Notion database where projects will be synced.
    -   **How to find**:
        1.  Open your Notion database in a web browser.
        2.  The URL will look something like: `https://www.notion.so/your-workspace/DATABASE_ID?v=VIEW_ID`
        3.  The `DATABASE_ID` is a 32-character alphanumeric string. Copy this value without any hyphens.

**Important**: The service account used by your Google Cloud Function must have the "Secret Manager Secret Accessor" IAM role (`roles/secretmanager.secretAccessor`) on these secrets (or on the project/folder containing them) to access their values.

### 5. Notion Database Setup
Your Notion database must be configured with the following properties:

-   **`Name`**: This must be a **Title** property. It will store the name of the Todoist project.
-   **`Source`**: This must be a **Select** property. Create an option named "Todoist" within this property's settings. The function will automatically set this value for new projects.
-   **`Description`**: This must be a **Rich Text** property. It will store a generated description (e.g., "Contains X comments. Todoist Project ID: YYYYYY.").
-   **`Todoist ID`**: This must be a **Rich Text** property. This field is crucial as it stores the unique identifier from Todoist, enabling reliable updates.
-   **`Last Synced`**: This must be a **Date** property. It will be updated each time the project is successfully synced.

**Share the Integration**: You also need to share your Notion integration with the target database:
1.  Open the Notion database.
2.  Click the `•••` menu (three dots) in the top-right corner.
3.  Click "Add connections" (or "Open in..." then "Connections" if you are in a page view).
4.  Search for and select the integration you created (e.g., "Todoist Sync Integration").
5.  Ensure it has "Can edit content" permissions.

## Deployment
This function is designed to be deployed on Google Cloud Functions (2nd gen).

### 1. Using `gcloud` CLI (Recommended)
This method aligns with the automated deployment in `.github/workflows/deploy.yml`.

```bash
gcloud functions deploy sync-projects \
    --gen2 \
    --runtime python311 \
    --region YOUR_REGION \
    --source . \
    --entry-point sync_projects \
    --trigger-http \
    --allow-unauthenticated \ # Or configure authentication as needed
    --set-env-vars GCP_PROJECT=YOUR_GCP_PROJECT_ID \
    --service-account YOUR_SERVICE_ACCOUNT_EMAIL # Optional: Specify if not using default
```
-   Replace `YOUR_REGION` with your desired GCP region (e.g., `us-central1`).
-   Replace `YOUR_GCP_PROJECT_ID` with your actual Google Cloud Project ID. This is crucial for the function to locate secrets.
-   Replace `YOUR_SERVICE_ACCOUNT_EMAIL` with the email of the service account that will run the function. This service account needs "Secret Manager Secret Accessor" role for the secrets and any other roles required by Cloud Functions. If you are using the default service account for Cloud Functions, ensure it has the necessary permissions.
-   The `--allow-unauthenticated` flag makes the function publicly accessible. For production, consider using authenticated invocations.
-   The function name `sync-projects` is used here, matching the workflow. The entry point in the code is `sync_projects`.

The key difference from previous versions or other common patterns is that API keys are **not** directly passed via `--set-secrets`. Instead, the `GCP_PROJECT` environment variable is passed, and the function code uses this to construct the full resource names for accessing secrets.

### 2. Via Google Cloud Console
If deploying via the Google Cloud Console:
-   Navigate to Cloud Functions in the GCP Console.
-   Click "Create function".
-   Configure the function:
    -   Environment: **2nd gen**
    -   Function name: e.g., `sync-projects`
    -   Region: Your preferred region
    -   Trigger: HTTP, Allow unauthenticated invocations (or set up authentication).
    -   Runtime, build, connections and security settings:
        -   Under "Runtime environment variables", add:
            -   Name: `GCP_PROJECT`, Value: `YOUR_GCP_PROJECT_ID` (replace with your actual project ID).
        -   Service account: Select a service account that has the "Secret Manager Secret Accessor" role for the required secrets.
    -   Runtime: Python 3.11
    -   Entry point: `sync_projects`
    -   Source code: Upload a ZIP of the repository or connect to a Cloud Source Repository.

Refer to the [official Google Cloud Functions deployment documentation](https://cloud.google.com/functions/docs/deploying) for more comprehensive instructions.

## Usage
Once deployed, the function can be triggered by sending an HTTP GET or POST request to its assigned URL.

-   **Success or Partial Success Response (200 OK)**:
    The response message will indicate counts for checked, created, and updated projects.
    If any non-critical errors occurred during the processing of individual projects, the status will be `partial_success`, and the `errors` array in `details` will be populated.
    ```json
    {
        "status": "success", // or "partial_success"
        "message": "Sync complete! Checked: Y, Created: X, Updated: U. Encountered E error(s).",
        "details": {
            "checked": Y,
            "created": X,
            "updated": U,
            "skipped": 0, // This will typically be 0 with the current ID-based matching logic
            "errors": [ /* array of error messages for specific projects, if any */ ]
        }
    }
    ```

-   **Critical Error Response (4xx or 5xx)**:
    For critical errors (e.g., `GCP_PROJECT` not configured, major API failures), an appropriate HTTP status code (like 400 or 500) will be returned with a JSON body.
    ```json
    {
        "status": "error",
        "message": "Server configuration error: GCP_PROJECT environment variable not set.",
        "details": {
            "checked": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 1,
            "error_details": ["GCP_PROJECT environment variable not set."]
        }
    }
    ```

You can use a service like Google Cloud Scheduler to trigger this function on a regular schedule (e.g., daily).

## Project Structure
```
.
├── .github/workflows/deploy.yml # GitHub Actions workflow for automated deployment
├── main.py                      # Main Cloud Function logic for syncing.
├── requirements.txt             # Python dependencies.
├── README.md                    # This file.
└── .gcloudignore                # Specifies files to ignore during GCP deployment.
└── src/                         # Currently unused, can be used for future modularization.
```
(Other files like `.devcontainer/` might be present for development.)

## Error Handling and Logging
-   The function logs detailed information, warnings, and errors to Google Cloud Logging (stdout/stderr from `print` statements in `main.py`). This should be your first point of reference for troubleshooting.
-   **Common Errors**:
    -   `Secret Manager secret not found or permission denied`: Ensure the secret names are correct (`todoist-api-key`, `notion-api-key`, `notion-database-id`), they exist in the correct `GCP_PROJECT`, and the function's service account has the "Secret Manager Secret Accessor" role.
    -   `Todoist API error: 401` or `Notion API error: 401`: API key is likely invalid or missing permissions. Verify your API keys in Secret Manager.
    -   `Notion API error: 400` or `404` with database ID: The Notion Database ID might be incorrect, or the integration may not have been shared with the database with "Can edit content" permissions.
    -   `Configuration error: GCP_PROJECT environment variable not set.`: This occurs if the `GCP_PROJECT` environment variable is not set for the Cloud Function during deployment.
    -   Property mismatch in Notion: If the Notion database properties (`Name`, `Source`, `Description`, `Todoist ID`, `Last Synced`) are not set up exactly as specified, creation or updates will fail. Check the logs for details from the Notion API.
    -   Missing "Todoist ID" on existing Notion pages: If you have pages in Notion created before this sync logic or by other means without the "Todoist ID" field populated, they won't be matched or updated by this script.

## Future Improvements
-   **Sync More Fields**: Allow synchronization of other Todoist project fields if available and desired (e.g., project color, favorite status, or fetching actual comments to populate Notion comments or enhance the description).
-   **Selective Sync**: Implement filters to sync only specific Todoist projects (e.g., based on a Todoist label, parent project, or a specific list of project IDs).
-   **Configuration File/Variables**: Manage settings like Notion property names via environment variables or a configuration file for more flexibility if the database schema changes.
-   **Enhanced Error Resilience**: Implement more sophisticated retry mechanisms (e.g., exponential backoff) for transient network or API rate limit errors from Todoist or Notion.
-   **Unit and Integration Tests**: Add a comprehensive test suite to ensure reliability.
-   **Two-Way Sync**: Explore options for bidirectional synchronization (this is significantly more complex due to potential conflicts and update loops).
-   **Deletion Handling**: Decide how to handle projects deleted in Todoist (e.g., delete in Notion, archive in Notion, or add a "Deleted from Todoist" status). Currently, they remain in Notion.

## Contributing
Contributions are welcome! Please feel free to submit a pull request or open an issue for bugs, feature requests, or improvements.

## License
This project is released under the MIT License.
(Consider adding an actual `LICENSE` file with the MIT License text if you intend to formally use it.)