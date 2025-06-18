import functions_framework
import json
import os
import requests
from datetime import datetime
from google.cloud import secretmanager, firestore

# Initialize clients
secret_client = secretmanager.SecretManagerServiceClient()
db = firestore.Client()

def get_secret(secret_name):
    """Get secret from Secret Manager"""
    project_id = os.environ.get("GCP_PROJECT")
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def get_todoist_headers():
    """Get Todoist API headers"""
    api_key = get_secret("todoist-api-key")
    return {"Authorization": f"Bearer {api_key}"}

def get_notion_headers():
    """Get Notion API headers"""
    api_key = get_secret("notion-api-key")
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

def get_todoist_projects():
    """Fetch all projects from Todoist"""
    response = requests.get(
        "https://api.todoist.com/rest/v2/projects",
        headers=get_todoist_headers()
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Todoist API error: {response.status_code}")

def get_todoist_tasks():
    """Fetch all active tasks from Todoist"""
    response = requests.get(
        "https://api.todoist.com/rest/v2/tasks",
        headers=get_todoist_headers()
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Todoist API error: {response.status_code}")

def get_todoist_labels():
    """Fetch all labels from Todoist"""
    response = requests.get(
        "https://api.todoist.com/rest/v2/labels",
        headers=get_todoist_headers()
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Todoist API error: {response.status_code}")

def create_todoist_label(name):
    """Create a new label in Todoist"""
    response = requests.post(
        "https://api.todoist.com/rest/v2/labels",
        headers=get_todoist_headers(),
        json={"name": name}
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to create label: {response.status_code}")

def get_or_create_label(label_name, existing_labels):
    """Get existing label or create new one"""
    for label in existing_labels:
        if label["name"] == label_name:
            return label["id"]
    
    # Create new label
    new_label = create_todoist_label(label_name)
    return new_label["id"]

def get_notion_projects():
    """Get existing projects from Notion database"""
    database_id = get_secret("notion-database-id")
    headers = get_notion_headers()
    
    response = requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers=headers,
        json={}
    )
    
    if response.status_code == 200:
        return response.json()["results"]
    else:
        return []

def get_notion_tasks():
    """Get tasks from The List of Things database"""
    database_id = get_secret("notion-tasks-db-id")  # New secret needed
    headers = get_notion_headers()
    
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
    categories_db_id = get_secret("notion-categories-db-id")
    headers = get_notion_headers()
    
    try:
        response = requests.post(
            f"https://api.notion.com/v1/databases/{categories_db_id}/query",
            headers=headers,
            json={}
        )
        
        if response.status_code == 200:
            categories = {}
            for page in response.json()["results"]:
                # Try different common property names for the title
                title = None
                for prop_name in ["Name", "Title", "Category"]:
                    if prop_name in page["properties"]:
                        prop = page["properties"][prop_name]
                        if prop.get("title") and prop["title"]:
                            title = prop["title"][0]["text"]["content"]
                            break
                
                if title:
                    categories[title] = page["id"]
                    
            return categories
        else:
            return {}
    except Exception as e:
        print(f"Warning: Could not fetch categories: {str(e)}")
        return {}

def create_or_update_notion_project(project_data, existing_projects):
    """Create or update a project in Notion"""
    database_id = get_secret("notion-database-id")
    headers = get_notion_headers()
    category_map = get_notion_categories()
    
    # Check if project exists
    page_id = None
    for page in existing_projects:
        try:
            if "Name" in page["properties"] and page["properties"]["Name"]["title"]:
                if page["properties"]["Name"]["title"][0]["text"]["content"] == project_data["name"]:
                    page_id = page["id"]
                    break
        except:
            pass
    
    properties = {
        "Name": {
            "title": [{"text": {"content": project_data["name"]}}]
        },
        "Source": {
            "select": {"name": "Todoist"}
        },
        "Last Synced": {
            "date": {"start": datetime.now().isoformat()}
        }
    }
    
    # Add Todoist URL
    if "id" in project_data:
        properties["Todoist URL"] = {
            "url": f"https://todoist.com/app/project/{project_data['id']}"
        }
    
    # Add status
    if project_data.get("is_archived"):
        properties["Status"] = {"select": {"name": "Done"}}
    else:
        properties["Status"] = {"select": {"name": "In Progress"}}
    
    # Add category if it's a child project
    if "parent_id" in project_data and project_data["parent_id"]:
        # Find parent name
        todoist_projects = get_todoist_projects()
        parent_name = None
        for p in todoist_projects:
            if p["id"] == project_data["parent_id"]:
                parent_name = p["name"]
                break
        
        if parent_name and parent_name in category_map:
            properties["Category"] = {
                "relation": [{"id": category_map[parent_name]}]
            }
    
    if page_id:
        # Update existing
        response = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"properties": properties}
        )
    else:
        # Create new
        response = requests.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json={
                "parent": {"database_id": database_id},
                "properties": properties
            }
        )
    
    if response.status_code not in [200, 201]:
        raise Exception(f"Notion API error: {response.status_code} - {response.text}")
    
    return response.json()

