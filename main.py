#
# CORRECTED AND CLEANED VERSION
#
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
    if not project_id:
        # Fallback for local development or if environment variable is not set
        project_id = 'productivity-sync-463008'

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
    response = requests.get("[https://api.todoist.com/rest/v2/projects](https://api.todoist.com/rest/v2/projects)", headers=get_todoist_headers())
    response.raise_for_status()
    return response.json()

def get_todoist_tasks():
    """Fetch all active tasks from Todoist"""
    response = requests.get("[https://api.todoist.com/rest/v2/tasks](https://api.todoist.com/rest/v2/tasks)", headers=get_todoist_headers())
    response.raise_for_status()
    return response.json()

def get_todoist_completed_tasks():
    """Fetch recently completed tasks from Todoist"""
    # Note: This requires Todoist Pro subscription
    try:
        response = requests.get("[https://api.todoist.com/rest/v2/completed/get_all](https://api.todoist.com/rest/v2/completed/get_all)", headers=get_todoist_headers())
        response.raise_for_status()
        return response.json().get("items", [])
    except:
        return []

def get_todoist_labels():
    """Fetch all labels from Todoist"""
    response = requests.get("[https://api.todoist.com/rest/v2/labels](https://api.todoist.com/rest/v2/labels)", headers=get_todoist_headers())
    response.raise_for_status()
    return response.json()

def create_todoist_label(name):
    """Create a new label in Todoist"""
    response = requests.post("[https://api.todoist.com/rest/v2/labels](https://api.todoist.com/rest/v2/labels)", headers=get_todoist_headers(), json={"name": name})
    response.raise_for_status()
    return response.json()

def get_or_create_label(label_name, existing_labels):
    """Get existing label or create new one"""
    for label in existing_labels:
        if label["name"] == label_name:
            return label["id"]
    new_label = create_todoist_label(label_name)
    return new_label["id"]

def get_notion_projects():
    """Get existing projects from Notion database"""
    database_id = get_secret("notion-database-id")
    headers = get_notion_headers()
    response = requests.post(f"[https://api.notion.com/v1/databases/](https://api.notion.com/v1/databases/){database_id}/query", headers=headers, json={})
    response.raise_for_status()
    return response.json()["results"]

def get_notion_tasks():
    """Get tasks from The List of Things database"""
    database_id = get_secret("notion-tasks-db-id")
    headers = get_notion_headers()
    response = requests.post(f"[https://api.notion.com/v1/databases/](https://api.notion.com/v1/databases/){database_id}/query", headers=headers, json={})
    response.raise_for_status()
    return response.json()["results"]

def get_notion_categories():
    """Get categories from Notion to map names to IDs"""
    try:
        categories_db_id = get_secret("notion-categories-db-id")
        headers = get_notion_headers()
        response = requests.post(f"[https://api.notion.com/v1/databases/](https://api.notion.com/v1/databases/){categories_db_id}/query", headers=headers, json={})
        response.raise_for_status()
        categories = {}
        for page in response.json()["results"]:
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
    except Exception as e:
        print(f"Warning: Could not fetch categories: {str(e)}")
        return {}

def create_or_update_notion_project(project_data, existing_projects, all_todoist_projects, category_map):
    """Create or update a project in Notion"""
    database_id = get_secret("notion-database-id")
    headers = get_notion_headers()
    page_id = None

    # Find existing project
    for page in existing_projects:
        try:
            if "Name" in page["properties"] and page["properties"]["Name"].get("title"):
                if page["properties"]["Name"]["title"][0]["text"]["content"] == project_data["name"]:
                    page_id = page["id"]
                    break
        except (KeyError, IndexError):
            pass

    properties = {
        "Name": {"title": [{"text": {"content": project_data["name"]}}]},
        "Source": {"select": {"name": "Todoist"}},
        "Last Synced": {"date": {"start": datetime.now().isoformat()}}
    }

    if "id" in project_data:
        properties["Todoist URL"] = {"url": f"[https://todoist.com/app/project/](https://todoist.com/app/project/){project_data['id']}"}
        properties["Todoist ID"] = {"rich_text": [{"text": {"content": str(project_data['id'])}}]}

    properties["Status"] = {"select": {"name": "Done" if project_data.get("is_archived") else "In Progress"}}

    if project_data.get("parent_id"):
        parent_name = next((p["name"] for p in all_todoist_projects if p["id"] == project_data["parent_id"]), None)
        if parent_name and parent_name in category_map:
            properties["Category"] = {"relation": [{"id": category_map[parent_name]}]}

    if page_id:
        response = requests.patch(f"[https://api.notion.com/v1/pages/](https://api.notion.com/v1/pages/){page_id}", headers=headers, json={"properties": properties})
    else:
        response = requests.post("[https://api.notion.com/v1/pages](https://api.notion.com/v1/pages)", headers=headers, json={"parent": {"database_id": database_id}, "properties": properties})

    response.raise_for_status()
    return response.json()

