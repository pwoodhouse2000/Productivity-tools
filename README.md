# Todoist to Notion Sync

## Overview
This Google Cloud Function, defined in `main.py`, syncs projects from Todoist to a specified Notion database. It is a one-way synchronization: new projects in Todoist are added to Notion. Existing projects in Notion are identified by their **name** to prevent duplicates.
Child projects in Todoist are automatically assigned a "Category" in Notion based on their parent project's name.
## `main.py` Script Purpose
The `main.py` script contains the core logic for the Todoist to Notion synchronization process. It is designed to be deployed as a Google Cloud Function and triggered via HTTP. The script performs the following key operations:
- Securely retrieves API keys and database IDs from Google Cloud Secret Manager.
- Fetches project data from Todoist.
- Fetches existing project data from Notion.
- Compares the projects and creates new entries in Notion for projects that don't already exist there.

## Google Cloud Secret Manager Usage
The script relies heavily on Google Cloud Secret Manager to securely store and access sensitive information like API keys and database IDs. This avoids hardcoding credentials into the source code.

- The `get_secret(secret_name)` function is a utility function responsible for fetching the latest version of a specified secret.
- It requires the `GCP_PROJECT` environment variable to be set for the Cloud Function. This variable provides the Google Cloud Project ID, which is used to construct the full path to the secret.
- The function uses the `google-cloud-secret-manager` client library to interact with the Secret Manager service.
- The service account running the Cloud Function must have the "Secret Manager Secret Accessor" IAM role for the secrets it needs to access.

The following secrets are expected to be configured in Secret Manager:
-   `todoist-api-key`: Your Todoist API token.
-   `notion-api-key`: Your Notion integration token.
-   `notion-database-id`: The ID of the Notion database where projects will be synced.

## Function Descriptions

### `get_secret(secret_name: str) -> str`
-   **Purpose**: Retrieves a specified secret's value from Google Cloud Secret Manager.
-   **Arguments**:
    -   `secret_name (str)`: The name of the secret to fetch (e.g., "todoist-api-key").
-   **Returns**: `str` - The decoded secret value.
-   **Details**: Constructs the full secret path using the `GCP_PROJECT` environment variable and the provided `secret_name`. Uses the `SecretManagerServiceClient` to access the latest version of the secret.

### `get_todoist_projects() -> list`
-   **Purpose**: Fetches all active projects from the user's Todoist account.
-   **Arguments**: None.
-   **Returns**: `tuple` - A tuple containing a list of Todoist project objects and a dictionary mapping project IDs to project names (for parent-child lookups).
-   **Details**:
    -   Retrieves the Todoist API key using `get_secret("todoist-api-key")`.
    -   Makes a GET request to the Todoist REST API endpoint (`https://api.todoist.com/rest/v2/projects`).
    -   Raises an exception if the API request fails.

### `get_notion_projects() -> list`
-   **Purpose**: Fetches existing project pages from the specified Notion database.
-   **Arguments**: None.
-   **Returns**: `list` - A list of Notion page objects (dictionaries) representing projects. Returns an empty list if the query fails or no projects are found.
-   **Details**:
    -   Retrieves the Notion API key and Database ID using `get_secret("notion-api-key")` and `get_secret("notion-database-id")` respectively.
    -   Makes a POST request to the Notion API endpoint (`https://api.notion.com/v1/databases/{database_id}/query`) to query all pages in the database.
    -   Uses Notion API version `2022-06-28`.

### `create_notion_project(project_name: str, category_name: str = None, source: str = None, last_synced: str = None) -> dict`
-   **Purpose**: Creates a new page (project) in the specified Notion database.
-   **Arguments**:
    -   `project_name (str)`: The name of the project to create in Notion.
    -   `category_name (str, optional)`: The name of the parent project, to be set in the "Category" property.
    -   `source (str, optional)`: The source of the project (e.g., "Todoist").
    -   `last_synced (str, optional)`: The ISO 8601 timestamp of the sync.
