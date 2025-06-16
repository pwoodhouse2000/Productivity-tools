"""
Synchronizes projects from Todoist to a Notion database.

This script is designed as a Google Cloud Function, triggered via HTTP.
It fetches projects from a Todoist account and ensures corresponding pages
exist and are up-to-date in a specified Notion database.

Key Features:
- Retrieves Todoist projects using the Todoist REST API.
- Interacts with a Notion database using the Notion API.
- Securely accesses API keys (Todoist API Key, Notion API Key) and the
  Notion Database ID from Google Secret Manager.
- Creates new pages in Notion for Todoist projects not yet present.
- Updates existing Notion pages if the corresponding Todoist project's details
  (e.g., name, description generated from comment count) have changed.
- Uses a "Todoist ID" property in Notion to reliably map Todoist projects
  to Notion pages.
- Updates a "Last Synced" timestamp in Notion for each processed project.

The main entry point for the Cloud Function is `sync_projects`.
"""
import functions_framework
import json
import os
import requests
from google.cloud import secretmanager
from datetime import datetime, timezone
import traceback # For logging stack traces in unhandled exceptions

# --- Environment and Secret Configuration ---
# GCP_PROJECT is expected to be set in the Google Cloud Function environment.
GCP_PROJECT = os.environ.get('GCP_PROJECT')

# Secret IDs in Google Secret Manager
TODOIST_API_KEY_SECRET_ID = "todoist-api-key"
NOTION_API_KEY_SECRET_ID = "notion-api-key"
NOTION_DATABASE_ID_SECRET_ID = "notion-database-id"

# --- Notion API Configuration ---
NOTION_API_VERSION = "2022-06-28"  # Recommended version by Notion documentation

