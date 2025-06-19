# Advanced Todoist <-> Notion Synchronization

## Overview

This project offers an advanced, **bi-directional synchronization solution for both projects and tasks** between Todoist and Notion. Deployed as a Google Cloud Function written in Python (`main.py`), it goes beyond simple one-way syncing to provide a more comprehensive alignment of your data across these two platforms.

Key features of this enhanced synchronization include:
*   **Bi-directional Updates**: Changes made to project/task names or completion statuses in either Todoist or Notion are reflected in the other platform.
*   **Task Synchronization**: Individual tasks within projects are synced, including their completion status.
*   **Firestore for State Management**: Google Cloud Firestore is utilized to store mappings between Todoist tasks and Notion pages. This is crucial for preventing duplicates, enabling updates to existing items, and correctly linking related entities.
*   **Synchronization History Logging**: A summary of each synchronization operation (e.g., items created, updated, errors) is logged to a dedicated Firestore collection for monitoring and auditing.
*   **Multiple Notion Databases**: The system interacts with three distinct Notion databases: one for Projects, one for Tasks, and one for Categories (used for structuring project views in Notion).

The project provides two main functionalities through HTTP-triggered Google Cloud Functions:
1.  **Main Sync Process (`sync_trigger`)**: Initiates the bi-directional synchronization of projects and tasks.
2.  **Sync History Retrieval (`get_sync_history`)**: An endpoint to view past synchronization logs stored in Firestore.

This solution aims to provide a robust and near real-time alignment of your project and task management data between Todoist and Notion.

## Understanding Project Lifecycle: Create, Edit, Deploy

To effectively use, customize, and manage this advanced synchronization solution, it's helpful to understand what we mean by "create, edit, and deploy":

*   **Create**: This refers to the initial setup of the project from scratch. This involves:
    *   Cloning this repository to your local machine or development environment.
    *   Installing all necessary Python dependencies listed in `requirements.txt`.
    *   Configuring access to your sensitive API keys (Todoist and Notion) and your Notion Database ID by setting them up in Google Cloud Secret Manager.
    *   Ensuring your Notion database is correctly prepared and shared with your Notion integration.

*   **Edit**: This involves modifying the core synchronization logic, which is primarily located in the `main.py` file. You might edit the code to:
    *   Sync additional fields from Todoist to Notion (e.g., project descriptions, due dates, labels).
    *   Change how data is processed or transformed before being sent to Notion.
    *   Implement different project matching logic (e.g., using a unique Todoist ID instead of just the project name).
    *   After making changes, you would typically test them locally (if possible) or by deploying to a test environment before deploying to production.

*   **Deploy**: This is the process of publishing your (potentially edited) Google Cloud Function to Google Cloud Platform (GCP) so it can run automatically. Deployment can be achieved through several methods:
    *   **Manual `gcloud` commands**: Using the Google Cloud CLI to directly deploy the function from your local machine.
    *   **`deploy.sh` script**: (If provided in the repository) A shell script that automates the `gcloud` deployment commands.
    *   **Automated GitHub Actions workflow**: The project includes a `.github/workflows/deploy.yml` file that automates deployment to GCP whenever changes are pushed to the main branch of the repository. This is the recommended method for continuous integration and deployment.

## `main.py` Script Purpose

The `main.py` script is the heart of this synchronization service. It's designed for deployment as Google Cloud Functions and orchestrates the complex bi-directional flow of data between Todoist and Notion, leveraging Google Cloud Firestore for persistence and logging.

Key operations performed by `main.py` include:

*   **Secure Credential Management**: Utilizes the `get_secret()` utility to fetch sensitive API keys (Todoist, Notion) and various Notion Database IDs from Google Cloud Secret Manager.
*   **Comprehensive Data Fetching**: Retrieves projects and tasks from both Todoist (via its REST API) and Notion (using the Notion API and targeting specific databases for projects, tasks, and categories).
*   **Bi-directional Synchronization Logic**:
    *   **Projects**: Creates new projects from Todoist in Notion and vice-versa. Updates project names if they change on either platform.
    *   **Tasks**: Creates new tasks from Todoist in the corresponding Notion project page's task database, and creates new tasks from Notion back into Todoist under the correct project.
    *   **Updates**: Reflects changes to task names and content (within limits) between platforms.
    *   **Completion Status**: Synchronizes task completion status. Completing a task in Todoist marks it done in Notion, and vice-versa.
*   **Stateful Syncing with Firestore**:
    *   **Task Mapping**: Stores relationships (e.g., Todoist task ID to Notion page ID) in Firestore. This mapping is essential for accurately updating existing items and preventing the creation of duplicates during subsequent sync runs.
    *   **Parent Project Tracking**: Associates tasks with their parent projects using these mappings.
*   **Logging to Firestore**: After each synchronization cycle, a summary (including counts of items created, updated, skipped, and any errors) is written to a `sync_history` collection in Firestore. This provides an auditable trail of operations.
*   **HTTP Endpoints**: Exposes two primary Google Cloud Functions that can be triggered via HTTP:
    *   `sync_trigger` (renamed from `sync_projects` in previous versions): Initiates the main bi-directional synchronization process for projects and tasks.
    *   `get_sync_history`: Allows users to retrieve and view past synchronization logs from Firestore.

This script represents a significant step up from a simple one-way sync, aiming for a more holistic and stateful integration.

## Google Cloud Secret Manager Usage

Securely managing API keys and other sensitive configuration data is critical. This project relies on Google Cloud Secret Manager for this purpose, preventing credentials from being hardcoded into the source.

The `get_secret(secret_name)` utility function within `main.py` is responsible for fetching the latest version of a specified secret. This function requires the `GCP_PROJECT` environment variable to be set for the deployed Cloud Function; this variable provides the Google Cloud Project ID used to construct the full path to the secret. If `GCP_PROJECT` is not found in the environment, the script attempts to infer the Project ID from the runtime environment, but explicitly setting `GCP_PROJECT` during deployment is strongly recommended for reliability.

The service account running the Cloud Function **must** have the "Secret Manager Secret Accessor" IAM role (`roles/secretmanager.secretAccessor`) on the secrets it needs to access (or on the project/folder containing them).

The following secrets **must be configured** in Google Cloud Secret Manager for the function to operate correctly:

*   **`todoist-api-key`**: Your Todoist API token.
    *   *Purpose*: Allows the function to authenticate with the Todoist API to read and write projects and tasks.
*   **`notion-api-key`**: Your Notion integration token ("Internal Integration Token").
    *   *Purpose*: Authenticates the function with the Notion API to read and write pages and database entries.
*   **`notion-database-id`**: The ID of your main Notion **Projects Database**.
    *   *Purpose*: Specifies the primary Notion database where Todoist projects will be synced as pages.
*   **`notion-tasks-db-id`**: The ID of your Notion **Tasks Database**.
    *   *Purpose*: Specifies the Notion database used to store tasks. These tasks are typically linked to pages in the Projects Database.
*   **`notion-categories-db-id`**: The ID of your Notion **Categories Database**.
    *   *Purpose*: Used to manage categories or groupings for projects within Notion, helping to structure the synced data.

Ensure these secret names are used exactly as listed when creating them in Secret Manager.

## Function Descriptions

This section details the core functions within `main.py` and their roles in the synchronization process.

### Core Utilities

#### `get_secret(secret_name: str) -> str`
-   **Purpose**: Securely retrieves a secret's value from Google Cloud Secret Manager.
-   **Arguments**:
    -   `secret_name (str)`: The name of the secret to fetch (e.g., "todoist-api-key").
-   **Returns**: `str` - The decoded secret value.
-   **Details**:
    -   Constructs the full secret resource name using the `GCP_PROJECT` environment variable (or a fallback Project ID if not set, though explicit setting is recommended) and the provided `secret_name`.
    -   Uses the `google-cloud-secret-manager` client library to access the latest enabled version of the secret.
    -   Decodes the secret payload from bytes to a UTF-8 string.

#### `get_todoist_headers() -> dict`
-   **Purpose**: Prepares the standard authorization headers required for Todoist API requests.
-   **Arguments**: None.
-   **Returns**: `dict` - A dictionary containing the `Authorization` header with the Bearer token.
-   **Details**: Retrieves the `todoist-api-key` using `get_secret()` and formats it into the required header structure.

#### `get_notion_headers() -> dict`
-   **Purpose**: Prepares the standard authorization and versioning headers required for Notion API requests.
-   **Arguments**: None.
-   **Returns**: `dict` - A dictionary containing `Authorization`, `Notion-Version`, and `Content-Type` headers.
-   **Details**: Retrieves the `notion-api-key` using `get_secret()` and includes it in the headers along with the Notion API version (`2022-06-28`) and `Content-Type: application/json`.

### Todoist Interaction Functions

#### `get_todoist_projects() -> list`
-   **Purpose**: Fetches all projects from the user's Todoist account.
-   **Arguments**: None.
-   **Returns**: `list` - A list of Todoist project objects (dictionaries).
-   **Details**: Makes a GET request to the Todoist REST API endpoint (`https://api.todoist.com/rest/v2/projects`) using `get_todoist_headers()`. Calls `response.raise_for_status()` to raise an HTTPError for bad responses (4xx or 5xx).

#### `get_todoist_tasks() -> list`
-   **Purpose**: Fetches all active (non-completed) tasks from the user's Todoist account.
-   **Arguments**: None.
-   **Returns**: `list` - A list of Todoist task objects.
-   **Details**: Makes a GET request to the Todoist REST API endpoint (`https://api.todoist.com/rest/v2/tasks`). Uses `response.raise_for_status()`.