def create_or_update_todoist_project(notion_project):
    """Create or update a project in Todoist based on Notion data"""
    headers = get_todoist_headers()
    
    # Extract project info from Notion
    project_name = notion_project["properties"]["Name"]["title"][0]["text"]["content"]
    
    # Check if it should be archived
    is_archived = False
    if "Status" in notion_project["properties"]:
        status = notion_project["properties"]["Status"].get("select", {})
        if status and status.get("name") in ["Done", "Canceled"]:
            is_archived = True
    
    # Get existing Todoist projects to check if it exists
    todoist_projects = get_todoist_projects()
    existing_project = None
    
    for p in todoist_projects:
        if p["name"] == project_name:
            existing_project = p
            break
    
    if existing_project:
        # Update existing project
        if existing_project["is_archived"] != is_archived:
            # Archive/unarchive project
            if is_archived:
                response = requests.post(
                    f"https://api.todoist.com/rest/v2/projects/{existing_project['id']}/archive",
                    headers=headers
                )
            else:
                response = requests.post(
                    f"https://api.todoist.com/rest/v2/projects/{existing_project['id']}/unarchive",
                    headers=headers
                )
        return existing_project["id"]
    else:
        # Create new project
        project_data = {"name": project_name}
        
        # Check for category/parent
        if "Category" in notion_project["properties"]:
            category_relation = notion_project["properties"]["Category"].get("relation", [])
            if category_relation:
                # Get category name
                category_id = category_relation[0]["id"]
                # Would need to look up category name and find corresponding Todoist project
                # For now, we'll skip parent assignment
        
        response = requests.post(
            "https://api.todoist.com/rest/v2/projects",
            headers=headers,
            json=project_data
        )
        
        if response.status_code == 200:
            new_project = response.json()
            if is_archived:
                # Archive the newly created project
                requests.post(
                    f"https://api.todoist.com/rest/v2/projects/{new_project['id']}/archive",
                    headers=headers
                )
            return new_project["id"]
        else:
            raise Exception(f"Failed to create Todoist project: {response.status_code}")

def create_or_update_notion_task(task_data, existing_tasks, project_map, label_map):
    """Create or update a task in Notion"""
    database_id = get_secret("notion-tasks-db-id")
    headers = get_notion_headers()
    
    # Check if task exists by Todoist ID stored in Firestore
    task_ref = db.collection('task_mappings').document(str(task_data["id"]))
    task_mapping = task_ref.get()
    
    page_id = None
    if task_mapping.exists:
        page_id = task_mapping.to_dict().get('notion_id')
    
    properties = {
        "Name": {
            "title": [{"text": {"content": task_data["content"]}}]
        },
        "Done": {
            "checkbox": task_data.get("is_completed", False)
        }
    }
    
    # Add due date if present
    if task_data.get("due"):
        properties["Due Date"] = {
            "date": {"start": task_data["due"]["date"]}
        }
    
    # Add project link if present
    if task_data.get("project_id") and task_data["project_id"] in project_map:
        properties["All Pete's Projects"] = {
            "relation": [{"id": project_map[task_data["project_id"]]}]
        }
    
    # Add label as Type if present
    if task_data.get("labels"):
        for label in task_data["labels"]:
            if label in label_map:
                properties["Type"] = {
                    "select": {"name": label_map[label]}
                }
                break
    
    if page_id:
        # Update existing
        response = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"properties": properties}
        )
    else:
        # Create new
        response = requests.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json={
                "parent": {"database_id": database_id},
                "properties": properties
            }
        )
        
        if response.status_code in [200, 201]:
            # Store mapping
            notion_id = response.json()["id"]
            task_ref.set({
                'todoist_id': task_data["id"],
                'notion_id': notion_id,
                'last_synced': datetime.now()
            })
    
    if response.status_code not in [200, 201]:
        raise Exception(f"Notion API error: {response.status_code} - {response.text}")
    
    return response.json()