def create_or_update_todoist_project(notion_project, todoist_projects):
    """Create or update a project in Todoist based on Notion data"""
    headers = get_todoist_headers()
    project_name = notion_project["properties"]["Name"]["title"][0]["text"]["content"]
    status_name = notion_project["properties"].get("Status", {}).get("select", {}).get("name")
    is_archived = status_name in ["Done", "Canceled"]

    existing_project = next((p for p in todoist_projects if p["name"] == project_name), None)

    if existing_project:
        if existing_project["is_archived"] != is_archived:
            endpoint = "archive" if is_archived else "unarchive"
            requests.post(f"[https://api.todoist.com/rest/v2/projects/](https://api.todoist.com/rest/v2/projects/){existing_project['id']}/{endpoint}", headers=headers)
        return existing_project["id"]
    else:
        project_data = {"name": project_name}
        response = requests.post("[https://api.todoist.com/rest/v2/projects](https://api.todoist.com/rest/v2/projects)", headers=headers, json=project_data)
        response.raise_for_status()
        new_project = response.json()
        if is_archived:
            requests.post(f"[https://api.todoist.com/rest/v2/projects/](https://api.todoist.com/rest/v2/projects/){new_project['id']}/archive", headers=headers)
        return new_project["id"]

def create_or_update_notion_task(task_data, project_map, label_map, is_completed=False):
    """Create or update a task in Notion"""
    database_id = get_secret("notion-tasks-db-id")
    headers = get_notion_headers()

    # Get existing mapping
    task_ref = db.collection('task_mappings').document(str(task_data["id"]))
    task_mapping = task_ref.get()
    page_id = task_mapping.to_dict().get('notion_id') if task_mapping.exists else None

    properties = {
        "Name": {"title": [{"text": {"content": task_data["content"]}}]},
        "Done": {"checkbox": is_completed or task_data.get("is_completed", False)},
        "Todoist ID": {"rich_text": [{"text": {"content": str(task_data["id"])}}]},
        "Todoist URL": {"url": f"[https://todoist.com/app/task/](https://todoist.com/app/task/){task_data['id']}"}
    }

    if task_data.get("due"):
        properties["Due Date"] = {"date": {"start": task_data["due"]["date"]}}

    if task_data.get("project_id") in project_map:
        properties["All Pete's Projects"] = {"relation": [{"id": project_map[task_data["project_id"]]}]}

    if task_data.get("labels"):
        label_name = next((label_map[label_id] for label_id in task_data["labels"] if label_id in label_map), None)
        if label_name:
            properties["Type"] = {"select": {"name": label_name}}

    if page_id:
        # Update existing task
        response = requests.patch(f"[https://api.notion.com/v1/pages/](https://api.notion.com/v1/pages/){page_id}", headers=headers, json={"properties": properties})
    else:
        # Create new task
        response = requests.post("[https://api.notion.com/v1/pages](https://api.notion.com/v1/pages)", headers=headers, json={"parent": {"database_id": database_id}, "properties": properties})

    response.raise_for_status()
    result = response.json()

    # Update mapping
    if not page_id:
        notion_id = result["id"]
        task_ref.set({
            'todoist_id': str(task_data["id"]),
            'notion_id': notion_id,
            'last_synced': datetime.now(),
            'notion_url': result.get("url", "")
        })
    else:
        # Update sync timestamp
        task_ref.update({'last_synced': datetime.now()})

    return result

