"""
This module provides a Google Cloud Function to synchronize projects
from Todoist to a Notion database. It fetches projects from Todoist,
checks for their existence in Notion, and creates new ones if they
are not found.
"""
import functions_framework
import json
import os
import requests
from google.cloud import secretmanager
from datetime import datetime
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Secret Manager client
secret_client = secretmanager.SecretManagerServiceClient()

def get_secret(secret_name):
    """
    Retrieves a secret from Google Secret Manager.

    Args:
        secret_name (str): The name of the secret to retrieve.

    Returns:
        str: The secret string.

    Raises:
        Exception: If the secret retrieval fails (e.g., secret not found,
                   permission issues). The Google Cloud client library typically
                   handles specific exceptions and may raise a generic one.
    """
    logger.info(f"Attempting to retrieve secret: {secret_name}")
    project_id = os.environ.get("GCP_PROJECT")
    if not project_id:
        logger.error("GCP_PROJECT environment variable not set.")
        raise ValueError("GCP_PROJECT environment variable not set.")

    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    try:
        response = secret_client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")
        logger.info(f"Successfully retrieved secret: {secret_name}")
        return secret_value
    except Exception as e:
        logger.error(f"Failed to access secret {secret_name}: {e}", exc_info=True)
        raise  # Re-raise the exception after logging

def get_todoist_projects():
    """
    Fetches all projects from the Todoist API.

    It uses the 'todoist-api-key' secret stored in Google Secret Manager
    to authenticate with the Todoist API.

    Returns:
        list: A list of project objects from Todoist. Each object is a
              dictionary representing a project.

    Raises:
        Exception: If the API request to Todoist fails (e.g., network issue,
                   authentication error, non-200 status code).
    """
    logger.info("Fetching projects from Todoist API...")
    api_key = get_secret("todoist-api-key")
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.get(
            "https://api.todoist.com/rest/v2/projects",
            headers=headers
        )
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        projects = response.json()
        logger.info(f"Successfully fetched {len(projects)} projects from Todoist.")
        return projects
    except requests.exceptions.RequestException as e:
        logger.error(f"Todoist API request failed: {e}", exc_info=True)
        raise Exception(f"Todoist API error: {e}") # Re-raise as a generic exception for the caller
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching Todoist projects: {e}", exc_info=True)
        raise # Re-raise the original error


def get_notion_projects():
    """
    Fetches existing project pages from the specified Notion database.

    It uses the 'notion-api-key' and 'notion-database-id' secrets
    stored in Google Secret Manager for authentication and to identify
    the target database.

    Returns:
        list: A list of Notion page objects, where each object represents
              a project already in the database.

    Raises:
        Exception: If the API request to Notion fails (e.g., network issue,
                   authentication error, invalid database ID, non-200 status code).
    """
    logger.info("Fetching existing projects from Notion database...")
    api_key = get_secret("notion-api-key")
    database_id = get_secret("notion-database-id")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            headers=headers,
            json={}
        )
        response.raise_for_status() # Raises an HTTPError for bad responses
        projects = response.json()["results"]
        logger.info(f"Successfully fetched {len(projects)} projects/pages from Notion.")
        return projects
    except requests.exceptions.RequestException as e:
        logger.error(f"Notion API request failed: {e.response.status_code} - {e.response.text}", exc_info=True)
        raise Exception(f"Notion API error: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching Notion projects: {e}", exc_info=True)
        raise


def create_notion_project(project_name, todoist_project_id):
    """
    Creates a new page in the Notion database to represent a project.

    This function constructs a new Notion page with properties for the
    project's name, source (defaulted to "Todoist"), a description
    containing the Todoist project ID, the Todoist Project ID itself,
    and the last synced timestamp.
    It uses 'notion-api-key' and 'notion-database-id' secrets.

    Args:
        project_name (str): The name of the project to be created in Notion.
        todoist_project_id (str or int): The ID of the project from Todoist.

    Returns:
        dict: The Notion page object that was created.

    Raises:
        Exception: If the API request to Notion for creating the page fails
                   (e.g., network issue, authentication error, non-200 status code).
    """
    logger.info(f"Attempting to create Notion project: '{project_name}' (Todoist ID: {todoist_project_id})")
    api_key = get_secret("notion-api-key")
    database_id = get_secret("notion-database-id")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    data = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": project_name
                        }
                    }
                ]
            },
            "Source": {
                "select": {
                    "name": "Todoist"
                }
            },
            "Description": {
                "rich_text": [
                    {
                        "text": {
                            "content": f"Synced from Todoist (ID: {todoist_project_id})"
                        }
                    }
                ]
            },
            "Todoist ID": { # New property to store Todoist Project ID
                "rich_text": [
                    {
                        "text": {
                            "content": str(todoist_project_id)
                        }
                    }
                ]
            },
            "Last Synced": {
                "date": {
                    "start": datetime.now().isoformat()
                }
            }
        }
    }
    
    try:
        response = requests.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=data
        )
        response.raise_for_status() # Raises an HTTPError for bad responses
        created_page = response.json()
        logger.info(f"Successfully created Notion project: '{project_name}' (Notion Page ID: {created_page.get('id')})")
        return created_page
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to create Notion project '{project_name}': {e.response.status_code} - {e.response.text}", exc_info=True)
        raise Exception(f"Failed to create Notion project '{project_name}': {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while creating Notion project '{project_name}': {e}", exc_info=True)
        raise