def create_or_update_todoist_task(notion_task, project_map_reverse, existing_labels):
    """Create or update a task in Todoist based on Notion data"""
    headers = get_todoist_headers()
    
    # Extract task info from Notion
    task_name = notion_task["properties"]["Name"]["title"][0]["text"]["content"]
    is_done = notion_task["properties"].get("Done", {}).get("checkbox", False)
    
    # Check if task exists by Notion ID stored in Firestore
    task_mappings = db.collection('task_mappings').where('notion_id', '==', notion_task["id"]).stream()
    todoist_id = None
    
    for mapping in task_mappings:
        todoist_id = mapping.to_dict().get('todoist_id')
        break
    
    task_data = {
        "content": task_name,
        "is_completed": is_done
    }
    
    # Add due date if present
    if "Due Date" in notion_task["properties"] and notion_task["properties"]["Due Date"].get("date"):
        task_data["due_date"] = notion_task["properties"]["Due Date"]["date"]["start"]
    
    # Add project if linked
    if "All Pete's Projects" in notion_task["properties"]:
        project_relation = notion_task["properties"]["All Pete's Projects"].get("relation", [])
        if project_relation:
            notion_project_id = project_relation[0]["id"]
            if notion_project_id in project_map_reverse:
                task_data["project_id"] = project_map_reverse[notion_project_id]
    
    # Add label if Type is set
    if "Type" in notion_task["properties"] and notion_task["properties"]["Type"].get("select"):
        type_name = notion_task["properties"]["Type"]["select"]["name"]
        label_id = get_or_create_label(type_name, existing_labels)
        task_data["labels"] = [label_id]
    
    if todoist_id:
        # Update existing task
        response = requests.post(
            f"https://api.todoist.com/rest/v2/tasks/{todoist_id}",
            headers=headers,
            json=task_data
        )
        
        # Handle completion state
        if is_done and response.status_code == 200:
            requests.post(
                f"https://api.todoist.com/rest/v2/tasks/{todoist_id}/close",
                headers=headers
            )
    else:
        # Create new task
        response = requests.post(
            "https://api.todoist.com/rest/v2/tasks",
            headers=headers,
            json=task_data
        )
        
        if response.status_code == 200:
            new_task = response.json()
            # Store mapping
            db.collection('task_mappings').document(str(new_task["id"])).set({
                'todoist_id': new_task["id"],
                'notion_id': notion_task["id"],
                'last_synced': datetime.now()
            })
            
            # Close if done
            if is_done:
                requests.post(
                    f"https://api.todoist.com/rest/v2/tasks/{new_task['id']}/close",
                    headers=headers
                )
    
    if response.status_code != 200:
        raise Exception(f"Todoist API error: {response.status_code}")
# Replace your existing sync_all function with this one

def sync_all():
    """Main sync function for both projects and tasks"""
    print("✅ Sync function started.") # 1. START

    results = {
        "projects": {"created": 0, "updated": 0, "errors": []},
        "tasks": {"created": 0, "updated": 0, "errors": []},
        "timestamp": datetime.now().isoformat()
    }

    try:
        # Let's add logging around the very first API calls
        print("...Attempting to fetch Todoist projects...") # 2.
        todoist_projects = get_todoist_projects()
        print("✅ Successfully fetched Todoist projects.") # 3.

        print("...Attempting to fetch Notion projects...") # 4.
        notion_projects = get_notion_projects()
        print("✅ Successfully fetched Notion projects.") # 5.


        # Todoist → Notion
        print("...Starting sync from Todoist to Notion.")
        for project in todoist_projects:
            try:
                create_or_update_notion_project(project, notion_projects)
                results["projects"]["updated"] += 1
            except Exception as e:
                results["projects"]["errors"].append(f"Project '{project['name']}': {str(e)}")
        print("✅ Finished sync from Todoist to Notion.")

        # Notion → Todoist (for new projects or status changes)
        print("...Starting sync from Notion to Todoist.")
        for project in notion_projects:
            if "Source" not in project["properties"] or not project["properties"]["Source"].get("select"):
                # This is a new project created in Notion
                try:
                    create_or_update_todoist_project(project)
                    results["projects"]["created"] += 1
                except Exception as e:
                    project_name = project["properties"]["Name"]["title"][0]["text"]["content"]
                    results["projects"]["errors"].append(f"Project '{project_name}': {str(e)}")
        print("✅ Finished sync from Notion to Todoist.")


        # Create project ID maps for task sync
        project_map = {}  # Todoist ID → Notion ID
        project_map_reverse = {}  # Notion ID → Todoist ID

        print("...Refreshing project lists after sync.")
        todoist_projects = get_todoist_projects()
        notion_projects = get_notion_projects()