def create_or_update_todoist_task(notion_task, project_map_reverse, existing_labels):
    """Create or update a task in Todoist based on Notion data"""
    headers = get_todoist_headers()
    notion_id = notion_task["id"]
    task_name = notion_task["properties"]["Name"]["title"][0]["text"]["content"]
    is_done = notion_task["properties"].get("Done", {}).get("checkbox", False)

    # Get existing mapping
    task_mapping_query = db.collection('task_mappings').where('notion_id', '==', notion_id).limit(1).stream()
    mapping_doc = next(task_mapping_query, None)
    todoist_id = mapping_doc.to_dict().get('todoist_id') if mapping_doc else None

    # Check if task has Todoist ID in properties
    if not todoist_id:
        todoist_id_prop = notion_task["properties"].get("Todoist ID", {}).get("rich_text", [])
        if todoist_id_prop:
            todoist_id = todoist_id_prop[0]["text"]["content"]

    task_data = {"content": task_name}

    if "Due Date" in notion_task["properties"] and notion_task["properties"]["Due Date"].get("date"):
        task_data["due_date"] = notion_task["properties"]["Due Date"]["date"]["start"]

    if "All Pete's Projects" in notion_task["properties"]:
        relation = notion_task["properties"]["All Pete's Projects"].get("relation", [])
        if relation and relation[0]["id"] in project_map_reverse:
            task_data["project_id"] = project_map_reverse[relation[0]["id"]]

    if "Type" in notion_task["properties"] and notion_task["properties"]["Type"].get("select"):
        type_name = notion_task["properties"]["Type"]["select"]["name"]
        label_id = get_or_create_label(type_name, existing_labels)
        task_data["labels"] = [label_id]  # Fixed: use label_id instead of type_name

    if todoist_id:
        # Update existing task
        try:
            # First, check if the task exists in Todoist
            check_response = requests.get(f"[https://api.todoist.com/rest/v2/tasks/](https://api.todoist.com/rest/v2/tasks/){todoist_id}", headers=headers)

            if check_response.status_code == 200:
                # Task exists, update it
                response = requests.post(f"[https://api.todoist.com/rest/v2/tasks/](https://api.todoist.com/rest/v2/tasks/){todoist_id}", headers=headers, json=task_data)
                response.raise_for_status()

                # Handle completion status change
                todoist_task = check_response.json()
                todoist_is_completed = todoist_task.get("is_completed", False)

                if is_done and not todoist_is_completed:
                    # Mark as complete in Todoist
                    requests.post(f"[https://api.todoist.com/rest/v2/tasks/](https://api.todoist.com/rest/v2/tasks/){todoist_id}/close", headers=headers).raise_for_status()
                elif not is_done and todoist_is_completed:
                    # Reopen in Todoist
                    requests.post(f"[https://api.todoist.com/rest/v2/tasks/](https://api.todoist.com/rest/v2/tasks/){todoist_id}/reopen", headers=headers).raise_for_status()

                return response.json()
            else:
                # Task doesn't exist in Todoist anymore, create new
                todoist_id = None
        except requests.exceptions.HTTPError:
            # Task doesn't exist, will create new
            todoist_id = None

    if not todoist_id:
        # Create new task
        response = requests.post("[https://api.todoist.com/rest/v2/tasks](https://api.todoist.com/rest/v2/tasks)", headers=headers, json=task_data)
        response.raise_for_status()
        new_task = response.json()

        # Save mapping
        db.collection('task_mappings').document(str(new_task["id"])).set({
            'todoist_id': str(new_task["id"]),
            'notion_id': notion_id,
            'last_synced': datetime.now(),
            'notion_url': notion_task.get("url", "")
        })

        # If task is marked as done in Notion, complete it in Todoist
        if is_done:
            requests.post(f"[https://api.todoist.com/rest/v2/tasks/](https://api.todoist.com/rest/v2/tasks/){new_task['id']}/close", headers=headers).raise_for_status()

        return new_task

