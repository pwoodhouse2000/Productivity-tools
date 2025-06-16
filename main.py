# Let's modify main.py to explore the data structure
import functions_framework
import json
import os
import requests
from google.cloud import secretmanager

def get_todoist_projects():
    """
    Fetches Todoist projects using the Todoist REST API.
    The API key is securely retrieved from Google Secret Manager.
    Returns a list of project dictionaries as returned by the API.
    """
    # Step 1: Set up the name of the secret in Google Secret Manager
    secret_name = "projects/YOUR_PROJECT_ID/secrets/TODOIST_API_KEY/versions/latest"  # <-- Replace YOUR_PROJECT_ID

    # Step 2: Create a Secret Manager client
    client = secretmanager.SecretManagerServiceClient()

    # Step 3: Access the secret version and get the API key
    response = client.access_secret_version(request={"name": secret_name})
    api_key = response.payload.data.decode("UTF-8")

    # Step 4: Set up the Todoist API endpoint and headers
    url = "https://api.todoist.com/rest/v2/projects"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    # Step 5: Make the GET request to Todoist API
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Raises an error for bad responses

    # Step 6: Parse and return the JSON response (list of projects)
    return response.json()

@functions_framework.http
def sync_projects(request):
    """Main function entry point"""
    try:
        # First, let's explore what Todoist gives us
        todoist_projects = get_todoist_projects()
        
        # Debug: Let's see the project structure
        project_info = []
        for project in todoist_projects[:3]:  # Just first 3 for testing
            project_info.append({
                'name': project['name'],
                'id': project['id'],
                'parent_id': project.get('parent_id'),
                'is_favorite': project.get('is_favorite'),
                'color': project.get('color'),
                'view_style': project.get('view_style'),
                # URL would be: https://todoist.com/app/project/{id}
                'todoist_url': f"https://todoist.com/app/project/{project['id']}"
            })
        
        return {
            "status": "success",
            "message": "Exploring Todoist project structure",
            "sample_projects": project_info,
            "total_projects": len(todoist_projects)
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }, 500
