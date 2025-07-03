import functions_framework
import os
import requests # Using requests for the REST API call
from google.cloud import secretmanager
from notion_client import Client
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Project

# --- Configuration ---
PROJECT_ID = "notion-todoist-sync-464419"
NOTION_PROJECTS_DB_ID = "21d89c4a21dd805d971eef334fea9640"
NOTION_TASKS_DB_ID = "21d89c4a21dd80f0a679e685cc7a3496"
NOTION_SECRET_NAME = "notion-api-key"
TODOIST_SECRET_NAME = "todoist-api-key"
ACTIVE_NOTION_STATUSES = {"Planning", "In Progress", "Ongoing"}

# --- Helper Functions ---

def get_secret(secret_name, version="latest"):
    """Retrieves a secret from Google Secret Manager."""
    print(f"Attempting to retrieve secret: {secret_name}")
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/{version}"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        return payload
    except Exception as e:
        print(f"Error retrieving secret {secret_name}: {e}")
        return None

def get_notion_projects(notion_client):
    """Fetches ALL projects from the Notion database using pagination and sorts them."""
    print(f"Querying Notion database to get all projects: {NOTION_PROJECTS_DB_ID}")
    projects_by_todoist_id = {}
    new_projects_in_notion = []
    next_cursor = None
    
    while True:
        try:
            response = notion_client.databases.query(database_id=NOTION_PROJECTS_DB_ID, start_cursor=next_cursor)
            for page in response.get("results", []):
                try:
                    todoist_id_prop = page.get("properties", {}).get("Todoist ID", {})
                    if todoist_id_prop.get('rich_text'):
                        todoist_id = todoist_id_prop['rich_text'][0]['plain_text']
                        projects_by_todoist_id[todoist_id] = page
                    else:
                        new_projects_in_notion.append(page)
                except (KeyError, IndexError) as e:
                    print(f"Could not parse a Notion project: {e}")
            
            if response.get("has_more"):
                next_cursor = response.get("next_cursor")
            else:
                break
        except Exception as e:
            print(f"An error occurred while querying Notion projects: {e}")
            return None, None
            
    print(f"Found {len(projects_by_todoist_id)} projects linked to Todoist.")
    print(f"Found {len(new_projects_in_notion)} new projects in Notion.")
    return projects_by_todoist_id, new_projects_in_notion

def get_todoist_projects(todoist_client):
    """Fetches all non-archived projects from Todoist."""
    print("Querying Todoist for projects.")
    try:
        projects = list(todoist_client.get_projects())
        print(f"Found {len(projects)} projects in Todoist.")
        return projects
    except Exception as e:
        print(f"An error occurred while querying Todoist projects: {e}")
        return None

def create_notion_project(notion_client, todoist_project):
    """Creates a new project page in Notion from a Todoist project."""
    print(f"Attempting to create Notion page for Todoist project: '{todoist_project.name}'")
    try:
        new_page_properties = {
            "Name": {"title": [{"text": {"content": todoist_project.name}}]},
            "Status": {"select": {"name": "Planning"}},
            "Source": {"select": {"name": "Todoist"}},
            "Todoist ID": {"rich_text": [{"text": {"content": todoist_project.id}}]},
            "Todoist URL": {"url": todoist_project.url}
        }
        response = notion_client.pages.create(
            parent={"database_id": NOTION_PROJECTS_DB_ID},
            properties=new_page_properties
        )
        print(f"Successfully created Notion page with ID: {response['id']}")
        return response
    except Exception as e:
        print(f"Failed to create Notion page for '{todoist_project.name}': {e}")
        return None

def create_todoist_project(todoist_client, notion_page):
    """Creates a new project in Todoist from a Notion page."""
    try:
        project_name = notion_page['properties']['Name']['title'][0]['plain_text']
        print(f"Attempting to create Todoist project for Notion page: '{project_name}'")
        project = todoist_client.add_project(name=project_name)
        print(f"Successfully created Todoist project with ID: {project.id}")
        return project
    except Exception as e:
        print(f"Failed to create Todoist project: {e}")
        return None

def update_notion_page_with_todoist_info(notion_client, notion_page_id, todoist_project):
    """Updates the Notion page with the new Todoist project's ID and URL."""
    print(f"Attempting to update Notion page {notion_page_id} with Todoist info.")
    try:
        properties_to_update = {
            "Todoist ID": {"rich_text": [{"text": {"content": todoist_project.id}}]},
            "Todoist URL": {"url": todoist_project.url}
        }
        notion_client.pages.update(
            page_id=notion_page_id,
            properties=properties_to_update
        )
        print(f"Successfully updated Notion page {notion_page_id}.")
    except Exception as e:
        print(f"Failed to update Notion page {notion_page_id}: {e}")