def sync_task_completion_status(todoist_tasks, notion_tasks, project_map, label_map):
    """Specifically sync completion status between platforms"""
    status_updates = {"todoist_to_notion": 0, "notion_to_todoist": 0}

    # Get completed tasks from Todoist
    completed_tasks = get_todoist_completed_tasks()
    completed_task_ids = {task["id"] for task in completed_tasks}

    # Create a map of Todoist IDs to completion status
    todoist_status_map = {}
    for task in todoist_tasks:
        todoist_status_map[task["id"]] = False  # Active tasks are not completed
    for task_id in completed_task_ids:
        todoist_status_map[task_id] = True  # Completed tasks

    # Check all task mappings for status mismatches
    mappings = db.collection('task_mappings').stream()

    for mapping in mappings:
        mapping_data = mapping.to_dict()
        todoist_id = mapping_data.get('todoist_id')
        notion_id = mapping_data.get('notion_id')

        if todoist_id and notion_id:
            # Get current status in Todoist
            todoist_is_completed = todoist_status_map.get(todoist_id, False)

            # Find the Notion task
            notion_task = next((t for t in notion_tasks if t["id"] == notion_id), None)

            if notion_task:
                notion_is_completed = notion_task["properties"].get("Done", {}).get("checkbox", False)

                # Update if status differs
                if todoist_is_completed != notion_is_completed:
                    if todoist_is_completed:
                        # Update Notion to mark as complete
                        headers = get_notion_headers()
                        update_data = {"properties": {"Done": {"checkbox": True}}}
                        requests.patch(f"[https://api.notion.com/v1/pages/](https://api.notion.com/v1/pages/){notion_id}", headers=headers, json=update_data)
                        status_updates["todoist_to_notion"] += 1
                    else:
                        # Task is incomplete in Todoist but complete in Notion
                        # This case is handled in create_or_update_todoist_task
                        pass

    return status_updates

def sync_all():
    """Main sync function"""
    print("✅ Sync function started.")
    results = {
        "projects": {"created": 0, "updated": 0, "errors": []},
        "tasks": {"created": 0, "updated": 0, "status_synced": 0, "errors": []},
        "timestamp": datetime.now().isoformat()
    }

    try:
        # Initial data fetch
        print("...Fetching initial data...")
        todoist_projects = get_todoist_projects()
        notion_projects = get_notion_projects()
        category_map = get_notion_categories()
        print("✅ Fetched initial data.")

        # Sync Projects: Todoist -> Notion
        print("...Syncing projects from Todoist to Notion...")
        for project in todoist_projects:
            try:
                result = create_or_update_notion_project(project, notion_projects, todoist_projects, category_map)
                if any(page["id"] == result["id"] for page in notion_projects):
                    results["projects"]["updated"] += 1
                else:
                    results["projects"]["created"] += 1
            except Exception as e:
                results["projects"]["errors"].append(f"T->N Project '{project['name']}': {str(e)}")

        # Sync Projects: Notion -> Todoist
        print("...Syncing projects from Notion to Todoist...")
        notion_projects_refreshed = get_notion_projects()
        for project in notion_projects_refreshed:
            # Only sync projects that don't have a source or aren't from Todoist
            source = project["properties"].get("Source", {}).get("select", {}).get("name")
            if not source or source != "Todoist":
                try:
                    create_or_update_todoist_project(project, todoist_projects)
                    results["projects"]["updated"] += 1
                except Exception as e:
                    project_name = project["properties"]["Name"]["title"][0]["text"]["content"]
                    results["projects"]["errors"].append(f"N->T Project '{project_name}': {str(e)}")

        # Create project ID maps
        print("...Creating project ID maps...")
        project_map, project_map_reverse = {}, {}
        final_notion_projects = get_notion_projects()
        for np in final_notion_projects:
            # Try to get Todoist ID from property first
            todoist_id_prop = np["properties"].get("Todoist ID", {}).get("rich_text", [])
            if todoist_id_prop:
                todoist_id = todoist_id_prop[0]["text"]["content"]
            else:
                # Fallback to URL parsing
                url_property = np["properties"].get("Todoist URL", {}).get("url")
                if url_property:
                    todoist_id = str(url_property.split("/")[-1])
                else:
                    continue

            project_map[todoist_id] = np["id"]
            project_map_reverse[np["id"]] = todoist_id
        print("✅ Created project ID maps.")

        # Sync Tasks
        print("...Fetching tasks and labels for sync...")
        todoist_tasks = get_todoist_tasks()
        notion_tasks = get_notion_tasks()
        existing_labels = get_todoist_labels()
        label_map = {label["id"]: label["name"] for label in existing_labels}
        print("✅ Fetched tasks and labels.")

        # First, sync completion status for existing tasks
        print("...Syncing task completion status...")
        status_results = sync_task_completion_status(todoist_tasks, notion_tasks, project_map, label_map)
        results["tasks"]["status_synced"] = status_results["todoist_to_notion"] + status_results["notion_to_todoist"]

        print("...Syncing tasks from Todoist to Notion...")
        # Track existing Notion task IDs
        existing_notion_task_ids = {task["id"] for task in notion_tasks}

        for task in todoist_tasks:
            try:
                result = create_or_update_notion_task(task, project_map, label_map)
                if result["id"] in existing_notion_task_ids:
                    results["tasks"]["updated"] += 1
                else:
                    results["tasks"]["created"] += 1
            except Exception as e:
                results["tasks"]["errors"].append(f"T->N Task '{task['content']}': {str(e)}")

        # Also sync completed tasks if available
        completed_tasks = get_todoist_completed_tasks()
        for task in completed_tasks[:50]:  # Limit to recent 50 completed tasks
            try:
                create_or_update_notion_task(task, project_map, label_map, is_completed=True)
            except Exception as e:
                results["tasks"]["errors"].append(f"T->N Completed Task '{task.get('content', 'Unknown')}': {str(e)}")

        print("...Syncing tasks from Notion to Todoist...")
        for task in notion_tasks:
            try:
                create_or_update_todoist_task(task, project_map_reverse, existing_labels)
                results["tasks"]["updated"] += 1
            except Exception as e:
                task_name = task["properties"]["Name"]["title"][0]["text"]["content"]
                results["tasks"]["errors"].append(f"N->T Task '{task_name}': {str(e)}")

        print("✅ Task sync finished.")

    except Exception as e:
        print(f"❌ A CRITICAL ERROR OCCURRED IN SYNC_ALL: {str(e)}")
        results["error"] = str(e)

    print("...Saving sync history to Firestore.")
    db.collection('sync_history').add(results)
    print("✅ Sync history saved. Function finished.")
    return results