def get_secret(secret_id: str) -> str:
    """
    Retrieves a secret's value from Google Secret Manager.

    Args:
        secret_id: The ID of the secret in Secret Manager (e.g., "todoist-api-key").

    Returns:
        The secret value as a string.

    Raises:
        ValueError: If the GCP_PROJECT environment variable is not set.
        google.api_core.exceptions.GoogleAPIError: If there's an issue accessing
            the secret (e.g., permission denied, secret not found).
    """
    if not GCP_PROJECT:
        # This is a critical configuration error, as project ID is needed for secret path.
        raise ValueError("GCP_PROJECT environment variable not set.")

    client = secretmanager.SecretManagerServiceClient()
    # Construct the full secret version name
    secret_name = f"projects/{GCP_PROJECT}/secrets/{secret_id}/versions/latest"

    try:
        response = client.access_secret_version(request={"name": secret_name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        # Log the specific secret that failed for easier debugging
        print(f"Error accessing secret '{secret_id}' in project '{GCP_PROJECT}': {e}")
        raise # Re-raise the exception to be handled by the calling function or main handler

def get_todoist_api_key() -> str:
    """
    Retrieves the Todoist API key from Secret Manager.

    Returns:
        The Todoist API key as a string.

    Raises:
        (propagates exceptions from get_secret)
    """
    return get_secret(TODOIST_API_KEY_SECRET_ID)

def get_notion_credentials() -> tuple[str, str]:
    """
    Retrieves Notion API key and Database ID from Secret Manager.

    Returns:
        A tuple containing:
            - notion_api_key (str): The Notion API key.
            - notion_database_id (str): The ID of the Notion database.

    Raises:
        (propagates exceptions from get_secret)
    """
    api_key = get_secret(NOTION_API_KEY_SECRET_ID)
    database_id = get_secret(NOTION_DATABASE_ID_SECRET_ID)
    return api_key, database_id

def get_todoist_projects(api_key: str) -> list[dict]:
    """
    Fetches all projects from Todoist using the Todoist REST API.

    Args:
        api_key: The Todoist API key.

    Returns:
        A list of project dictionaries as returned by the Todoist API.
        Each dictionary represents a project and contains its properties.

    Raises:
        requests.exceptions.RequestException: If there's an issue with the
            API request (e.g., network error, non-2xx status code).
    """
    url = "https://api.todoist.com/rest/v2/projects"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
    return response.json()

# --- Notion Helper Functions ---

def query_notion_database(notion_api_key: str, notion_database_id: str, todoist_project_id_str: str) -> list[dict]:
    """
    Queries a Notion database to find pages with a specific "Todoist ID".

    Args:
        notion_api_key: The Notion API key.
        notion_database_id: The ID of the Notion database to query.
        todoist_project_id_str: The Todoist Project ID (as a string) to search for
                                in the "Todoist ID" property of Notion pages.

    Returns:
        A list of Notion page objects (dictionaries) that match the query.
        If no matching pages are found, an empty list is returned.

    Raises:
        requests.exceptions.RequestException: For network issues or API errors.
    """
    url = f"https://api.notion.com/v1/databases/{notion_database_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }
    # Construct the filter payload for querying by the "Todoist ID" property.
    # This assumes "Todoist ID" is a Rich Text property in Notion.
    query_filter = {
        "property": "Todoist ID", # Name of the Notion property
        "rich_text": {
            "equals": todoist_project_id_str
        }
    }
    response = requests.post(url, headers=headers, json={"filter": query_filter})
    response.raise_for_status()
    return response.json().get("results", []) # "results" key contains the list of pages

def create_notion_page(
    notion_api_key: str,
    notion_database_id: str,
    project_name: str,
    todoist_project_id_str: str,
    project_description: str = ""
) -> dict:
    """
    Creates a new page in the specified Notion database.

    Args:
        notion_api_key: The Notion API key.
        notion_database_id: The ID of the Notion database where the page will be created.
        project_name: The name of the project, to be used as the Notion page title.
        todoist_project_id_str: The Todoist Project ID (as a string) to store.
        project_description: A description for the project. Defaults to an empty string.
                             This will be stored in the "Description" property.

    Returns:
        A dictionary representing the newly created Notion page object.

    Raises:
        requests.exceptions.RequestException: For network issues or API errors.
    """
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }

    current_time_iso = datetime.now(timezone.utc).isoformat()

    # Define the properties for the new Notion page according to the database schema.
    # Ensure these property names and types match your Notion database setup.
    properties = {
        "Name": {"title": [{"text": {"content": project_name}}]},
        "Todoist ID": {"rich_text": [{"text": {"content": todoist_project_id_str}}]},
        "Source": {"select": {"name": "Todoist"}}, # Assumes a "Select" property named "Source" with an option "Todoist"
        "Last Synced": {"date": {"start": current_time_iso}},
        "Description": {"rich_text": [{"text": {"content": project_description or ""}}]} # Ensure description is not None
    }

    payload = {
        "parent": {"database_id": notion_database_id},
        "properties": properties,
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def update_notion_page(
    notion_api_key: str,
    page_id: str,
    project_name: str,
    project_description: str = ""
) -> dict:
    """
    Updates an existing page in Notion.

    Currently updates the "Name", "Description", and "Last Synced" properties.

    Args:
        notion_api_key: The Notion API key.
        page_id: The ID of the Notion page to update.
        project_name: The new name for the project.
        project_description: The new description for the project. Defaults to an empty string.

    Returns:
        A dictionary representing the updated Notion page object.

    Raises:
        requests.exceptions.RequestException: For network issues or API errors.
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }

    current_time_iso = datetime.now(timezone.utc).isoformat()

    # Define the properties to update.
    properties = {
        "Name": {"title": [{"text": {"content": project_name}}]},
        "Last Synced": {"date": {"start": current_time_iso}},
        "Description": {"rich_text": [{"text": {"content": project_description or ""}}]} # Ensure description is not None
    }

    payload = {"properties": properties}
    response = requests.patch(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

@functions_framework.http
def sync_projects(request: functions_framework. também_request) -> tuple[dict, int] | dict:
    """
    Main Google Cloud Function entry point for syncing Todoist projects to Notion.

    Triggered by an HTTP request. It fetches projects from Todoist,
    compares them with entries in a Notion database (matching by "Todoist ID"),
    and creates or updates Notion pages accordingly.

    Args:
        request: The HTTP request object provided by Google Cloud Functions.
                 This function does not use any data from the request body or query parameters.

    Returns:
        A tuple containing a JSON serializable dictionary and an HTTP status code,
        or just a JSON serializable dictionary (which defaults to 200 OK).
        The dictionary summarizes the sync operation, including counts of
        projects checked, created, updated, and any errors encountered.
        Example success response:
        {
            "status": "success",
            "message": "Sync complete! Checked: 10, Created: 2, Updated: 8. Encountered 0 error(s).",
            "details": {
                "checked": 10,
                "created": 2,
                "updated": 8,
                "skipped": 0, // Skipped is currently not used as items are either created or updated
                "errors": []
            }
        }
        Example error response (e.g., config error):
        {
            "status": "error",
            "message": "Server configuration error: GCP_PROJECT environment variable not set.",
            "details": { ... }
        }, 500
    """
    log_messages = [] # For accumulating log messages during the run
    status_counts = {"checked": 0, "created": 0, "updated": 0, "skipped": 0, "errors": 0}
    error_details = [] # For collecting specific error messages for individual projects

    try:
        # GCP_PROJECT is crucial for accessing secrets.
        if not GCP_PROJECT:
            log_messages.append("CRITICAL: GCP_PROJECT environment variable not set.")
            # This is a server configuration error, preventing secret access.
            return {
                "status": "error",
                "message": "Server configuration error: GCP_PROJECT environment variable not set.",
                "details": {"checked": 0, "created": 0, "updated": 0, "skipped": 0, "errors": 1, "error_details": ["GCP_PROJECT not set"]}
            }, 500 # Internal Server Error

        # Retrieve API keys and configuration from Secret Manager
        todoist_api_key = get_todoist_api_key()
        notion_api_key, notion_database_id = get_notion_credentials()
        
        # Fetch projects from Todoist
        todoist_projects = get_todoist_projects(todoist_api_key)
        log_messages.append(f"Fetched {len(todoist_projects)} projects from Todoist.")

        # Process each Todoist project
        for project in todoist_projects:
            status_counts["checked"] += 1
            project_id_str = str(project['id'])
            project_name = project['name']

            # Todoist API v2 for projects doesn't have a direct 'description' field.
            # We generate a description based on comment count and project ID,
            # as the README implies a "Description" field in Notion should be populated.
            # This can be customized if project comments themselves need to be fetched.
            comment_count = project.get("comment_count", 0)
            project_description_text = f"Contains {comment_count} comments. Todoist Project ID: {project_id_str}."

            try:
                # Check if this Todoist project already exists in Notion
                existing_pages = query_notion_database(notion_api_key, notion_database_id, project_id_str)

                if existing_pages:
                    # Project exists, update it
                    page_id = existing_pages[0]['id'] # Assuming the first result is the one

                    # Potentially, one could compare current_notion_name and current_notion_description
                    # with project_name and project_description_text to see if an update is truly needed,
                    # but for simplicity and to ensure "Last Synced" is always updated, we call update.
                    # current_notion_name = existing_pages[0]['properties']['Name']['title'][0]['text']['content']

                    update_notion_page(notion_api_key, page_id, project_name, project_description_text)
                    status_counts["updated"] += 1
                    log_messages.append(f"Updated Notion page for Todoist project: '{project_name}' (ID: {project_id_str})")
                else:
                    # Project does not exist, create it
                    create_notion_page(notion_api_key, notion_database_id, project_name, project_id_str, project_description_text)
                    status_counts["created"] += 1
                    log_messages.append(f"Created Notion page for Todoist project: '{project_name}' (ID: {project_id_str})")

            except requests.exceptions.RequestException as re:
                # Handle errors related to Notion API calls (e.g., network, specific API error codes)
                status_counts["errors"] += 1
                # Try to get status code from response, if available
                status_code_info = f" (Status: {re.response.status_code})" if re.response is not None else ""
                err_msg = f"API Error processing project '{project_name}' (ID: {project_id_str}){status_code_info}: {str(re)}"
                error_details.append(err_msg)
                log_messages.append(f"ERROR: {err_msg}")
            except Exception as e:
                # Handle other unexpected errors during individual project processing
                status_counts["errors"] += 1
                err_msg = f"Unexpected error processing project '{project_name}' (ID: {project_id_str}): {str(e)}"
                error_details.append(err_msg)
                log_messages.append(f"ERROR: {err_msg}")
                traceback.print_exc() # Log stack trace for unexpected errors
        
        final_message = (
            f"Sync complete! Checked: {status_counts['checked']}, "
            f"Created: {status_counts['created']}, Updated: {status_counts['updated']}. "
            # f"Skipped: {status_counts['skipped']}. " # Skipped is not currently used as items are either created or updated
            f"Encountered {status_counts['errors']} error(s)."
        )
        
        # Print all collected log messages (useful for Cloud Logging)
        for msg in log_messages:
            print(msg)
        if error_details:
            print("--- Error Details ---")
            for err in error_details:
                print(err)
            print("--- End Error Details ---")

        response_status = "success" if status_counts["errors"] == 0 else "partial_success"
        http_status_code = 200 # OK for both success and partial_success

        return {
            "status": response_status,
            "message": final_message,
            "details": {
                "checked": status_counts["checked"],
                "created": status_counts["created"],
                "updated": status_counts["updated"],
                "skipped": status_counts["skipped"], # Will be 0 with current logic
                "errors": error_details
            }
        }, http_status_code

    except ValueError as ve: # Handles GCP_PROJECT not set from get_secret
        err_msg = f"Configuration error: {str(ve)}"
        print(err_msg)
        return {
            "status": "error",
            "message": err_msg,
            "details": {"checked": 0, "created": 0, "updated": 0, "skipped": 0, "errors": 1, "error_details": [str(ve)]}
        }, 400 # Bad Request, as it's a client-side (configuration) error
    except requests.exceptions.RequestException as re:
        # Handles critical errors during initial API calls (e.g., fetching Todoist projects, initial secret retrieval)
        err_msg = f"A critical API error occurred: {str(re)}"
        print(err_msg)
        traceback.print_exc()
        status_counts["errors"] +=1
        return {
            "status": "error",
            "message": err_msg,
            "details": {**status_counts, "error_details": error_details + [f"Critical API error: {str(re)}"]}
        }, 500 # Internal Server Error
    except Exception as e:
        # Catch-all for any other unhandled exceptions in the main flow
        err_msg = f"An unexpected critical error occurred: {str(e)}"
        print(err_msg)
        traceback.print_exc() # Log the full stack trace for debugging

        status_counts["errors"] +=1
        return {
            "status": "error",
            "message": err_msg,
            "details": {**status_counts, "error_details": error_details + [f"Critical unhandled error: {str(e)}"]}
        }, 500 # Internal Server Error
