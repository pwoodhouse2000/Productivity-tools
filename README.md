# Todoist to Notion Sync

## Overview
This Google Cloud Function syncs projects from Todoist to a specified Notion database. It is a one-way synchronization: new projects in Todoist are added to Notion. Existing projects are identified by their name to prevent duplicates.

## Features
- Fetches all active projects from your Todoist account.
- Creates new projects in Notion if they don't already exist (matched by Todoist Project ID).
- Updates existing projects in Notion if changes are detected in Todoist (e.g., project name). The "Last Synced" timestamp and description are updated.
- Stores a "Todoist ID" in a dedicated property in Notion for reliable matching.
- Each Notion page includes the project name, a "Todoist" source tag, a description referencing the Todoist Project ID, the Todoist ID itself, and a "Last Synced" timestamp.
- Logs operations, errors, and informational messages to Google Cloud Logging for monitoring and troubleshooting.
- HTTP-triggered for easy invocation via URL, Cloud Scheduler, or other services.

## Prerequisites
- Python 3.9+
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
Ensure you have Python 3.9+ installed. Then, install the required Python packages:
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
-   `GCP_PROJECT`: Your Google Cloud Project ID. The function attempts to automatically determine this when deployed on Google Cloud. For local development, you might need to set this environment variable.

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

**Important**: The service account used by your Google Cloud Function must have the "Secret Manager Secret Accessor" IAM role (`roles/secretmanager.secretAccessor`) to access these secrets.

### 5. Notion Database Setup
Your Notion database must be configured with the following properties:

-   **`Name`**: This must be a **Title** property. It will store the name of the Todoist project.
-   **`Source`**: This must be a **Select** property. Create an option named "Todoist" within this property's settings. The function will automatically set this value for new projects.
-   **`Description`**: This must be a **Rich Text** property. It will store a brief description, including a reference to the original Todoist Project ID.
-   **`Todoist ID`**: This must be a **Rich Text** property (alternatively, a Text property can be used if preferred, the script uses Rich Text). This field is crucial as it stores the unique identifier from Todoist, enabling reliable updates.
-   **`Last Synced`**: This must be a **Date** property. It will be updated each time the project is created or updated.

**Share the Integration**: You also need to share your Notion integration with the target database:
1.  Open the Notion database.
2.  Click the `•••` menu (three dots) in the top-right corner.
3.  Click "Add connections" (or "Open in..." then "Connections" if you are in a page view).
4.  Search for and select the integration you created (e.g., "Todoist Sync Integration").
5.  Ensure it has "Can edit content" permissions.

## Deployment
This function is designed to be deployed on Google Cloud Functions.

1.  **Using `gcloud` CLI**:
    ```bash
    gcloud functions deploy sync_projects \
        --gen2 \
        --runtime python39 \
        --region YOUR_REGION \
        --source . \
        --entry-point sync_projects \
        --trigger-http \
        --allow-unauthenticated \ # Or configure authentication as needed
        --set-secrets "todoist-api-key=todoist-api-key:latest,notion-api-key=notion-api-key:latest,notion-database-id=notion-database-id:latest" \
        --service-account YOUR_SERVICE_ACCOUNT_EMAIL
    ```
    -   Replace `YOUR_REGION` with your desired GCP region (e.g., `us-central1`).
    -   Replace `YOUR_SERVICE_ACCOUNT_EMAIL` with the email of the service account that has permissions for Secret Manager.
    -   The `--set-secrets` flag maps the environment variables used in the code to the secrets stored in Secret Manager.
    -   The `--allow-unauthenticated` flag makes the function publicly accessible. For production, consider using authenticated invocations.

2.  **Via Google Cloud Console**:
    -   Navigate to Cloud Functions in the GCP Console.
    -   Click "Create function".
    -   Configure the function:
        -   Environment: 2nd gen
        -   Function name: e.g., `sync-todoist-to-notion`
        -   Region: Your preferred region
        -   Trigger: HTTP, Allow unauthenticated invocations (or set up authentication).
        -   Runtime, build, connections and security settings:
            -   Service account: Select a service account with Secret Manager access.
            -   Under "Runtime environment variables", add references to the secrets:
                -   `todoist-api-key`: `todoist-api-key:latest` (Select "Secret")
                -   `notion-api-key`: `notion-api-key:latest` (Select "Secret")
                -   `notion-database-id`: `notion-database-id:latest` (Select "Secret")
        -   Runtime: Python 3.9 (or your chosen version)
        -   Entry point: `sync_projects`
        -   Source code: Upload a ZIP of the repository or connect to a Cloud Source Repository.