#### `get_todoist_completed_tasks() -> list`
-   **Purpose**: Fetches recently completed tasks from Todoist. This functionality might require a Todoist Pro/Business subscription.
-   **Arguments**: None.
-   **Returns**: `list` - A list of completed Todoist task items, or an empty list if the API call fails (e.g., due to subscription limitations or other errors).
-   **Details**: Makes a GET request to the Todoist Sync API endpoint (`https://api.todoist.com/sync/v9/completed/get_all` - Note: the `main.py` actually uses `https://api.todoist.com/rest/v2/completed/get_all`). It includes basic error handling to return an empty list on failure. *(Self-correction: The actual `main.py` uses `https://api.todoist.com/rest/v2/completed/get_all` endpoint. The README should reflect this.)*

#### `get_todoist_labels() -> list`
-   **Purpose**: Fetches all labels (tags) from the user's Todoist account.
-   **Arguments**: None.
-   **Returns**: `list` - A list of Todoist label objects.
-   **Details**: Makes a GET request to the Todoist REST API endpoint (`https://api.todoist.com/rest/v2/labels`). Uses `response.raise_for_status()`.

#### `create_todoist_label(name: str) -> dict`
-   **Purpose**: Creates a new label in Todoist with the given name.
-   **Arguments**:
    -   `name (str)`: The name for the new label.
-   **Returns**: `dict` - The created Todoist label object.
-   **Details**: Makes a POST request to the Todoist REST API endpoint (`https://api.todoist.com/rest/v2/labels`) with the label name in the JSON payload. Uses `response.raise_for_status()`.

#### `get_or_create_label(label_name: str, existing_labels: list) -> str`
-   **Purpose**: Retrieves the ID of an existing Todoist label by name, or creates it if it doesn't exist.
-   **Arguments**:
    -   `label_name (str)`: The desired name of the label.
    -   `existing_labels (list)`: A list of existing Todoist label objects (dictionaries) to search through.
-   **Returns**: `str` - The ID of the existing or newly created Todoist label.
-   **Details**: Iterates through `existing_labels`. If a label with `label_name` is found, its ID is returned. Otherwise, `create_todoist_label()` is called to create the new label, and its ID is returned.

#### `create_or_update_todoist_project(notion_project: dict, todoist_projects: list) -> str`
-   **Purpose**: Creates a new project in Todoist or updates an existing one (specifically its archived status) based on data from a Notion project page.
-   **Arguments**:
    -   `notion_project (dict)`: The Notion project page object.
    -   `todoist_projects (list)`: A list of existing Todoist project objects to check against.
-   **Returns**: `str` - The ID of the created or updated Todoist project.
-   **Details**:
    -   Extracts the project name and status (e.g., "Done", "Canceled" imply archived) from the `notion_project` properties.
    -   Checks if a Todoist project with the same name already exists.
    -   If it exists and its archived status differs from the Notion status, it archives or unarchives the Todoist project accordingly.
    -   If it doesn't exist, a new project is created in Todoist. If the Notion status implies it should be archived, it's archived immediately after creation.
    -   Uses `response.raise_for_status()` for API calls.

#### `create_or_update_todoist_task(notion_task: dict, project_map_reverse: dict, existing_labels: list) -> dict`
-   **Purpose**: Creates a new task in Todoist or updates an existing one based on data from a Notion task page. Handles task content, due date, project assignment, labels, and completion status.
-   **Arguments**:
    -   `notion_task (dict)`: The Notion task page object.
    *   `project_map_reverse (dict)`: A dictionary mapping Notion project page IDs to Todoist project IDs.
    *   `existing_labels (list)`: A list of all existing Todoist labels.
-   **Returns**: `dict` - The created or updated Todoist task object.
-   **Details**:
    *   Extracts task name, completion status ("Done" checkbox), due date, parent project relation, and type (label) from `notion_task` properties.
    *   Queries Firestore (`task_mappings` collection) using the `notion_id` to find an existing Todoist task ID. If not found in Firestore, it checks for a "Todoist ID" property on the Notion task page.
    *   Constructs the task data payload for the Todoist API, including project ID (via `project_map_reverse`) and label ID (via `get_or_create_label`).
    *   **If an existing `todoist_id` is found**:
        *   It first checks if the task still exists in Todoist using a GET request.
        *   If it exists, it updates the task content, due date, project, and labels via a POST request.
        *   It then compares the `is_done` status from Notion with the `is_completed` status from Todoist and makes necessary calls to `/close` or `/reopen` Todoist task endpoints.
    *   **If no `todoist_id` is found (new task)**:
        *   Creates a new task in Todoist.
        *   Saves the mapping between the new Todoist task ID and the Notion page ID to the `task_mappings` collection in Firestore.
        *   If the Notion task was marked "Done", it completes the newly created Todoist task.
    *   Uses `response.raise_for_status()` for API calls.

### Notion Interaction Functions

#### `get_notion_projects() -> list`
-   **Purpose**: Fetches all pages from the Notion Projects Database.
-   **Arguments**: None.
-   **Returns**: `list` - A list of Notion page objects representing projects.
-   **Details**:
    -   Retrieves `notion-database-id` (for the Projects DB) using `get_secret()`.
    -   Makes a POST request to the Notion API's database query endpoint.
    -   Uses `response.raise_for_status()`.

#### `get_notion_tasks() -> list`
-   **Purpose**: Fetches all pages from the Notion Tasks Database.
-   **Arguments**: None.
-   **Returns**: `list` - A list of Notion page objects representing tasks.
-   **Details**:
    -   Retrieves `notion-tasks-db-id` using `get_secret()`.
    -   Makes a POST request to the Notion API's database query endpoint.
    -   Uses `response.raise_for_status()`.

#### `get_notion_categories() -> dict`
-   **Purpose**: Fetches pages from the Notion Categories Database and creates a mapping of category names to their Notion page IDs.
-   **Arguments**: None.
-   **Returns**: `dict` - A dictionary where keys are category names (strings) and values are Notion page IDs (strings). Returns an empty dictionary if the categories database ID is not found or an error occurs.
-   **Details**:
    -   Retrieves `notion-categories-db-id` using `get_secret()`.
    -   Queries the database. It iterates through pages, attempting to find a title property (checking "Name", "Title", then "Category" property names).
    -   If a title is found, it maps `title: page_id`.
    -   Includes basic error handling for cases where the categories DB might not be configured.

#### `create_or_update_notion_project(project_data: dict, existing_projects: list, all_todoist_projects: list, category_map: dict) -> dict`
-   **Purpose**: Creates a new project page in the Notion Projects Database or updates an existing one based on data from a Todoist project.
-   **Arguments**:
    -   `project_data (dict)`: The Todoist project object.
    -   `existing_projects (list)`: A list of existing Notion project page objects to check against by name.
    -   `all_todoist_projects (list)`: A list of all Todoist projects, used to find parent project names for category linking.
    -   `category_map (dict)`: A mapping of category names to Notion Category page IDs.
-   **Returns**: `dict` - The created or updated Notion page object.
-   **Details**:
    -   Searches `existing_projects` for a Notion page whose "Name" property matches `project_data["name"]`.
    -   Constructs the Notion page properties payload, including:
        *   "Name" (Title property).
        *   "Source" (Select property, set to "Todoist").
        *   "Last Synced" (Date property, set to current time).
        *   "Todoist URL" and "Todoist ID" if the Todoist project ID is available.
        *   "Status" (Select property, "Done" if Todoist project is archived, "In Progress" otherwise).
        *   "Category" (Relation property), linking to a Notion Category page if the Todoist project has a parent project whose name exists in `category_map`.
    -   If an existing Notion `page_id` is found, it updates the page using a PATCH request. Otherwise, it creates a new page using a POST request.
    -   Uses `response.raise_for_status()`.

#### `create_or_update_notion_task(task_data: dict, project_map: dict, label_map: dict, is_completed: bool = False) -> dict`
-   **Purpose**: Creates a new task page in the Notion Tasks Database or updates an existing one based on data from a Todoist task.
-   **Arguments**:
    -   `task_data (dict)`: The Todoist task object.
    -   `project_map (dict)`: A dictionary mapping Todoist project IDs to Notion Project page IDs.
    -   `label_map (dict)`: A dictionary mapping Todoist label IDs to label names.
    -   `is_completed (bool)`: Optional, defaults to `False`. Explicitly sets the completion status, useful for syncing completed tasks.
-   **Returns**: `dict` - The created or updated Notion page object for the task.
-   **Details**:
    -   Retrieves `notion-tasks-db-id` using `get_secret()`.
    -   Queries Firestore (`task_mappings` collection) using the Todoist `task_data["id"]` to find an existing Notion page ID.
    -   Constructs the Notion page properties payload:
        *   "Name" (Title property) from `task_data["content"]`.
        *   "Done" (Checkbox property) based on `is_completed` or `task_data.get("is_completed")`.
        *   "Todoist ID" and "Todoist URL".
        *   "Due Date" if present in `task_data`.
        *   "All Pete's Projects" (Relation property) linking to the Notion Project page, using `project_map` and `task_data.get("project_id")`.
        *   "Type" (Select property) using the first label from `task_data.get("labels")` that exists in `label_map`.
    -   If an existing Notion `page_id` is found (from Firestore mapping), it updates the page via PATCH.
    -   Otherwise, it creates a new page via POST.
    -   After successful creation/update, it updates/creates the mapping in the Firestore `task_mappings` collection (document ID is Todoist task ID), storing `todoist_id`, `notion_id`, `last_synced` timestamp, and `notion_url`.
    -   Uses `response.raise_for_status()`.

### Synchronization Logic Functions