# REPLACE WITH THIS CORRECTED BLOCK
for np in notion_projects:
    if "Todoist URL" in np["properties"] and np["properties"]["Todoist URL"].get("url"):
        # Corrected "Todoist URL"
        url = np["properties"]["Todoist URL"]["url"] 
        todoist_id = str(url.split("/")[-1]) # Added str() for safety
        project_map[todoist_id] = np["id"]
        project_map_reverse[np["id"]] = todoist_id
        print("✅ Created project ID maps.")

        # Sync tasks
        print("...Fetching tasks and labels.")
        todoist_tasks = get_todoist_tasks()
        notion_tasks = get_notion_tasks()
        existing_labels = get_todoist_labels()
        print("✅ Fetched tasks and labels.")

        # Create label map
        label_map = {label["id"]: label["name"] for label in existing_labels}

        # Todoist → Notion
        for task in todoist_tasks:
            try:
                create_or_update_notion_task(task, notion_tasks, project_map, label_map)
                results["tasks"]["updated"] += 1
            except Exception as e:
                results["tasks"]["errors"].append(f"Task '{task['content']}': {str(e)}")

        # Notion → Todoist
        for task in notion_tasks:
            try:
                create_or_update_todoist_task(task, project_map_reverse, existing_labels)
                results["tasks"]["updated"] += 1
            except Exception as e:
                task_name = task["properties"]["Name"]["title"][0]["text"]["content"]
                results["tasks"]["errors"].append(f"Task '{task_name}': {str(e)}")
        
        print("✅ Task sync finished.")

    except Exception as e:
        print(f"❌ AN ERROR OCCURRED: {str(e)}") # This will catch any exceptions
        results["error"] = str(e)

    # Store sync history
    print("...Saving sync history to Firestore.")
    db.collection('sync_history').add(results)
    print("✅ Sync history saved. Function finished.")

    return results

@functions_framework.http
def sync_projects(request):
    """Main HTTP function entry point"""
    try:
        results = sync_all()
        
        # Build summary message
        message_parts = []
        
        if results["projects"]["created"] > 0:
            message_parts.append(f"Projects created: {results['projects']['created']}")
        if results["projects"]["updated"] > 0:
            message_parts.append(f"Projects updated: {results['projects']['updated']}")
        if results["tasks"]["created"] > 0:
            message_parts.append(f"Tasks created: {results['tasks']['created']}")
        if results["tasks"]["updated"] > 0:
            message_parts.append(f"Tasks updated: {results['tasks']['updated']}")
        
        if not message_parts:
            message_parts.append("No changes needed")
            
        message = f"Sync complete! {', '.join(message_parts)}."
        
        total_errors = len(results["projects"]["errors"]) + len(results["tasks"]["errors"])
        if total_errors > 0:
            message += f" Errors: {total_errors}."
        
        return {
            "status": "success",
            "message": message,
            "details": results
        }, 200, {'Access-Control-Allow-Origin': '*'}
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }, 500, {'Access-Control-Allow-Origin': '*'}

@functions_framework.http
def get_sync_history(request):
    """Get recent sync history"""
    try:
        # Get last 10 syncs
        history = []
        docs = db.collection('sync_history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).stream()
        
        for doc in docs:
            history.append(doc.to_dict())
        
        return {
            "status": "success",
            "history": history
        }, 200, {'Access-Control-Allow-Origin': '*'}
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }, 500, {'Access-Control-Allow-Origin': '*'}