Refer to the [official Google Cloud Functions deployment documentation](https://cloud.google.com/functions/docs/deploying) for more comprehensive instructions.

## Usage
Once deployed, the function can be triggered by sending an HTTP GET or POST request to its assigned URL.

-   **Success Response (200 OK)**:
    The response message will indicate counts for checked, created, and updated projects.
    If any non-critical errors occurred during the processing of individual projects, the status might be "partial_success", and the "errors" array in "details" will be populated.
    ```json
    {
        "status": "success", // or "partial_success" if non-critical errors occurred
        "message": "Sync complete! Checked: Y, Created: X, Updated: U. Skipped: S. Encountered E error(s).",
        "details": {
            "checked": Y,
            "created": X,
            "updated": U,
            "skipped": S, // Should generally be 0 with ID-based matching
            "errors": [ /* array of error messages for specific projects */ ]
        }
    }
    ```
-   **Critical Error Response (500 Internal Server Error)**:
    ```json
    {
        "status": "error",
        "message": "Description of the error that occurred."
    }
    ```

You can use a service like Google Cloud Scheduler to trigger this function on a regular schedule (e.g., daily).

## Project Structure
```
.
├── main.py           # Main Cloud Function logic for syncing.
├── requirements.txt  # Python dependencies.
├── README.md         # This file.
└── .gcloudignore     # Specifies files to ignore during GCP deployment.
└── src/              # Currently unused, planned for future modularization.
```

## Error Handling and Logging
-   The function logs detailed information, warnings, and errors to Google Cloud Logging. This should be your first point of reference for troubleshooting.
-   **Common Errors**:
    -   `Secret Manager secret not found or permission denied`: Ensure the secret names are correct and the function's service account has the "Secret Manager Secret Accessor" role.
    -   `Todoist API error: 401` or `Notion API error: 401`: API key is likely invalid or missing permissions. Verify your API keys.
    -   `Notion API error: 400` or `404` with database ID: The Notion Database ID might be incorrect, or the integration may not have been shared with the database.
    -   `ValueError: GCP_PROJECT environment variable not set.`: Usually occurs during local testing if the `GCP_PROJECT` env var isn't set.
    -   Property mismatch in Notion: If the Notion database properties (`Name`, `Source`, `Description`, `Todoist ID`, `Last Synced`) are not set up exactly as specified, creation or updates will fail. Check the logs for details.
    -   Missing "Todoist ID" on existing pages: If you have pages created before the "Todoist ID" field was used, they won't be updated. Consider manually backfilling this ID or a one-time script.

## Future Improvements
-   **Sync More Fields**: Allow synchronization of other project fields like comments (Todoist `comment_count` to Notion description or comments), labels, due dates, etc.
-   **Selective Sync**: Implement filters to sync only specific Todoist projects (e.g., based on a Todoist label or parent project).
-   **Configuration File**: Manage settings like Notion property names and types via a configuration file for more flexibility.
-   **Enhanced Error Resilience**: Implement more sophisticated retry mechanisms for transient network or API rate limit errors.
-   **Unit and Integration Tests**: Add a comprehensive test suite to ensure reliability.
-   **Two-Way Sync**: Explore options for bidirectional synchronization (significantly more complex, involves handling potential conflicts and update loops).
-   **Deletion Handling**: Decide how to handle projects deleted in Todoist (e.g., delete in Notion, archive in Notion, or ignore).

## Contributing
Contributions are welcome! Please feel free to submit a pull request or open an issue for bugs, feature requests, or improvements.
(Consider adding more specific guidelines if the project grows, e.g., coding style, branch naming conventions.)

## License
This project is released under the MIT License.
(Consider adding an actual `LICENSE` file with the MIT License text if you intend to formally use it.)