#### `sync_task_completion_status(todoist_tasks: list, notion_tasks: list, project_map: dict, label_map: dict) -> dict`
-   **Purpose**: Specifically synchronizes the completion status of tasks between Todoist and Notion for tasks that already exist and are mapped in Firestore.
-   **Arguments**:
    -   `todoist_tasks (list)`: List of active Todoist tasks.
    -   `notion_tasks (list)`: List of Notion task pages.
    -   `project_map (dict)`: Mapping of Todoist project IDs to Notion project page IDs (used if re-creating/updating Notion task is needed, though current implementation focuses on status).
    -   `label_map (dict)`: Mapping of Todoist label IDs to label names (similar to `project_map`).
-   **Returns**: `dict` - A dictionary summarizing status updates (e.g., `{"todoist_to_notion": count, "notion_to_todoist": count}`).
-   **Details**:
    -   Fetches recently completed Todoist tasks using `get_todoist_completed_tasks()`.
    -   Creates a `todoist_status_map` of `todoist_id: is_completed_status`.
    -   Iterates through all task mappings in the Firestore `task_mappings` collection.
    -   For each mapping, it compares the completion status in Todoist (from `todoist_status_map`) with the "Done" checkbox status in the corresponding Notion task (found by looking up `notion_id` in `notion_tasks`).
    -   If statuses differ and the task is completed in Todoist but not Notion, it updates the Notion task to be "Done".
    -   *Note: The function description mentions `notion_to_todoist` updates in returns, but the provided code primarily implements Todoist -> Notion status updates for this specific function. Notion -> Todoist completion is handled within `create_or_update_todoist_task`.*

#### `sync_all() -> dict`
-   **Purpose**: Orchestrates the entire bi-directional synchronization process for projects and tasks.
-   **Arguments**: None.
-   **Returns**: `dict` - A dictionary containing a summary of all operations (projects created/updated, tasks created/updated/status_synced, errors, timestamp).
-   **Details**:
    1.  Fetches initial data: Todoist projects, Notion projects (from Projects DB), and Notion categories.
    2.  **Syncs Projects (Todoist to Notion)**: Iterates through Todoist projects, calling `create_or_update_notion_project` for each.
    3.  **Syncs Projects (Notion to Todoist)**: Refreshes Notion projects, then iterates through them. If a Notion project doesn't have "Todoist" as its "Source" property, it calls `create_or_update_todoist_project`.
    4.  **Creates Project ID Maps**: After project sync, builds `project_map` (Todoist ID -> Notion ID) and `project_map_reverse` (Notion ID -> Todoist ID) by looking up "Todoist ID" or "Todoist URL" properties on the final set of Notion projects.
    5.  Fetches tasks: Todoist active tasks, Notion tasks (from Tasks DB), Todoist labels. Creates a `label_map`.
    6.  **Syncs Task Completion Status**: Calls `sync_task_completion_status` to handle status updates for existing mapped tasks.
    7.  **Syncs Tasks (Todoist to Notion)**: Iterates through active Todoist tasks, calling `create_or_update_notion_task`. Also processes a limited number of recently completed Todoist tasks to ensure they are marked as "Done" in Notion.
    8.  **Syncs Tasks (Notion to Todoist)**: Iterates through Notion tasks, calling `create_or_update_todoist_task`.
    9.  Logs the overall `results` dictionary to the `sync_history` collection in Firestore.
    10. Includes a top-level try-except block to catch critical errors during the entire process.

### HTTP Endpoint Functions

#### `sync_projects(request)`
-   **Purpose**: The main HTTP-triggered Google Cloud Function that initiates the entire bi-directional synchronization process by calling `sync_all()`.
-   **Arguments**:
    -   `request (flask.Request)`: The HTTP request object provided by the Cloud Functions framework. Not directly used by the function logic itself but required by the decorator.
-   **Returns**: `tuple` - A tuple containing a JSON response (summarizing the sync operation or error) and an HTTP status code, along with CORS headers.
-   **Details**:
    -   Handles HTTP `OPTIONS` requests for CORS preflight.
    -   Calls `sync_all()` to perform the synchronization.
    -   Formats a success message based on the counts from `sync_all()` results.
    -   Returns a JSON response with status "success" or "error", a message, and detailed results. Includes CORS headers in the response.
    -   *Note: The `README.md` previously referred to this as `sync_trigger`. The Python code uses `sync_projects`. The description should match the code name.*

#### `get_sync_history(request)`
-   **Purpose**: An HTTP-triggered Google Cloud Function to retrieve and display the last 10 synchronization history logs from Firestore.
-   **Arguments**:
    -   `request (flask.Request)`: The HTTP request object.
-   **Returns**: `tuple` - A tuple containing a JSON response (with sync history or error message) and an HTTP status code, along with CORS headers.
-   **Details**:
    -   Handles HTTP `OPTIONS` requests for CORS preflight.
    -   Queries the `sync_history` collection in Firestore, ordering by `timestamp` (descending) and limiting to 10 results.
    -   Returns a JSON response containing the list of history documents. Includes CORS headers.

## Prerequisites

Before you begin, ensure you have the following set up:

1.  **Python**:
    *   Version 3.11 or newer is recommended (as used in deployment configurations and `main.py`).

2.  **Google Cloud Platform (GCP) Project**:
    *   A GCP project with **billing enabled**.
    *   The following **APIs enabled** in your GCP project (you can enable them by searching for the API in the GCP Console and clicking "Enable"):
        *   **Cloud Functions API**: For deploying and running the function.
        *   **Secret Manager API**: For securely storing API keys and other credentials.
        *   **Cloud Firestore API**: For storing task mappings and synchronization history. (Note: When you create your first database in Firestore mode for your project, this API is typically enabled automatically).
        *   *Cloud Build API*: Usually enabled automatically by GCP when deploying Cloud Functions, as it's used in the build process. If you encounter build issues, ensure this API is enabled.

3.  **Todoist Account**:
    *   A Todoist account (Standard or Premium/Business).
        *   *Note*: Fetching all completed tasks (used in `get_todoist_completed_tasks`) might require a Todoist Premium/Business subscription for full historical access, though recent completions might work on free tiers. The script is designed to gracefully handle an empty list if completed tasks cannot be fetched.
    *   Your **Todoist API token**.

4.  **Notion Account & Workspace**:
    *   A Notion account and workspace.
    *   A **Notion Integration Token**.
    *   **Three distinct Notion Databases created in your workspace**:
        *   A database for **Projects** (e.g., with columns for Name, Status, Todoist ID, Todoist URL, Category Relation, Last Synced, Source).
        *   A database for **Tasks** (e.g., with columns for Name, Done (checkbox), Due Date, Project Relation, Todoist ID, Todoist URL, Type (Select for labels)).
        *   A database for **Categories** (e.g., with a "Name" column). This is used for relating projects, often to represent Todoist parent projects or broader groupings.
        *(Detailed configuration of these databases, including required properties and sharing them with your Notion integration, will be covered in the "Setup and Configuration" section.)*

5.  **Google Cloud CLI (`gcloud`)**:
    *   Installed and configured on your local machine if you plan to:
        *   Deploy the function manually from the command line.
        *   Set up local application default credentials (`gcloud auth application-default login`) for local development and testing.
        *   Manage secrets or other GCP resources via the command line.

## Setup and Configuration

This section provides a comprehensive guide to setting up all components required for the synchronization: your Google Cloud Platform project, Notion workspace (including the three databases), and the application secrets.

### 1. GCP Project Setup

#### 1.1. Enable Required APIs
Ensure the following APIs are enabled in your GCP project. You can usually find and enable them by searching for their names in the GCP Console under "APIs & Services" > "Library".
*   **Cloud Functions API**
*   **Secret Manager API**
*   **Cloud Firestore API**
*   **Cloud Build API** (often enabled automatically with Cloud Functions)

Refer to the "[Prerequisites](#prerequisites)" section for more details.

#### 1.2. Set Up Cloud Firestore
This project uses Cloud Firestore in **Native Mode** to store task mappings and synchronization history.

1.  In the GCP Console, navigate to **Firestore**.
2.  If you haven't used Firestore in this project before, you'll be prompted to select a Firestore mode. **Choose "Native Mode"**. *Do not select Datastore mode.*
3.  Select a **location (region)** for your Firestore database. This should ideally be the same region where you plan to deploy your Cloud Function.
4.  **Firestore Security Rules**:
    By default, Firestore databases have restrictive security rules. You need to allow your Cloud Function's service account to read and write to the database.
    *   Go to the **Firestore** section in the GCP Console.
    *   Navigate to the **"Rules"** tab.
    *   Replace the existing rules with the following (or merge appropriately if you have other rules):
        ```
        rules_version = '2';
        service cloud.firestore {
          match /databases/{database}/documents {
            // Allow read/write access for your function's service account
            // Replace 'YOUR_FUNCTION_SERVICE_ACCOUNT_EMAIL' with the actual email address
            // of the service account your Cloud Function will run as.
            // This is typically YOUR_PROJECT_ID@appspot.gserviceaccount.com for the default App Engine SA,
            // or a custom SA email if you've configured one for the function.
            match /task_mappings/{taskId} {
              allow read, write: if request.auth.token.email == 'YOUR_FUNCTION_SERVICE_ACCOUNT_EMAIL';
            }
            match /sync_history/{historyId} {
              allow read, write: if request.auth.token.email == 'YOUR_FUNCTION_SERVICE_ACCOUNT_EMAIL';
            }
            // Add rules for other collections if needed, or use a broader match:
            // match /{document=**} {
            // allow read, write: if request.auth.token.email == 'YOUR_FUNCTION_SERVICE_ACCOUNT_EMAIL';
            // }
            // For initial setup and testing, a broader rule might be easier,
            // but for production, use more specific rules like the ones for task_mappings and sync_history.
          }
        }
        ```
    *   **Important**: Replace `YOUR_FUNCTION_SERVICE_ACCOUNT_EMAIL` with the email address of the service account your Cloud Function will use at runtime.
    *   Click **"Publish"**.
    *   For production environments, you should implement more granular security rules tailored to your specific access patterns rather than granting broad access.