def archive_todoist_project(todoist_api_key, project_id):
    """Archives a project in Todoist using the REST API."""
    print(f"Attempting to archive Todoist project with ID: {project_id} using REST API.")
    try:
        headers = {"Authorization": f"Bearer {todoist_api_key}"}
        url = f"https://api.todoist.com/rest/v2/projects/{project_id}/archive"
        # The REST API uses POST to archive
        response = requests.post(url, headers=headers)
        
        # A successful archive returns a 204 No Content status
        if response.status_code == 204:
            print(f"Successfully archived Todoist project {project_id}.")
            return True
        else:
            print(f"[ERROR] Failed to archive Todoist project {project_id}. Status: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"An exception occurred while archiving Todoist project {project_id}: {e}")
        return False

# --- Main Sync Logic ---

def run_full_sync():
    """Orchestrates the entire sync process."""
    print("Running the main sync logic...")
    
    # 1. Get secrets
    notion_api_key = get_secret(NOTION_SECRET_NAME)
    todoist_api_key = get_secret(TODOIST_SECRET_NAME)
    if not notion_api_key or not todoist_api_key:
        raise Exception("Could not retrieve API keys.")

    # 2. Initialize clients
    notion = Client(auth=notion_api_key)
    todoist = TodoistAPI(todoist_api_key)

    # 3. Fetch data
    notion_projects_by_id, new_notion_projects = get_notion_projects(notion)
    todoist_projects = get_todoist_projects(todoist)
    if notion_projects_by_id is None or todoist_projects is None:
        raise Exception("Failed to fetch data from Notion or Todoist.")

    # 4. Perform sync logic
    print("\n--- Starting Project Sync ---")
    
    flat_todoist_projects = []
    if todoist_projects:
        # Handle the nested list issue safely
        source_list = todoist_projects[0] if isinstance(todoist_projects[0], list) else todoist_projects
        for item in source_list:
            if isinstance(item, Project): 
                flat_todoist_projects.append(item)

    # Part 1: Todoist -> Notion
    todoist_project_names = {p.name for p in flat_todoist_projects}
    for project in flat_todoist_projects:
        if project.id not in notion_projects_by_id:
            print(f"[ACTION] Todoist project '{project.name}' needs to be created in Notion.")
            create_notion_project(notion, project)

    # Part 2: Notion -> Todoist
    print("\n--- Checking for new projects in Notion ---")
    for page in new_projects_in_notion:
        try:
            project_name = page['properties']['Name']['title'][0]['plain_text']
            if project_name in todoist_project_names:
                print(f"[SKIP] Project '{project_name}' already exists in Todoist. Skipping.")
                continue
            new_todoist_project = create_todoist_project(todoist, page)
            if new_todoist_project:
                update_notion_page_with_todoist_info(notion, page['id'], new_todoist_project)
        except (KeyError, IndexError):
            print("[ERROR] Could not read name from a new Notion project page.")

    # Part 3: Archive projects
    print("\n--- Checking for projects to archive ---")
    for todoist_id, notion_page in notion_projects_by_id.items():
        try:
            status = notion_page['properties']['Status']['select']['name']
            if status not in ACTIVE_NOTION_STATUSES:
                project_name = notion_page['properties']['Name']['title'][0]['plain_text']
                print(f"[ACTION] Notion project '{project_name}' has status '{status}'. Archiving in Todoist.")
                archive_todoist_project(todoist_api_key, todoist_id) # Pass the key here
        except (KeyError, IndexError):
            print(f"[ERROR] Could not read status or name from Notion page with Todoist ID: {todoist_id}")

    print("--- Project Sync Check Complete ---")
    return {"message": "Sync logic executed."}


# --- Cloud Function Entry Point ---

@functions_framework.http
def sync_projects(_):
    """Cloud Function entry point. Triggers a full sync."""
    try:
        print("Sync function triggered.")
        results = run_full_sync()
        print(f"Sync function completed successfully. Results: {results}")
        return {"status": "success", "message": "Sync completed.", "details": results}
    except Exception as e:
        print(f"Sync function failed with error: {e}")
        return {"status": "error", "message": str(e)}, 500
