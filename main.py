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
        return response.json()
    else:
        raise Exception(f"Todoist API error: {response.status_code}")

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

def get_notion_categories():
    """Get categories from Notion to map names to IDs"""
    api_key = get_secret("notion-api-key")
    categories_db_id = get_secret("notion-categories-db-id")  # You'll need to add this secret
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"https://api.notion.com/v1/databases/{categories_db_id}/query",
            headers=headers,
            json={}
        )
        
        if response.status_code == 200:
            categories = {}
            for page in response.json()["results"]:
                # Get the title of the category
                if "Name" in page["properties"] and page["properties"]["Name"]["title"]:
                    name = page["properties"]["Name"]["title"][0]["text"]["content"]
                    categories[name] = page["id"]
            return categories
        else:
            print(f"Warning: Could not fetch categories: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Warning: Could not fetch categories: {str(e)}")
        return {}

def create_notion_project(project_name, todoist_id=None, category_name=None, category_map=None):
    """Create a new project in Notion"""
    api_key = get_secret("notion-api-key")
    database_id = get_secret("notion-database-id")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    properties = {
        "Name": {
            "title": [{"text": {"content": project_name}}]
        },
        "Source": {
            "select": {"name": "Todoist"}
        }
    }
    
    # Add Todoist URL if we have the ID
    if todoist_id:
        properties["Todoist URL"] = {
            "url": f"https://todoist.com/app/project/{todoist_id}"
        }
    
    # Add category if we have it and it exists in our map
    if category_name and category_map and category_name in category_map:
        properties["Category"] = {
            "relation": [{"id": category_map[category_name]}]
        }
    
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

def update_notion_project(page_id, todoist_id=None, category_name=None, category_map=None):
    """Update an existing project in Notion"""
    api_key = get_secret("notion-api-key")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    properties = {
        "Source": {
            "select": {"name": "Todoist"}
        }
    }
    
    # Add Todoist URL if we have the ID
    if todoist_id:
        properties["Todoist URL"] = {
            "url": f"https://todoist.com/app/project/{todoist_id}"
        }
    
    # Add category if we have it and it exists in our map
    if category_name and category_map and category_name in category_map:
        properties["Category"] = {
            "relation": [{"id": category_map[category_name]}]
        }
    
    data = {"properties": properties}
    
    response = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=headers,
        json=data
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to update Notion page '{page_id}': {response.status_code} - {response.text}")
    
    return response.json()

def sync_todoist_to_notion():
    """Main sync logic"""
    # Get all projects from both systems
    todoist_projects = get_todoist_projects()
    notion_projects = get_notion_projects()
    
    # Get category mappings
    category_map = get_notion_categories()
    
    # Create a map of Todoist project IDs to their parent names
    project_parent_map = {}
    todoist_project_map = {p["id"]: p["name"] for p in todoist_projects}
    
    for project in todoist_projects:
        if project.get("parent_id") and project["parent_id"] in todoist_project_map:
            project_parent_map[project["id"]] = todoist_project_map[project["parent_id"]]
    
    # Build a map of existing Notion projects
    existing_projects = {}
    for page in notion_projects:
        try:
            if "Name" in page["properties"] and page["properties"]["Name"]["title"]:
                name = page["properties"]["Name"]["title"][0]["text"]["content"]
                existing_projects[name] = page["id"]
        except:
            pass
    
    results = {
        "checked": len(todoist_projects),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": []
    }
    
    for project in todoist_projects:
        project_name = project["name"]
        project_id = project["id"]
        category_name = project_parent_map.get(project_id)
        
        try:
            if project_name in existing_projects:
                # Update existing project
                try:
                    update_notion_project(
                        page_id=existing_projects[project_name],
                        todoist_id=project_id,
                        category_name=category_name,
                        category_map=category_map
                    )
                    results["updated"] += 1
                except Exception as e:
                    results["errors"].append(f"Failed to update '{project_name}': {str(e)}")
            else:
                # Create new project
                create_notion_project(
                    project_name=project_name,
                    todoist_id=project_id,
                    category_name=category_name,
                    category_map=category_map
                )
                results["created"] += 1
        except Exception as e:
            results["errors"].append(f"Failed to sync '{project_name}': {str(e)}")
    
    return results

@functions_framework.http
def sync_projects(request):
    """Main function entry point"""
    try:
        results = sync_todoist_to_notion()
        
        # Build summary message
        message_parts = []
        if results["created"] > 0:
            message_parts.append(f"Created: {results['created']}")
        if results["updated"] > 0:
            message_parts.append(f"Updated: {results['updated']}")
        if results["skipped"] > 0:
            message_parts.append(f"Skipped: {results['skipped']}")
        
        if not message_parts:
            message_parts.append("No changes needed")
            
        message = f"Sync complete! {', '.join(message_parts)}."
        
        if results["errors"]:
            message += f" Errors: {len(results['errors'])}."
        
        return {
            "status": "success",
            "message": message,
            "details": results
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }, 500