@functions_framework.http
def sync_projects(request):
    """Main HTTP function entry point"""
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    cors_headers = {'Access-Control-Allow-Origin': '*'}
    try:
        results = sync_all()
        message_parts = []
        if results["projects"]["created"] > 0:
            message_parts.append(f"Projects created: {results['projects']['created']}")
        if results["projects"]["updated"] > 0:
            message_parts.append(f"Projects updated: {results['projects']['updated']}")
        if results["tasks"]["created"] > 0:
            message_parts.append(f"Tasks created: {results['tasks']['created']}")
        if results["tasks"]["updated"] > 0:
            message_parts.append(f"Tasks updated: {results['tasks']['updated']}")
        if results["tasks"]["status_synced"] > 0:
            message_parts.append(f"Task statuses synced: {results['tasks']['status_synced']}")
        if not message_parts:
            message_parts.append("No changes needed")

        message = f"Sync complete! {', '.join(message_parts)}."
        total_errors = len(results["projects"]["errors"]) + len(results["tasks"]["errors"])
        if total_errors > 0:
            message += f" Errors: {total_errors}."

        return ({"status": "success", "message": message, "details": results}, 200, cors_headers)
    except Exception as e:
        return ({"status": "error", "message": str(e)}, 500, cors_headers)

@functions_framework.http
def get_sync_history(request):
    """Get recent sync history"""
    if request.method == 'OPTIONS':
        headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET', 'Access-Control-Max-Age': '3600'}
        return ('', 204, headers)

    cors_headers = {'Access-Control-Allow-Origin': '*'}
    try:
        history = []
        docs = db.collection('sync_history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).stream()
        for doc in docs:
            history.append(doc.to_dict())
        return ({"status": "success", "history": history}, 200, cors_headers)
    except Exception as e:
        return ({"status": "error", "message": str(e)}, 500, cors_headers)

