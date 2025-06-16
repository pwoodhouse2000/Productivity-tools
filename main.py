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

def create_notion_project(project_name):
    """Create a new project in Notion - simplified version"""
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
            }
        }
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
    todoist_projects = get_todoist_projects()
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
        
        if project_name in existing_names:
            results["skipped"] += 1
        else:
            try:
                create_notion_project(project_name)
                results["created"] += 1
            except Exception as e:
                results["errors"].append(f"Failed '{project_name}': {str(e)}")
    
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
