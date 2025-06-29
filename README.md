# Todoist to Notion Sync

## Overview
This Google Cloud Function performs a one-way synchronization of projects and tasks from Todoist into two separate Notion databases. It is designed to be robust, scalable, and easy to deploy.

### Key Features
-   **Project & Task Syncing**: Syncs both Todoist projects and tasks.
-   **Dual Database Model**: Uses separate Notion databases for "Master Projects" and "Master Tasks" for better organization.
-   **Reliable Matching**: Uses a `Todoist ID` property in Notion to reliably track synced items and prevent duplicates, even if names change.
-   **Relational Linking**: Automatically links tasks to their parent project in Notion using a `Relation` property.
-   **Secure**: All secrets (API keys, database IDs) are managed securely using Google Cloud Secret Manager.

## Project Structure
The code is organized into a `src` directory for clarity and maintainability:
```
.
├── .github/workflows/deploy.yml # GitHub Actions workflow for automated deployment
├── main.py                      # The Cloud Function entry point
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── REQUIREMENTS.md              # Detailed functional requirements for the project
└── src/
    ├── __init__.py
    ├── clients.py               # Handles all API communication with Todoist and Notion
    └── sync.py                  # Contains the core synchronization logic
```

## Google Cloud Secret Manager Usage
The script relies heavily on Google Cloud Secret Manager to securely store and access sensitive information like API keys and database IDs. This avoids hardcoding credentials into the source code.

- The `get_secret(secret_name)` function is a utility function responsible for fetching the latest version of a specified secret.

## Setup and Configuration

### 1. Notion Database Setup
You need two databases in Notion.

+**A. "Master Projects" Database**
This database will store your Todoist projects. It must have the following properties:
-   `Name` (Type: **Title**)
-   `Todoist ID` (Type: **Text** or Rich Text) - *This is essential for preventing duplicates.*
-   `Todoist URL` (Type: **URL**)
-   `Status` (Type: **Select**) - *Must include an option named "Planning".*
-   `Source` (Type: **Select**) - *Must include an option named "Todoist".*
-   `Last Synced` (Type: **Date**)
-   `Category` (Type: **Select**) - *Optional, for parent project names.*

+**B. "Master Tasks" Database**
This database will store your Todoist tasks. It must have the following properties:
-   `Name` (Type: **Title**)
-   `Project` (Type: **Relation**) - *Crucially, this must be related to your "Master Projects" database.*
-   `Todoist ID` (Type: **Text** or Rich Text)
-   `Todoist URL` (Type: **URL**)
-   `Due Date` (Type: **Date**)
-   `Priority` (Type: **Select**) - *Must include options: "Priority 1", "Priority 2", "Priority 3", "Priority 4".*
-   `Source` (Type: **Select**) - *Must include an option named "Todoist".*
-   `Last Synced` (Type: **Date**)

### 2. Share Databases with Notion Integration
Your Notion integration must be "shared" with **both** databases.
1.  Open each database.
2.  Click the `•••` menu in the top-right corner.
3.  Click "Add connections" and select your integration.
4.  Ensure it has "Can edit content" permissions.

### 3. Set up Google Cloud Secrets
In the Google Cloud Secret Manager for your project, create the following secrets with their corresponding values:
-   `todoist-api-key`: Your Todoist API token.
-   `notion-api-key`: Your Notion integration token.
-   `notion-projects-database-id`: The ID of your "Master Projects" database.
-   `notion-tasks-database-id`: The ID of your "Master Tasks" database.

## Deployment (High-Level Overview)
This function is designed to be deployed on Google Cloud Functions (2nd gen). The deployment process involves packaging the `main.py` script and its dependencies (`requirements.txt`) and configuring the Cloud Function runtime environment.