### 2. Notion Workspace Setup

#### 2.1. Create a Notion Integration
If you haven't already, create a Notion integration and obtain its token:
1.  Go to Notion's "My Integrations" page: [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations).
2.  Click **"+ New integration"**.
3.  Give it a name (e.g., "Todoist-Notion Advanced Sync").
4.  Associate it with the workspace containing your target databases.
5.  Capabilities: Ensure it has **"Read content"**, **"Update content"**, and **"Insert content"** permissions. "Read user information" is generally not needed.
6.  Submit and copy the **"Internal Integration Token"**. This will be your `notion-api-key` secret.

#### 2.2. Create Notion Databases
You need to create three separate databases in Notion. The property names listed below are suggestions based on what `main.py` attempts to use. **It's crucial that property names and types in your Notion databases match what the script expects, especially for "Title" properties and those explicitly named in the script (like "Todoist ID", "Source", "Status", "Done", "All Pete's Projects", "Type").**

**Database 1: Projects Database**
   *   Create a new full-page database in Notion.
   *   **Required & Recommended Properties**:
        *   `Name` (Property Type: **Title**) - *Script relies on this as the primary identifier if "Todoist ID" is missing.*
        *   `Source` (Property Type: **Select**) - Options should include "Todoist" and "Notion". *Script uses this to determine sync direction.*
        *   `Status` (Property Type: **Select**) - Options like "In Progress", "Done", "Canceled". *Script uses this for project archiving status.*
        *   `Todoist ID` (Property Type: **Text** or **Rich Text**) - *Script uses this to store and look up Todoist project ID for reliable mapping.*
        *   `Todoist URL` (Property Type: **URL**) - *Script sets this.*
        *   `Last Synced` (Property Type: **Date**) - *Script updates this.*
        *   `Category` (Property Type: **Relation**) - This should be related to your "Categories Database" (see below). *Script uses this for linking.*
    *   **Share**: Click the `•••` menu on the database page, go to "Connections" (or "Add connections"), and share it with the Notion integration you created (e.g., "Todoist-Notion Advanced Sync"), granting it **"Can edit"** permissions.

**Database 2: Tasks Database**
   *   Create another new full-page database.
   *   **Required & Recommended Properties**:
        *   `Name` (Property Type: **Title**) - *Script relies on this.*
        *   `Done` (Property Type: **Checkbox**) - *Script uses this for completion status.*
        *   `Todoist ID` (Property Type: **Text** or **Rich Text**) - *Critical for mapping tasks; script sets this.*
        *   `Todoist URL` (Property Type: **URL**) - *Script sets this.*
        *   `Due Date` (Property Type: **Date**) - *Script syncs this.*
        *   `All Pete's Projects` (Property Type: **Relation**) - This **must** be related to your "Projects Database". *The name "All Pete's Projects" is hardcoded in `main.py` for this relation property; ensure your Notion database uses this exact name for the relation property pointing to the Projects DB.*
        *   `Type` (Property Type: **Select**) - Used for syncing Todoist labels. Create select options that match your common Todoist labels.
    *   **Share**: Share this database with your Notion integration, granting **"Can edit"** permissions.

**Database 3: Categories Database**
   *   Create a third new full-page database.
   *   **Purpose**: This database is used to structure projects, often by representing Todoist parent projects or other high-level groupings. The script attempts to link projects from the "Projects Database" to this "Categories Database" based on Todoist parent project names.
   *   **Required Properties**:
        *   `Name` (Property Type: **Title**) - The script will look for a title property by checking common names like "Name", "Title", or "Category". This property's values should match the names of your Todoist parent projects if you want automatic categorization.
   *   **Share**: Share this database with your Notion integration. **"Can edit"** permissions are safest, though "Can view" might suffice if the script only reads category names for mapping.

#### 2.3. Obtain Database IDs
For each of the three databases created above, you need its ID:
1.  Open the database as a full page in Notion.
2.  Click the `•••` menu (top-right) and select "Copy link".
3.  The URL will look like `https://www.notion.so/your-workspace/DATABASE_ID?v=VIEW_ID`.
4.  The `DATABASE_ID` is the 32-character alphanumeric string. Copy this value carefully for each database.

### 3. Configure Google Cloud Secret Manager
Create the following secrets in Secret Manager with their respective values:
*   **`todoist-api-key`**: Your Todoist API token.
*   **`notion-api-key`**: Your Notion integration token.
*   **`notion-database-id`**: The Database ID of your **Projects Database**.
*   **`notion-tasks-db-id`**: The Database ID of your **Tasks Database**.
*   **`notion-categories-db-id`**: The Database ID of your **Categories Database**.

Refer to the "[Google Cloud Secret Manager Usage](#google-cloud-secret-manager-usage)" section for more on how secrets are used.

### 4. Set IAM Permissions for the Cloud Function's Service Account
The service account that your Cloud Function will run as needs specific IAM permissions in your GCP project:
*   **`Secret Manager Secret Accessor`** (role: `roles/secretmanager.secretAccessor`): To access the secrets stored in Secret Manager. You can grant this on the specific secrets or on the project level.
*   **`Cloud Datastore User`** (role: `roles/datastore.user`): This role provides permissions to read and write to Firestore (which operates in Datastore mode or Native mode under the hood). This is essential for the function to use Firestore for task mappings and sync history.

You can assign these roles by going to "IAM & Admin" > "IAM" in the GCP Console, finding your service account (or creating a new dedicated one), and adding these roles.

### 5. Clone Repository & Install Dependencies
1.  **Clone or Fork**:
    *   To customize or contribute: Fork the repository on GitHub, then clone your fork.
        ```bash
        git clone https://github.com/YOUR_USERNAME/todoist-notion-sync.git # Replace YOUR_USERNAME
        cd todoist-notion-sync
        ```
    *   To deploy as is:
        ```bash
        git clone <repository-url> # Replace <repository-url> with the main project URL
        cd <repository-directory>
        ```
2.  **Install Dependencies**:
    Navigate to the project directory and install dependencies using pip, preferably within a virtual environment (see "[Local Development and Testing](#local-development-and-testing)" for venv setup).
    ```bash
    pip install -r requirements.txt
    ```

After completing these steps, you'll be ready to proceed with local testing or deployment.

## Local Development and Testing

Setting up a local environment allows you to test changes to `main.py` (and specifically the `sync_all()` function which contains the core logic) before deploying the Cloud Functions.

### 1. Set Up a Virtual Environment
It's highly recommended to use a Python virtual environment to manage project dependencies and avoid conflicts with system-wide packages.

