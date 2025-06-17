import functions_framework
import json
import os
import requests
from google.cloud import secretmanager

# Initialize Secret Manager client
secret_client = secretmanager.SecretManagerServiceClient()

def get_secret(secret_name):
    """Get secret from Secret Manager"""
    project_id = os.environ.get("GCP_PROJECT")
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def get_todoist_projects():
    """Fetch all projects from Todoist"""
    api_key = get_secret("todoist-api-key")
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    response = requests.get(
        "https://api.todoist.com/rest/v2/projects",
        headers=headers
    )
    
    if response.status_code == 200:
        projects = response.json()
        project_map = {project["id"]: project["name"] for project in projects}
        return projects, project_map
    else:
        # Log the error or handle it more gracefully
        print(f"Todoist API error: {response.status_code} - {response.text}")
        return [], {}

def get_notion_projects():
    """Get existing projects from Notion database"""
    api_key = get_secret("notion-api-key")
    database_id = get_secret("notion-database-id")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers=headers,
        json={}
    )
    
    if response.status_code == 200:
        return response.json()["results"]
    else:
        return []

def create_notion_project(project_name, category_name=None, source=None, last_synced=None, description=None):
    """
    Create a new project in Notion with additional fields: Source, Last Synced, and Description.
    - project_name: Name of the project (string)
    - category_name: Optional category (string)
    - source: Optional source of the project (string)
    - last_synced: Optional last synced date/time (string, ISO format recommended)
    - description: Optional description (string)
    """
    api_key = get_secret("notion-api-key")
    database_id = get_secret("notion-database-id")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Build the Notion properties dictionary
    properties = {
        "Name": {
            "title": [
                {"text": {"content": project_name}}
            ]
        }
    }
    if category_name:
        properties["Category"] = {"select": {"name": category_name}}
    if source:
        properties["Source"] = {"rich_text": [{"text": {"content": source}}]}
    if last_synced:
        properties["Last Synced"] = {"date": {"start": last_synced}}
    if description:
        properties["Description"] = {"rich_text": [{"text": {"content": description}}]}

    data = {
        "parent": {"database_id": database_id},
        "properties": properties
    }
    
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=data
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to create '{project_name}': {response.status_code} - {response.text}")
    
    return response.json()

def sync_todoist_to_notion():
    """Main sync logic"""
    todoist_projects, todoist_project_map = get_todoist_projects() # Adjusted to unpack two values
    notion_projects = get_notion_projects()
    
    existing_names = set()
    for page in notion_projects:
        try:
            if "Name" in page["properties"]:
                title_prop = page["properties"]["Name"].get("title", [])
                if title_prop:
                    existing_names.add(title_prop[0]["text"]["content"])
        except:
            pass
    
    results = {
        "checked": len(todoist_projects),
        "created": 0,
        "skipped": 0,
        "errors": []
    }
    
    for project in todoist_projects:
        project_name = project["name"]
        parent_id = project.get("parent_id") # Use .get() for safety
        category_name = None

        if parent_id:
            category_name = todoist_project_map.get(str(parent_id)) # Ensure parent_id is string if keys are strings

        if project_name in existing_names:
            results["skipped"] += 1
        else:
            try:
                # Set the new fields for Notion
                source = "Todoist"  # You can change this as needed
                from datetime import datetime
                last_synced = datetime.utcnow().isoformat()  # Current UTC time in ISO format
                description = project.get("description", "")  # Use Todoist description if available
                create_notion_project(
                    project_name,
                    category_name=category_name,
                    source=source,
                    last_synced=last_synced,
                    description=description
                )
                results["created"] += 1
            except Exception as e:
                results["errors"].append(f"Failed '{project_name}' (Category: {category_name}): {str(e)}")
    
    return results

@functions_framework.http
def sync_projects(request):
    """Main function entry point"""
    try:
        results = sync_todoist_to_notion()
        
        return {
            "status": "success",
            "message": f"Sync complete! Created {results['created']} new projects.",
            "details": results
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }, 500