### Key Deployment Steps:
1.  **Package Code**: Ensure `main.py`, `requirements.txt`, and any other necessary files are included.
2.  **Specify Runtime**: Python 3.11.
3.  **Set Entry Point**: The function to be executed is `sync_projects` in `main.py`.
4.  **Configure Trigger**: Typically HTTP-triggered.
5.  **Set Environment Variables**: Crucially, `GCP_PROJECT` must be set to your Google Cloud Project ID.
6.  **Assign Service Account**: The function needs a service account with permissions to access secrets from Secret Manager (role: "Secret Manager Secret Accessor").
7.  **Region**: Choose the GCP region for deployment.

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
-   Replace `YOUR_GCP_PROJECT_ID` with your actual Google Cloud Project ID.
-   Replace `YOUR_SERVICE_ACCOUNT_EMAIL` with the email of the service account.
-   The function name `sync-projects` is used here, matching the workflow. The entry point in the code is `sync_projects`.

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
        -   Service account: Select a service account that has the "Secret Manager Secret Accessor" role.
    -   Runtime: Python 3.11
    -   Entry point: `sync_projects`
    -   Source code: Upload a ZIP of the repository or connect to a Cloud Source Repository.

Refer to the [official Google Cloud Functions deployment documentation](https://cloud.google.com/functions/docs/deploying) for more comprehensive instructions.

## Usage
Once deployed, the function can be triggered by sending an HTTP GET or POST request to its assigned URL.

-   **Success Response (200 OK)**:
    ```json
    {
        "status": "success",
        "message": "Sync complete! Created X new projects.",
        "details": {
            "checked": Y,
            "created": X,
            "skipped": Z,
            "errors": [] // or list of errors if some creations failed
        }
    }
    ```
    If `errors` list is populated, it means some projects failed creation, but the function itself completed.

-   **Critical Error Response (500 Internal Server Error)**:
    For critical errors (e.g., `GCP_PROJECT` not configured, major API failures preventing initial setup), an HTTP 500 status code will be returned.
    ```json
    {
        "status": "error",
        "message": "Specific error message here (e.g., Todoist API error: 401)"
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
-   The function logs basic information to Google Cloud Logging via `print()` statements (which are routed to stdout/stderr). For detailed error messages from API calls (like Notion project creation failures), the `sync_todoist_to_notion` function collects these and returns them in the JSON response.
-   **Common Errors**:
    -   `Secret Manager secret not found or permission denied`: Ensure the secret names (`todoist-api-key`, `notion-api-key`, `notion-database-id`) are correct, they exist in the specified `GCP_PROJECT`, and the function's service account has the "Secret Manager Secret Accessor" role.
    -   `Todoist API error: 401` or `Notion API error: 401`: API key is likely invalid or missing permissions. Verify your API keys in Secret Manager.
    -   `Notion API error: 400` or `404` with database ID: The Notion Database ID might be incorrect, or the integration may not have been shared with the database with "Can edit content" permissions.
    -   `Failed to create '{project_name}': {status_code} - {response_text}`: This error (visible in the response `details.errors`) indicates a problem creating a specific project in Notion. Check the Notion database setup (especially the "Name" property type) and the integration permissions.
    -   `GCP_PROJECT environment variable not set`: This error will likely cause `get_secret` to fail, leading to a general error. Ensure `GCP_PROJECT` is set in the Cloud Function's environment variables.

## Future Improvements
-   **Sync More Fields**: The current `main.py` only syncs the project name. It could be extended to sync other Todoist project fields (e.g., comments, color, favorite status) to corresponding Notion properties. This would involve:
    - Adding new properties to the Notion database.
    - Modifying the `create_notion_project` function to include these new properties in the payload.
    - Potentially adding an update mechanism if projects are already synced.
-   **Robust Project Matching**: Currently, projects are skipped if a Notion page with the same *name* exists. For more reliable syncing and to allow updates, use a unique Todoist Project ID stored in a custom property in Notion (e.g., "Todoist ID").
    - This would involve modifying `get_notion_projects` to retrieve this ID.
    - `sync_todoist_to_notion` would need to compare based on this ID.
    - An `update_notion_project` function would be needed.
-   **Selective Sync**: Implement filters to sync only specific Todoist projects.
-   **Enhanced Error Resilience**: Add retries for transient API errors.
-   **Unit and Integration Tests**: Add a comprehensive test suite.
-   **Deletion Handling**: Define behavior for projects deleted in Todoist.

## Contributing
Contributions are welcome! Please feel free to submit a pull request or open an issue for bugs, feature requests, or improvements.

## License
This project is released under the MIT License.
(Consider adding an actual `LICENSE` file with the MIT License text if you intend to formally use it.)