def update_notion_project(page_id, project_name, todoist_project_id):
    """
    Updates an existing project page in the Notion database.

    This function updates the project's name, its description to reflect the update,
    and the 'Last Synced' timestamp. It uses the Notion Page ID to identify the
    page to update. It relies on 'notion-api-key'.

    Args:
        page_id (str): The ID of the Notion page to update.
        project_name (str): The new (or current) name of the project from Todoist.
        todoist_project_id (str or int): The ID of the project from Todoist.

    Returns:
        dict: The updated Notion page object.

    Raises:
        Exception: If the API request to Notion for updating the page fails.
    """
    logger.info(f"Attempting to update Notion project: '{project_name}' (Notion Page ID: {page_id}, Todoist ID: {todoist_project_id})")
    api_key = get_secret("notion-api-key")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    data = {
        "properties": {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": project_name
                        }
                    }
                ]
            },
            "Description": {
                "rich_text": [
                    {
                        "text": {
                            "content": f"Synced from Todoist (ID: {todoist_project_id}) - Updated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    }
                ]
            },
            "Last Synced": {
                "date": {
                    "start": datetime.now().isoformat()
                }
            }
            # Note: "Todoist ID" is not updated here as it's the key for matching.
        }
    }
    
    try:
        response = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        updated_page = response.json()
        logger.info(f"Successfully updated Notion project: '{project_name}' (Notion Page ID: {page_id})")
        return updated_page
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to update Notion project '{project_name}' (Page ID: {page_id}): {e.response.status_code} - {e.response.text}", exc_info=True)
        raise Exception(f"Failed to update Notion project '{project_name}': {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while updating Notion project '{project_name}' (Page ID: {page_id}): {e}", exc_info=True)
        raise