-   **Returns**: `dict` - The Notion page object created.
-   **Details**:
    -   Retrieves the Notion API key and Database ID.
    -   Constructs the data payload for creating a new page. It sets the "Name" property and can optionally set "Category", "Source", and "Last Synced" properties if they exist in the Notion database.
    -   Makes a POST request to the Notion API endpoint (`https://api.notion.com/v1/pages`).
    -   Raises an exception if the page creation fails, including the status code and error text from Notion.

### `sync_todoist_to_notion() -> dict`
-   **Purpose**: Orchestrates the synchronization logic between Todoist and Notion.
-   **Arguments**: None.
-   **Returns**: `dict` - A dictionary containing the results of the sync operation:
    -   `checked (int)`: Total number of projects fetched from Todoist.
    -   `created (int)`: Number of new projects created in Notion.
    -   `skipped (int)`: Number of Todoist projects already found in Notion (by name) and therefore skipped.
    -   `errors (list)`: A list of error messages for projects that failed to be created.
-   **Details**:
    -   Calls `get_todoist_projects()` to get projects from Todoist.
    -   Calls `get_notion_projects()` to get existing projects from Notion.
    -   Extracts the names of existing Notion projects into a set for efficient lookup.
    -   Iterates through each Todoist project:
        -   If the project name already exists in Notion, it's skipped.
        -   Otherwise, it calls `create_notion_project()` to create it in Notion.
        -   If a Todoist project has a parent, the parent's name is passed as `category_name`.
        -   It also sets the `source` to "Todoist" and `last_synced` to the current time.
        -   Tracks counts for created, skipped projects, and any errors encountered.

### `sync_projects(request) -> tuple`
-   **Purpose**: The main entry point for the Google Cloud Function, triggered by an HTTP request.
-   **Arguments**:
    -   `request`: The HTTP request object provided by the Cloud Functions framework (not directly used by the function logic in this version, but required by the decorator).
-   **Returns**: `tuple` - A tuple containing a JSON response and an HTTP status code.
    -   On success: A JSON object with `status: "success"`, a summary message, and detailed results from `sync_todoist_to_notion()`. Status code 200.
    -   On failure: A JSON object with `status: "error"` and an error message. Status code 500.
-   **Details**:
    -   Wraps the call to `sync_todoist_to_notion()` in a try-except block to handle any exceptions during the sync process.
    -   Formats the response based on the outcome.

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
-   `GCP_PROJECT`: Your Google Cloud Project ID. This environment variable **must be set** for the deployed Cloud Function. It is used by the `get_secret` function to construct the full path to the secrets in Google Secret Manager.

For local development, you would also need to set this environment variable and ensure your local environment is authenticated with GCP (e.g., via `gcloud auth application-default login`) with permissions to access the secrets.

### 4. Google Secret Manager (Setting Up Secrets)
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

**Important**: The service account used by your Google Cloud Function must have the "Secret Manager Secret Accessor" IAM role (`roles/secretmanager.secretAccessor`) on these secrets (or on the project/folder containing them) to access their values. The `get_secret` function in `main.py` uses the `GCP_PROJECT` environment variable to dynamically build the secret resource name.

### 5. Notion Database Setup
Your Notion database must be configured with at least the following property:
-   **`Name`**: This must be a **Title** property. It will store the name of the Todoist project.

To support all features of the current script, you should add the following properties:
-   **`Category`**: A **Select** property. This will be populated with the name of the parent project from Todoist.
-   **`Source`**: A **Rich Text** (or Text) property. This will be set to "Todoist".
-   **`Last Synced`**: A **Date** property. This will be set to the timestamp of when the project was synced.

**Share the Integration**: You also need to share your Notion integration with the target database:
1.  Open the Notion database.
2.  Click the `•••` menu (three dots) in the top-right corner.
3.  Click "Add connections" (or "Open in..." then "Connections" if you are in a page view).
4.  Search for and select the integration you created (e.g., "Todoist Sync Integration").
5.  Ensure it has "Can edit content" permissions.

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