# Let's modify main.py to explore the data structure
import functions_framework
import json
import os
import requests
from google.cloud import secretmanager

# ... (keep existing functions) ...

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