def sync_todoist_to_notion():
    """
    Main logic for synchronizing projects from Todoist to Notion.

    This function performs the following steps:
    1. Fetches all projects from Todoist.
    2. Fetches all existing project pages from the Notion database.
    3. Creates a mapping of Notion pages by their stored "Todoist ID".
    4. Iterates through Todoist projects:
        - If a Todoist project's ID is found in the Notion map, the corresponding Notion page is updated.
        - Otherwise, a new project page is created in Notion.
    5. Collects and returns statistics about the synchronization process (checked, created, updated, errors).

    Returns:
        dict: A dictionary containing the results of the sync operation.
    """
    logger.info("Starting Todoist to Notion synchronization process (with updates)...")
    try:
        todoist_projects = get_todoist_projects()
        notion_pages = get_notion_projects() # Renamed for clarity
    except Exception as e:
        logger.error(f"Failed to retrieve initial project data for sync: {e}", exc_info=True)
        raise

    # Create a map of Notion projects by their "Todoist ID" property
    notion_projects_by_todoist_id = {}
    for page in notion_pages:
        try:
            # Assuming "Todoist ID" is a Rich Text property
            todoist_id_property = page.get("properties", {}).get("Todoist ID", {}).get("rich_text", [])
            if todoist_id_property and isinstance(todoist_id_property, list) and len(todoist_id_property) > 0:
                # Extract text content from the first rich text item
                page_todoist_id = todoist_id_property[0].get("text", {}).get("content")
                if page_todoist_id:
                    # Store page ID and current name for potential comparison or logging
                    notion_projects_by_todoist_id[page_todoist_id] = {
                        "page_id": page["id"],
                        "name": page.get("properties", {}).get("Name", {}).get("title", [{}])[0].get("text", {}).get("content", "Unknown Name")
                    }
            else: # Handle cases where "Todoist ID" might be a "Text" type property (less likely based on create_project)
                # This part might need adjustment if "Todoist ID" is a simple Text (Number) property in Notion
                # For now, we primarily expect rich_text as defined in create_notion_project
                pass # logger.debug(f"Page {page.get('id')} has no 'Todoist ID' rich_text property or it's empty.")
        except Exception as e:
            logger.warning(f"Error parsing 'Todoist ID' for Notion page {page.get('id')}: {e}", exc_info=True)


    results = {
        "checked": 0,
        "created": 0,
        "updated": 0, # New counter for updated projects
        "skipped": 0, # Will likely be 0 with ID-based matching, unless other skip conditions are added
        "errors": []
    }

    for project in todoist_projects:
        results["checked"] += 1
        todoist_project_id_str = str(project["id"]) # Ensure string for dictionary key consistency
        project_name = project["name"]
        # project_description = ... # Define if syncing description, for now using default in create/update

        if todoist_project_id_str in notion_projects_by_todoist_id:
            # Project exists in Notion, update it
            notion_page_details = notion_projects_by_todoist_id[todoist_project_id_str]
            notion_page_id = notion_page_details["page_id"]
            logger.info(f"Project '{project_name}' (Todoist ID: {todoist_project_id_str}) found in Notion (Page ID: {notion_page_id}). Attempting update.")
            try:
                update_notion_project(notion_page_id, project_name, todoist_project_id_str)
                results["updated"] += 1
            except Exception as e:
                error_message = f"Failed to update project '{project_name}' (Todoist ID: {todoist_project_id_str}, Notion Page ID: {notion_page_id}): {str(e)}"
                logger.error(error_message, exc_info=True)
                results["errors"].append(error_message)
        else:
            # Project does not exist in Notion, create it
            logger.info(f"Project '{project_name}' (Todoist ID: {todoist_project_id_str}) not found in Notion. Attempting to create.")
            try:
                create_notion_project(project_name, todoist_project_id_str)
                results["created"] += 1
            except Exception as e:
                error_message = f"Failed to create project '{project_name}' (Todoist ID: {todoist_project_id_str}): {str(e)}"
                logger.error(error_message, exc_info=True)
                results["errors"].append(error_message)
    
    logger.info(f"Synchronization process completed. Checked: {results['checked']}, Created: {results['created']}, Updated: {results['updated']}, Errors: {len(results['errors'])}")
    if results["errors"]:
        logger.warning(f"Sync completed with errors: {results['errors']}")
    return results

@functions_framework.http
def sync_projects(request):
    """
    HTTP entry point for the Google Cloud Function.

    This function is triggered by an HTTP request. It orchestrates the
    Todoist to Notion synchronization process by calling `sync_todoist_to_notion()`.

    Args:
        request (flask.Request): The HTTP request object. While the current
                                 logic does not use specific data from the
                                 request object (e.g., query parameters or body),
                                 it's a standard parameter for HTTP-triggered
                                 Google Cloud Functions.

    Returns:
        tuple: A tuple containing a JSON response and an HTTP status code.
               On success, returns a JSON object with sync status and details,
               and a 200 status code (implicitly, as Flask/Functions Framework handles this).
               On error, returns a JSON object with an error message and a 500 status code.
    """
    logger.info("Google Cloud Function 'sync_projects' invoked.")
    try:
        results = sync_todoist_to_notion()
        
        message = (
            f"Sync complete! "
            f"Checked: {results['checked']}, "
            f"Created: {results['created']}, "
            f"Updated: {results['updated']}. "
            f"Skipped: {results['skipped']} (should be 0 with ID matching)." # Added skipped for completeness
        )
        if results['errors']:
            message += f" Encountered {len(results['errors'])} error(s)."

        response_data = {
            "status": "success" if not results['errors'] else "partial_success",
            "message": message,
            "details": results
        }
        
        if results['errors']:
            logger.warning(f"Sync process completed with some errors. Returning response: {response_data}")
        else:
            logger.info(f"Sync process successful. Returning response: {response_data}")

        return response_data, 200 # Return 200 even with partial success, errors are in the response body

    except Exception as e:
        logger.error(f"Critical error during sync_projects execution: {e}", exc_info=True)
        error_response = {
            "status": "error",
            "message": f"A critical error occurred: {str(e)}"
        }
        logger.error(f"Sync process failed critically. Returning error response: {error_response}")
        return error_response, 500