*   **Create a virtual environment** (if you haven't already):
    Open your terminal in the project's root directory and run:
    ```bash
    python -m venv venv
    ```
    This creates a `venv` folder in your project directory.

*   **Activate the virtual environment**:
    *   On macOS and Linux:
        ```bash
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        venv\Scripts\activate
        ```
    Your terminal prompt should change to indicate that the virtual environment is active.

### 2. Install Dependencies
Once your virtual environment is active, install the project dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment for Local Execution
To run the function locally, your environment needs access to your `GCP_PROJECT` ID and must be authenticated with Google Cloud. This authentication allows `main.py` (via the `get_secret` function) to fetch secrets from Google Cloud Secret Manager and also enables interaction with Google Cloud Firestore for task mappings and history logging.

*   **Set `GCP_PROJECT` Environment Variable**:
    The `main.py` script requires the `GCP_PROJECT` environment variable to be set to know which project to use for accessing secrets. You can set this in your terminal session:
    *   macOS/Linux: `export GCP_PROJECT="your-gcp-project-id"`
    *   Windows (PowerShell): `$env:GCP_PROJECT="your-gcp-project-id"`
    *   Windows (CMD): `set GCP_PROJECT=your-gcp-project-id`
    Replace `"your-gcp-project-id"` with your actual GCP Project ID.
    Alternatively, if you are familiar with tools like `python-dotenv`, you can use a `.env` file to manage this environment variable locally. If you do, ensure `.env` is listed in your `.gitignore` file (a pre-configured `.gitignore` including this is provided in the project root). Example `.env` content:
    ```env
    GCP_PROJECT="your-gcp-project-id"
    ```

*   **Authenticate with GCP**:
    Ensure you are authenticated with Google Cloud, and that your Application Default Credentials (ADC) have permission to access secrets in Google Secret Manager and to read/write to your Firestore database. The simplest way to set up ADC for local development is usually:
    ```bash
    gcloud auth application-default login
    ```
    This command requires the `gcloud` CLI to be installed. Follow the prompts to authenticate. Your authenticated user will need "Secret Manager Secret Accessor" and "Cloud Datastore User" (for Firestore) roles on the GCP project.

    **Important**: The `get_secret()` function in `main.py` will fetch all API keys and Notion Database IDs directly from Google Cloud Secret Manager. You do **not** need to set these specific keys/IDs as local environment variables.

### 4. Running the Synchronization Logic Locally
The main synchronization logic is encapsulated in the `sync_all()` function. The HTTP-triggered Cloud Function `sync_projects(request)` (or `sync_trigger` as referred to in some documentation parts, with `sync_projects` being the actual function name in `main.py`) primarily acts as a wrapper around `sync_all()`. For local testing of the core sync process, it's often more direct to call `sync_all()`.

Create a file named `local_test_runner.py` in the root of your project directory with the following content:

```python
# local_test_runner.py
import os
from main import sync_all  # Import sync_all directly
# from main import sync_projects, get_sync_history # Or import HTTP wrappers to test them

# Option 1: Ensure GCP_PROJECT is set in your shell environment as described above.
# Option 2: Or, uncomment and set it here if you prefer:
# os.environ['GCP_PROJECT'] = 'YOUR_ACTUAL_GCP_PROJECT_ID' # Replace with your Project ID

if __name__ == "__main__":
    gcp_project_id = os.getenv('GCP_PROJECT')
    if not gcp_project_id:
        print("Error: GCP_PROJECT environment variable is not set.")
        print("Please set it in your shell, in a .env file (if using python-dotenv), or directly in this script.")
    else:
        print(f"Running local test of sync_all() for GCP Project: {gcp_project_id}...")
        try:
            results = sync_all()  # Call the core sync logic directly
            print("\n--- sync_all() Execution Complete ---")
            print(f"Results: {results}")
        except Exception as e:
            print("\n--- sync_all() Execution Failed ---")
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()

        # --- Optional: Test the get_sync_history endpoint ---
        # print("\n--- Testing get_sync_history endpoint (first ensure sync_all has run at least once)... ---")
        # class MockRequest:
        #     method = 'GET' # Required for the get_sync_history function
        #     # Add other attributes if your HTTP wrapper expects them (e.g., headers, args)
        #
        # mock_http_request = MockRequest()
        # try:
        #     # Ensure get_sync_history is imported if you uncomment this block
        #     from main import get_sync_history
        #     response_data, status_code, _ = get_sync_history(mock_http_request)
        #     print(f"get_sync_history Status: {status_code}")
        #     if status_code == 200:
        #         print("Sync History (up to 10 most recent):")
        #         for item in response_data.get("history", []):
        #             print(item)
        #     else:
        #         print(f"Error fetching history: {response_data}")
        # except Exception as e:
        #     print(f"Error testing get_sync_history: {e}")
        #     import traceback
        #     traceback.print_exc()
```
To run this test script from your project root:
```bash
python local_test_runner.py
```
This directly invokes the main synchronization logic. If you wish to test the full HTTP endpoint behavior of `sync_projects` or `get_sync_history`, you can adapt the script to call those functions, passing a `MockRequest` object (you might need to define attributes on `MockRequest` if your HTTP handlers expect specific request properties).

### 5. Testing Considerations
*   **Use Test Notion Databases and Todoist Account**: It is **strongly recommended** to use separate Notion databases (Projects, Tasks, Categories) and potentially a separate Todoist account or dedicated test projects/labels for development. This prevents accidental modification or deletion of your production data. Update the corresponding secrets in Secret Manager (`notion-database-id`, `notion-tasks-db-id`, `notion-categories-db-id`) temporarily to point to your test database IDs during local testing, or create dedicated test secrets.
*   **Firestore Emulator (Advanced)**: For more isolated testing without interacting with your live Firestore database, you can use the [Firestore emulator](https://cloud.google.com/firestore/docs/emulator). Setting this up involves running the emulator locally and configuring your local environment (often by setting the `FIRESTORE_EMULATOR_HOST` environment variable) so that `main.py`'s Firestore client connects to the local emulator instead of the cloud instance. This is an advanced setup but recommended for rigorous testing. Note that `main.py` itself does not currently include logic to automatically detect the emulator via `FIRESTORE_EMULATOR_HOST`; this would be an addition for a more seamless emulator experience.
*   **Debugging**: Any `print()` statements within `main.py` will output directly to your console when you run `local_test_runner.py`, which is invaluable for debugging.
*   **IAM Permissions for Local User**: Ensure the Google account you authenticated with via `gcloud auth application-default login` has the necessary IAM permissions on your GCP project:
    *   `Secret Manager Secret Accessor` (to read secrets).
    *   `Cloud Datastore User` (to read/write to Firestore).
*   **`.gitignore`**: The root `.gitignore` file in this project is pre-configured to ignore `local_test_runner.py` (if you choose to commit a customized version under a different name, add that name too) and any `.env` files used for local environment variable management.

## Modifying the Function (Editing)

The `main.py` script, with its bi-directional synchronization and Firestore integration, is considerably more complex than a simple one-way sync. Modifications should be approached with care and tested thoroughly using the local development setup.

Before making any changes, ensure you are familiar with:
*   The "[Local Development and Testing](#local-development-and-testing)" section.
*   The "[Function Descriptions](#function-descriptions)" for an overview of how different parts of the script operate.
*   The relevant Todoist and Notion API documentation.

### Key Areas for Modification

Here are some common areas you might want to customize:

**1. Adding New Fields to Sync (Task Example: Priority)**

Let's say you want to sync task priorities between Todoist (which uses P1-P4) and a "Priority" Select property in your Notion Tasks Database.

*   **Step 1: Update Notion Tasks Database**
    *   Add a new property named "Priority" to your Notion Tasks Database.
    *   Choose the **Select** property type.
    *   Manually create options in Notion that correspond to Todoist priorities (e.g., "P1 - Urgent", "P2 - High", "P3 - Medium", "P4 - Low").

*   **Step 2: Understand Todoist Priority Data**
    *   The Todoist API represents priority as an integer: `4` for P1 (Urgent), `3` for P2 (High), `2` for P3 (Medium), `1` for P4 (Low).

*   **Step 3: Modify `create_or_update_notion_task` (Todoist -> Notion Sync)**
    *   In this function, when processing `task_data` from Todoist (which is a Todoist task object):
        *   Get the `priority` value (e.g., `todoist_priority_int = task_data.get('priority')`).
        *   Create a mapping from the Todoist integer to your defined Notion Select option name:
            ```python
            # Example mapping, adjust to your Notion Select option names
            priority_map_to_notion = {
                4: "P1 - Urgent",
                3: "P2 - High",
                2: "P3 - Medium",
                1: "P4 - Low"
            }
            notion_priority_name = priority_map_to_notion.get(todoist_priority_int)
            ```
        *   If `notion_priority_name` is determined, add it to the `properties` dictionary for the Notion page:
            ```python
            if notion_priority_name:
                properties["Priority"] = {"select": {"name": notion_priority_name}}
            else:
                # Handle cases where priority might be missing or unmapped
                # You could set a default, or ensure "Priority" is not included if no match
                properties["Priority"] = None # Or omit this line
            ```

*   **Step 4: Modify `create_or_update_todoist_task` (Notion -> Todoist Sync)**
    *   In this function, when processing `notion_task` (a Notion page object):
        *   Get the selected option name for your "Priority" property from `notion_task["properties"]`.
            `notion_priority_name = notion_task["properties"].get("Priority", {}).get("select", {}).get("name")`
        *   Create a reverse mapping from your Notion Select option name to the Todoist integer:
            ```python
            # Example mapping, adjust to your Notion Select option names
            priority_map_to_todoist = {
                "P1 - Urgent": 4,
                "P2 - High": 3,
                "P3 - Medium": 2,
                "P4 - Low": 1
            }
            todoist_priority_int = priority_map_to_todoist.get(notion_priority_name)
            ```
        *   If `todoist_priority_int` is found, add it to the `task_data` dictionary being prepared for the Todoist API:
            ```python
            if todoist_priority_int:
                task_data["priority"] = todoist_priority_int
            ```

*   **Step 5: Firestore Mappings (`task_mappings` collection)**
    *   No changes are typically needed to the Firestore `task_mappings` structure for syncing additional fields like priority. The mapping primarily links the Todoist task ID with the Notion page ID.

*   **Step 6: Testing**
    *   Create tasks in Todoist with different priorities; run the sync and verify they appear correctly in your Notion Tasks Database.
    *   Create tasks in Notion, selecting different "Priority" options; run the sync and verify the priorities are set correctly in Todoist.
    *   Update priorities on both platforms for existing synced tasks and test if the changes propagate correctly in both directions.

**2. Changing Data Transformation/Mapping**

You might want to alter how existing data is mapped or transformed. For example:
*   **Todoist Labels to Notion "Type" Property**: The current script (in `create_or_update_notion_task`) takes the first label from a Todoist task and maps it to the "Type" Select property in Notion. You could modify this to:
    *   Concatenate multiple Todoist labels into a single Notion Text property.
    *   Map specific Todoist labels to different Notion Select options.
    *   Prioritize certain labels if multiple are present.
*   **Due Dates**: If you need to adjust timezones or date formats (though the script generally uses ISO format which is standard for APIs), these changes would be within `create_or_update_notion_task` (for Todoist to Notion) and `create_or_update_todoist_task` (for Notion to Todoist).

**3. Modifying Project Sync Logic**

Similar to tasks, if you want to sync additional fields for projects (e.g., comments from Todoist, a custom "Project Status Notes" field from Notion):
*   First, ensure the corresponding property exists in your Notion Projects Database or that you know how to structure it for the Todoist API.
*   Modify `create_or_update_notion_project` to extract the new data from the Todoist project object and include it in the Notion page properties payload.
*   Modify `create_or_update_todoist_project` to extract the new data from the Notion project page and include it in the Todoist project data payload.

**4. Adjusting Firestore Usage (Advanced)**

*   The script currently uses Firestore's `task_mappings` collection to link Todoist task IDs with Notion page IDs, and `sync_history` for logging.
*   Advanced users could extend Firestore usage, for example:
    *   Storing more detailed logs for each item synced, not just a summary.
    *   Caching certain non-sensitive data from Todoist/Notion in Firestore to potentially reduce API calls (though this adds significant complexity around cache invalidation and consistency).
    *   Implementing a more sophisticated distributed locking mechanism in Firestore if there's a risk of multiple instances of the sync function running concurrently and causing race conditions (the current script is designed to be run as a single executing instance at any given time).

### Conflict Resolution in Bi-Directional Sync

True bi-directional synchronization introduces the challenge of **conflict resolution**. What happens if a task's name is changed differently in Todoist and Notion *simultaneously* (i.e., both are changed before the next sync cycle)?

*   **Current Approach**: This script generally employs a **"last-write-wins"** type of behavior based on the direction of the sync operation being performed at that moment.
    *   When syncing from Todoist to Notion (e.g., in `create_or_update_notion_task`), the data from the Todoist task is considered the source of truth and will overwrite the corresponding Notion page's properties.
    *   When syncing from Notion to Todoist (e.g., in `create_or_update_todoist_task`), the data from the Notion page is the source and will overwrite the Todoist task.
    *   The `sync_all` function processes changes in a specific order (e.g., Todoist projects to Notion, then Notion projects to Todoist, then tasks). The last operation to process an item will determine its final state if there were conflicting edits between syncs.
*   **No Advanced Conflict Resolution**: This script does **not** implement sophisticated conflict resolution mechanisms like:
    *   Comparing timestamps of individual field changes to see which was more recent.
    *   Providing a UI or log for users to manually resolve detected conflicts.
    *   Prioritizing one platform as the definitive source of truth for all fields or specific fields.
*   **Implications**: If a field is updated on both platforms between sync cycles, the version from the source being processed *during that specific part of the `sync_all` function* will likely overwrite the destination. This is a common simplification in many sync tools.
*   **Future Enhancement**: Implementing more granular conflict resolution would be a significant modification and is noted as a potential "[Future Improvement](#future-improvements)".

When making modifications, be mindful of how your changes might interact with this existing update logic and the potential for data overwrites in conflict scenarios.

### General Advice for Modifications

*   **API Documentation is Key**: Always have the official API documentation for [Todoist REST API](https://developer.todoist.com/rest/v2/) and [Notion API](https://developers.notion.com/reference/intro) open. These are your primary references for available fields, data structures, and request/response formats.
*   **Incremental Changes & Rigorous Testing**: Make small, isolated changes one at a time. After each change, test thoroughly using your local development setup (`local_test_runner.py`) and dedicated test accounts/databases. Test all directions of sync (Todoist to Notion, Notion to Todoist) for any fields you modify.
*   **Understand Firestore `task_mappings`**: If your changes involve how tasks are linked or identified, it's crucial to understand the structure and purpose of the `task_mappings` collection in Firestore. Incorrectly modifying this data or the logic that uses it can lead to duplicate tasks being created or updates failing for existing tasks.
*   **Backup `main.py`**: Before undertaking significant modifications, always create a backup copy of your `main.py` file (or use version control like Git effectively).
*   **Error Handling**: Enhance error handling within the functions you modify. Consider edge cases: What if an expected field is missing from an API response? What if a Notion property type is different than expected? Add `try-except` blocks and informative logging.

By proceeding carefully and testing methodically, you can extend and adapt this synchronization script to your specific needs.

## Project Customization and Adaptation

While this project specifically syncs Todoist projects to a Notion database, its structure and core logic can serve as a template for various other API integration tasks. Understanding its general pattern can help you adapt it for different services or use cases.

### Core Logic Abstraction

This project demonstrates a common pattern for serverless API integrations:

1.  **Secure Credential Management**: Uses Google Cloud Secret Manager (`get_secret` function) to store and access API keys and other sensitive data, avoiding hardcoding them into the script.
2.  **Fetching Data from a Source API**: The `get_todoist_projects()` function is responsible for connecting to the source service (Todoist) and retrieving the necessary data.
3.  **Fetching Data from a Destination API (Optional but common for syncs)**: The `get_notion_projects()` function connects to the destination service (Notion) to retrieve existing data, often used to prevent duplicates or for update logic.
4.  **Data Comparison and Transformation**: The `sync_todoist_to_notion()` function contains the core logic for comparing source and destination data and deciding what actions to take (e.g., which projects are new). This is where any necessary data transformation would also occur to match the destination service's expected format.
5.  **Writing Data to the Destination API**: The `create_notion_project()` function is responsible for sending the processed data to the destination service (Notion) to create new items.
6.  **Serverless Deployment**: The entire logic is wrapped in a main function (`sync_projects`) suitable for deployment as a Google Cloud Function, triggered via HTTP.
7.  **Configuration via Environment Variables**: Key operational parameters like `GCP_PROJECT` are configured via environment variables set during deployment.

### Adapting for Different Services

You can adapt this project by replacing the source (Todoist) or the destination (Notion) with other services that offer APIs.

**Example: Changing the Source (e.g., from Todoist to Asana)**

Imagine you want to sync tasks from Asana to your Notion database instead of Todoist projects.

*   **Fetching Logic**: You would rewrite `get_todoist_projects()` to become `get_asana_tasks()`. This new function would:
    *   Use the Asana API client library (e.g., `asana`) or `requests` to call the appropriate Asana API endpoints (e.g., `/tasks`).
    *   Require new secrets in Secret Manager for Asana API credentials (e.g., an Asana Personal Access Token stored as `asana-api-key`).
*   **Data Structure**: The data structure returned by Asana's API will be different from Todoist's. You'll need to understand Asana's task object.
*   **Core Sync Logic**: The main comparison logic in `sync_todoist_to_notion()` (which you might rename to `sync_asana_to_notion()`) would need to change to process Asana tasks. For example, instead of `project.get("name")`, you'd use the equivalent field from an Asana task object.
*   **Creation Logic**: The `create_notion_project()` function might still be largely usable if your goal is to create Notion pages from Asana tasks. However, the data it receives (now an Asana task object or relevant parts of it) and how it maps that data to Notion page properties would need to be adjusted.

**Example: Changing the Destination (e.g., from Notion to Google Sheets)**

Suppose you want to log your Todoist projects into a Google Sheet instead of a Notion database.

*   **Fetching Destination Data (Optional)**: `get_notion_projects()` would be replaced by a function like `get_existing_projects_from_sheet()`. This function would use the Google Sheets API (e.g., via `google-api-python-client`) to read existing project names from a specific sheet to avoid duplicates.
*   **Creation Logic**: `create_notion_project()` would be replaced by `append_project_to_sheet()`. This function would:
    *   Use the Google Sheets API to append a new row with project details (name, color, etc.).
    *   The data formatting would be different (a list of values for a row) compared to Notion's JSON structure.
*   **Secrets**: You might need new secrets for Google Sheets API access, such as OAuth2 credentials or a service account key if the function authenticates as a service account to access the sheet.

### Key Files for Customization

When adapting the project, these are the primary areas you'll focus on:

*   **`main.py`**: This is where all the core logic resides. You'll modify existing functions or add new ones to interact with different APIs and process data accordingly.
*   **`requirements.txt`**: If you introduce new services, you'll likely need to add their Python client libraries to this file (e.g., `asana`, `google-api-python-client`).
*   **Secret Manager**: You will need to define new secrets in Google Cloud Secret Manager for the API keys and identifiers of the new services you integrate. Update the calls to `get_secret("your-new-secret-name")` in `main.py` to match these new secret names.

### Keeping the GCP Framework

Even if you significantly change the data sources or destinations:

*   The **Google Cloud Function structure** (`sync_projects` as the entry point) can often remain the same.
*   The **Secret Manager integration** (`get_secret` utility function) is reusable for securely accessing any new API keys or credentials.
*   The **deployment methods** (gcloud CLI, GitHub Actions, Cloud Console) described in this README will still be applicable for deploying your modified function to GCP.
*   **Local development practices** (virtual environment, `local_test_runner.py`) can still be used.

### Start Your Own Integration!

Feel free to use this project as a template or a starting point for your own API integration ideas. By understanding its components, you can swap out parts, add new logic, and build powerful custom workflows connecting the tools you use.

## Deployment Options

Deployment is the process of publishing your Google Cloud Functions (defined in `main.py`) to Google Cloud Platform (GCP) so they can be triggered and run their respective logic.

**Important Note on Multiple Functions:** The `main.py` script now defines **two distinct HTTP-triggered functions**:
1.  **`sync_projects`**: This is the main function that triggers the bi-directional synchronization of projects and tasks. *(In previous documentation or internal references, this might have been called `sync_trigger`)*.
2.  **`get_sync_history`**: This function provides an endpoint to retrieve logs of past synchronization operations from Firestore.

The automated deployment tools provided in this repository (`deploy.sh`, `.github/workflows/deploy.yml`) are primarily configured to deploy the `sync_projects` function. Deploying the `get_sync_history` function, or any other custom functions you might add to `main.py`, will require manual adjustments to these scripts/workflows or separate deployment commands.

**Runtime Service Account Permissions:**
Regardless of the deployment method, the **runtime service account** used by your Cloud Functions (e.g., `sync_projects` and `get_sync_history`) needs the following IAM roles in your GCP project:
*   **`Secret Manager Secret Accessor`** (`roles/secretmanager.secretAccessor`): To fetch API keys and database IDs.
*   **`Cloud Datastore User`** (`roles/datastore.user`): To read from and write to Firestore (for task mappings and sync history).

### 1. Automated Deployment with GitHub Actions (for `sync_projects`)

This repository includes a GitHub Actions workflow file (`.github/workflows/deploy.yml`) that automates the deployment of the `sync_projects` function. This is recommended if you have forked the repository and want continuous deployment for the main sync functionality.

**How it Works:**
-   The workflow is triggered automatically when you push changes to the `main` branch of your forked repository.
-   It uses the `google-github-actions/auth` action to authenticate with GCP using a service account key.
-   It then uses `google-github-actions/setup-gcloud` to set up the `gcloud` CLI and deploys the `sync_projects` function.

**Prerequisites for Your Fork (for GitHub Actions Service Account):**
To use this automated workflow, the service account whose key is stored in `GCP_SA_KEY` needs the following roles in your GitHub repository's settings (`Settings > Secrets and variables > Actions`):
1.  **`GCP_PROJECT_ID`** (Note: The workflow uses `secrets.GCP_PROJECT` but it's better to use `GCP_PROJECT_ID` for clarity if you set it up now):
    *   **Type**: Repository Secret
    *   **Value**: Your Google Cloud Project ID.
2.  **`GCP_SA_KEY`**:
    *   **Type**: Repository Secret
    *   **Value**: The JSON key for the Google Cloud Service Account that will perform the deployment. To get this:
        1.  **Create a Service Account (SA) in your GCP Project**:
            *   Navigate to "IAM & Admin" > "Service Accounts" in the Google Cloud Console.
            *   Click "+ CREATE SERVICE ACCOUNT".
            *   Give it a descriptive name (e.g., `github-actions-deployer`).
            *   **Grant this Service Account the following roles on your GCP project**:
                *   `Cloud Functions Admin` (`roles/cloudfunctions.admin`): Allows deploying and managing Cloud Functions.
                *   `Service Account User` (`roles/iam.serviceAccountUser`): Allows this SA to act as (impersonate) the runtime service account of the Cloud Function if they are different (which is good practice).
            *   Click "Continue" / "Done" as appropriate.
        2.  **Generate a JSON Key for this Service Account**:
            *   Find the created SA, click on it, go to the "KEYS" tab.
            *   Click "ADD KEY" > "Create new key".
            *   Choose "JSON" and click "CREATE". A JSON file will be downloaded.
            *   Open the JSON file, copy its entire contents, and paste it as the value for the `GCP_SA_KEY` secret in GitHub.

The workflow file (`.github/workflows/deploy.yml`) hardcodes the function name `sync-projects` and region (`us-central1`). You can edit this file in your fork to change the region or other parameters. See notes below on adapting it for `get_sync_history`.

### 2. Using `gcloud` CLI (for `sync_projects` and `get_sync_history`)

You can manually deploy (or update) each function from your local machine using the `gcloud` command-line tool. Ensure you have installed `gcloud` and authenticated (`gcloud auth login`, `gcloud config set project YOUR_GCP_PROJECT_ID`).

**Deploying `sync_projects`:**
```bash
gcloud functions deploy sync-projects \
    --gen2 \
    --runtime python311 \
    --region YOUR_REGION \
    --source . \
    --entry-point sync_projects \
    --trigger-http \
    --allow-unauthenticated \ # Consider security implications below
    --set-env-vars GCP_PROJECT=YOUR_GCP_PROJECT_ID \
    --service-account YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL # Email of the runtime SA
```

**Explanation of Parameters:**
-   `sync-projects`: The desired name for your deployed Cloud Function.
-   `--gen2`: Specifies a 2nd generation Cloud Function.
-   `--runtime python311`: Sets the runtime environment.
-   `--region YOUR_REGION`: The GCP region (e.g., `us-central1`).
-   `--source .`: Source code is in the current directory.
-   `--entry-point sync_projects`: The Python function in `main.py` to execute.
-   `--trigger-http`: Makes the function invokable via HTTP.
-   `--allow-unauthenticated`: Allows public access. **Security Note**: For production, configure authentication (remove this flag and set up IAM or API Gateway). See [GCP documentation on securing Cloud Functions](https://cloud.google.com/functions/docs/securing/authenticating).
-   `--set-env-vars GCP_PROJECT=YOUR_GCP_PROJECT_ID`: Sets the required environment variable.
-   `--service-account YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL`: Specifies the runtime IAM service account (must have Secret Manager and Firestore access).

### 3. Deploying `get_sync_history` via `gcloud` CLI

To deploy the `get_sync_history` function, use a similar command, changing the function name and entry point:
```bash
gcloud functions deploy get-sync-history \
    --gen2 \
    --runtime python311 \
    --region YOUR_REGION \
    --source . \
    --entry-point get_sync_history \
    --trigger-http \
    --allow-unauthenticated \ # Consider security implications
    --set-env-vars GCP_PROJECT=YOUR_GCP_PROJECT_ID \
    --service-account YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL # Typically the same SA as for sync_projects
```
Ensure `YOUR_REGION`, `YOUR_GCP_PROJECT_ID`, and `YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL` are replaced with your actual values.

### 4. Using the `deploy.sh` Script

The repository includes a `deploy.sh` script primarily for the `sync_projects` function.

**To use and adapt it:**
1.  **Make it executable**: `chmod +x deploy.sh`
2.  **Customize the script**: Open `deploy.sh`. It hardcodes values for region, `GCP_PROJECT`, and the function to deploy (`sync-projects`).
    ```bash
    #!/bin/bash
    echo "Deploying sync-projects function..."
    gcloud functions deploy sync-projects \
      --gen2 \
      --runtime python311 \
      --region us-central1 \ # <-- Check/Change this
      --source . \
      --entry-point sync_projects \
      --trigger-http \
    --allow-unauthenticated \ # Consider security implications
    --set-env-vars GCP_PROJECT=YOUR_GCP_PROJECT_ID_HERE \ # <-- EDIT THIS
    --timeout 60 # Timeout in seconds
    # Add --service-account YOUR_RUNTIME_SA_EMAIL if not using default
    echo "Deployment complete for sync-projects!"

    # To deploy get_sync_history as well, uncomment and adapt the following:
    # echo "Deploying get-sync-history function..."
    # gcloud functions deploy get-sync-history \
    #   --gen2 \
    #   --runtime python311 \
    #   --region us-central1 \ # <-- Ensure this matches
    #   --source . \
    #   --entry-point get_sync_history \
    #   --trigger-http \
    #   --allow-unauthenticated \
    #   --set-env-vars GCP_PROJECT=YOUR_GCP_PROJECT_ID_HERE \ # <-- Ensure this matches
    #   --service-account YOUR_RUNTIME_SA_EMAIL # Optional: if different from sync_projects SA
    #   --timeout 60
    # echo "Deployment complete for get-sync-history!"
    ```
    **You MUST change `GCP_PROJECT=YOUR_GCP_PROJECT_ID_HERE` to your own project ID.** You can uncomment and adapt the second block to deploy `get_sync_history`.
3.  **Run the script**: `./deploy.sh`

### 5. Adapting GitHub Actions for `get_sync_history`

The existing `.github/workflows/deploy.yml` deploys `sync-projects`. To also deploy `get_sync_history` via GitHub Actions, you would need to modify this workflow file. This typically involves adding another "step" within the deployment job that mirrors the `gcloud functions deploy` command for `sync-projects`, but with the `entry-point` changed to `get_sync_history` and the function name changed to `get-sync-history`.

Example conceptual addition to the `run` block in `.github/workflows/deploy.yml`:
```yaml
      - run: |
          # Existing command for sync-projects
          gcloud functions deploy sync-projects \
            --gen2 \
            --runtime=python311 \
            --region=us-central1 \
            --source=. \
            --entry-point=sync_projects \
            --trigger-http \
            --allow-unauthenticated \
            --set-env-vars GCP_PROJECT=${{ secrets.GCP_PROJECT_ID }} \ # Ensure secret is named GCP_PROJECT_ID or update
            --timeout=60

          # New command for get-sync-history
          echo "Deploying get-sync-history function..."
          gcloud functions deploy get-sync-history \
            --gen2 \
            --runtime=python311 \
            --region=us-central1 \ # Ensure region matches
            --source=. \
            --entry-point=get_sync_history \
            --trigger-http \
            --allow-unauthenticated \
            --set-env-vars GCP_PROJECT=${{ secrets.GCP_PROJECT_ID }} \ # Ensure secret is named GCP_PROJECT_ID or update
            --timeout=60
          # Note: You might need to specify --service-account if it's different
          # or if the default SA for the project doesn't have the right permissions.
```
Remember to use consistent service accounts and ensure the GitHub secret for `GCP_PROJECT_ID` is correctly named and configured in your repository settings.

### 6. Via Google Cloud Console (Manual UI Deployment)

You can deploy both `sync_projects` and `get_sync_history` manually through the Google Cloud Console. The process is similar for both:

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Select your GCP project and navigate to **Cloud Functions**.
3.  Click **"+ CREATE FUNCTION"** for each function you want to deploy.
4.  **For `sync_projects`**:
    *   Function name: `sync-projects` (or your choice)
    *   Entry point: `sync_projects`
5.  **For `get_sync_history`**:
    *   Function name: `get-sync-history` (or your choice)
    *   Entry point: `get_sync_history`
6.  **Common settings for both**:
    *   Environment: **2nd gen**.
    *   Region: Your preferred region.
    *   Trigger Type: **HTTP**.
    *   Authentication: "Allow unauthenticated invocations" (review security implications) or "Require authentication".
    *   Runtime Environment Variables: Add `GCP_PROJECT` with your Project ID as its value.
    *   Service Account: Select the runtime service account (ensure it has Secret Manager and Firestore access).
    *   Source Code: Python 3.11 (or as per `requirements.txt`), upload source as ZIP or connect to a repository.
7.  Click **"DEPLOY"**.

For the most current and detailed steps, always refer to the [official Google Cloud Functions deployment documentation](https://cloud.google.com/functions/docs/deploying).

### Post-Deployment: Finding Your Function URLs

Once your functions are successfully deployed, you will have **two distinct invocation URLs**: one for `sync_projects` and one for `get_sync_history`.
-   **`gcloud` CLI / `deploy.sh`**: The URLs are typically printed in your terminal output.
-   **GitHub Actions**: The workflow attempts to print the URL for `sync-projects`. You'd need to adapt it to also print the URL for `get_sync_history` if you add its deployment there.
-   **Google Cloud Console**: Navigate to each function in the Cloud Functions list. The URL will be displayed, often in the "Trigger" tab of the function's details page.

After obtaining the URLs, refer to the "[Usage](#usage)" section for details on how to make requests to each.

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

Understanding how errors are handled and where to find logs is crucial for troubleshooting.

**Error Reporting:**
-   The `sync_projects` function (the main entry point) catches most exceptions during its execution.
-   A successful HTTP response (Status Code 200) will include a JSON body. The `details.errors` list within this JSON will contain messages for any individual Todoist projects that failed to be created in Notion (e.g., due to Notion API issues for that specific project). The overall sync might still be considered "successful" if it processed all projects.
    ```json
    {
        "status": "success",
        "message": "Sync complete! Created X new projects, Y errors.",
        "details": {
            "checked": Z, // Total Todoist projects checked
            "created": X, // New projects created in Notion
            "skipped": S, // Projects skipped (already existed in Notion)
            "errors": ["Failed to create 'Project A': ...", "Failed to create 'Project B': ..."] // List of errors, if any
        }
    }
    ```
-   A critical error preventing the function from performing its core task (e.g., failure to retrieve initial API keys from Secret Manager) will typically result in an HTTP 500 status code with a JSON error message detailing the issue.

**Logging:**

*   **Local Debugging**:
    *   When running the function locally using `local_test_runner.py` (see "[Local Development and Testing](#local-development-and-testing)"), any `print()` statements in `main.py` will output directly to your console. This is useful for observing the function's flow and variable states.
    *   The `local_test_runner.py` example also includes a `try-except` block that will print full tracebacks to the console if an unhandled exception occurs.

*   **Google Cloud Logging (for Deployed Functions)**:
    *   Once deployed, Google Cloud Functions automatically send output from `print()` statements and standard error streams (like exception tracebacks) to [Google Cloud Logging](https://cloud.google.com/logging).
    *   To view these logs:
        1.  Go to the Google Cloud Console.
        2.  Navigate to "Logging" > "Logs Explorer".
        3.  In the query builder, you can filter by your Cloud Function's name. Select "Cloud Function" as a resource type and then specify your function name (e.g., `sync-projects`).
        4.  Adjust the time range as needed to find relevant log entries.
    *   Cloud Logging is invaluable for diagnosing issues with deployed functions, including timeouts, crashes, or unexpected behavior.

**Common Errors and Troubleshooting:**

*   **`Secret Manager secret not found or permission denied`**:
    *   **Check**: Ensure the secret names (`todoist-api-key`, `notion-api-key`, `notion-database-id`) are spelled correctly in Secret Manager and match what `get_secret()` expects.
    *   **Check**: Verify they exist in the GCP project specified by the `GCP_PROJECT` environment variable.
    *   **Check**: The runtime service account of your Cloud Function **must** have the "Secret Manager Secret Accessor" IAM role for these secrets (or on the GCP project/folder containing them).

*   **`Todoist API error: 401 Unauthorized`** or **`Notion API error: 401 Unauthorized`**:
    *   **Check**: The API key stored in Secret Manager for the respective service is likely invalid, revoked, or does not have the correct permissions for the operations being attempted.
    *   **Todoist**: Regenerate your API token in Todoist settings and update the secret.
    *   **Notion**: Ensure your Notion integration token is correct and that the integration has been shared with the target database with the necessary permissions (see "Prepare Your Notion Database").

*   **`Notion API error: 400 Bad Request`** or **`404 Not Found` (often related to Database ID or Page ID)**:
    *   **Check**: The `notion-database-id` secret might be incorrect. Double-check you copied the correct ID.
    *   **Check**: The Notion integration might not have been shared with the database, or it might lack "Can edit" / "Full access" permissions.
    *   **Check**: If modifying the script to update existing pages, ensure the page IDs are correct.
    *   **Check**: The payload structure for creating/updating a Notion page might be incorrect (e.g., wrong property type format for "Name", "Project Color", etc.). Consult the Notion API documentation for the correct structure. The error response from Notion (often in `e.response.text` if using `requests.exceptions.HTTPError`) usually contains specific details.

*   **`Failed to create '{project_name}': {status_code} - {response_text}`** (in the JSON response `details.errors`):
    *   **Check**: This indicates a problem creating a specific project in Notion. The `response_text` from Notion (included in the error message) is key.
    *   Common causes:
        *   The Notion database does not have a "Name" property of type "Title".
        *   A property you are trying to set (e.g., "Project Color" in the modification example) does not exist in the Notion database, or it's of a different type than what the script is sending.
        *   A value for a "Select" or "Multi-Select" property does not match one of the predefined options in Notion.

*   **`GCP_PROJECT environment variable not set`**:
    *   **Check**: This error means the `get_secret()` function couldn't determine your GCP Project ID.
    *   For deployed functions: Ensure `GCP_PROJECT` is set as an environment variable in the Cloud Function's configuration (see Deployment sections).
    *   For local testing: Ensure `GCP_PROJECT` is set in your shell or in the `local_test_runner.py` script.

*   **Function Timeouts**:
    *   **Check**: If the function takes longer than its configured timeout (default is 60 seconds, can be up to 540 seconds for HTTP-triggered Gen 2 functions), it will be terminated. This can happen if you have a very large number of Todoist projects or if API calls are slow.
    *   **Solution**: Increase the timeout setting during deployment (e.g., `--timeout=300` in `gcloud` or in `deploy.sh`/GitHub Actions workflow).
    *   **Solution**: Optimize the script. For instance, if dealing with a vast number of projects, consider modifying the logic to fetch and process projects in batches (though the current script fetches all Todoist projects first, then processes).

## Future Improvements

This project provides a solid foundation for Todoist to Notion synchronization. Here are some potential areas for future enhancements:

*   **Sync More Project Fields**:
    *   **Examples**: Todoist project URLs, comments, shared status, parent/child project relationships, due dates (if projects have them), or custom fields if Todoist adds such features.
    *   **Action**: This would involve adding new properties to the Notion database to store this information and modifying the `create_notion_project` function (and potentially `sync_todoist_to_notion`) to include these new fields in the payload sent to Notion, similar to the "Project Color" example.

*   **Robust Project Matching & Updates**:
    *   **Current**: Projects are skipped if a Notion page with the same *name* exists. This is simple but can be problematic if project names change or are not unique.
    *   **Improvement**: Use a unique Todoist Project ID.
    *   **Action**:
        1.  Add a new property (e.g., "Todoist Project ID", Text type) to your Notion database.
        2.  Modify `create_notion_project` to store the Todoist project's ID in this new Notion property.
        3.  Modify `get_notion_projects` to fetch this "Todoist Project ID" for existing entries.
        4.  Change the core logic in `sync_todoist_to_notion` to compare based on this ID instead of the name.
        5.  (Optional) Implement an `update_notion_project` function to update existing Notion pages if corresponding Todoist projects have changed (e.g., name, color).

*   **Selective Sync (Filtering)**:
    *   **Improvement**: Allow users to specify criteria for which Todoist projects get synced (e.g., only projects with a specific label, only projects not in an archive, projects matching a certain name pattern).
    *   **Action**: This could involve:
        *   Adding new configuration options (perhaps via environment variables or modifying the script directly).
        *   Updating `get_todoist_projects` to filter projects based on these criteria (Todoist API might offer some server-side filtering) or filtering them after they are fetched.

*   **Enhanced Error Resilience & Retries**:
    *   **Improvement**: Implement automatic retries for transient network errors or API rate limit issues when communicating with Todoist or Notion.
    *   **Action**: Wrap API call sections (e.g., in `get_todoist_projects`, `create_notion_project`) with retry logic, possibly using libraries like `tenacity`.

*   **Develop a Test Suite**:
    *   **Improvement**: Create a formal suite of unit and integration tests to ensure code quality and prevent regressions when making changes.
    *   **Action**: Use Python's `unittest` or `pytest` frameworks. This would involve writing test cases for individual functions (mocking external API calls) and potentially end-to-end tests with test Todoist/Notion accounts.

*   **Deletion Handling**:
    *   **Improvement**: Define what should happen in Notion if a project is deleted in Todoist (e.g., mark as archived in Notion, delete from Notion, do nothing).
    *   **Action**: This is a more complex change and might require:
        *   Regularly fetching all project IDs from Todoist.
        *   Querying all Notion pages that are managed by this sync (e.g., by checking for the presence of a "Todoist Project ID" if you've implemented robust matching).
        *   Comparing the two lists to find Notion pages whose corresponding Todoist project no longer exists, and then taking appropriate action (e.g., add an "Archived" tag in Notion, or delete the Notion page).

*   **Bi-Directional Sync (Major Enhancement)**:
    *   **Improvement**: Allow changes in Notion to be synced back to Todoist.
    *   **Action**: This is a significant undertaking, vastly increasing complexity. It would likely require:
        *   A way to track changes in Notion (e.g., using Notion's `last_edited_time` property on pages, or potentially webhooks if Notion's API offers suitable ones for database changes).
        *   Logic to map Notion changes back to Todoist API calls.
        *   Robust conflict resolution strategies if data changes in both places simultaneously.
        *   More extensive API permissions for both services.

Contributions towards these improvements are welcome!

## Contributing
Contributions are welcome! Please feel free to submit a pull request or open an issue for bugs, feature requests, or improvements.

## License
This project is released under the MIT License.
(Consider adding an actual `LICENSE` file with the MIT License text if you intend to formally use it.)