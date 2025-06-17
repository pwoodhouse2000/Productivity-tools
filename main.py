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
        results = response.json()["results"]
        projects_dict = {}
        for page in results:
            try:
                # Skip page if 'Name' property or its title component is missing
                if "Name" not in page["properties"] or not page["properties"]["Name"].get("title"):
                    continue

                project_name = page["properties"]["Name"]["title"][0]["text"]["content"]

                # Skip page if project_name is empty or None
                if not project_name:
                    continue

                properties_data = {}

                # Extract Category (select property)
                category_prop = page["properties"].get("Category")
                if category_prop and category_prop.get("select"):
                    properties_data["Category"] = category_prop["select"]["name"]
                else:
                    properties_data["Category"] = None

                # Extract Source (rich_text property)
                source_prop = page["properties"].get("Source")
                if source_prop and source_prop.get("rich_text"):
                    properties_data["Source"] = source_prop["rich_text"][0]["text"]["content"] if source_prop["rich_text"] else None
                else:
                    properties_data["Source"] = None

                # Extract Last Synced (date property)
                last_synced_prop = page["properties"].get("Last Synced")
                if last_synced_prop and last_synced_prop.get("date"):
                    properties_data["Last Synced"] = last_synced_prop["date"]["start"]
                else:
                    properties_data["Last Synced"] = None

                # Extract Description (rich_text property)
                description_prop = page["properties"].get("Description")
                if description_prop and description_prop.get("rich_text"):
                    properties_data["Description"] = description_prop["rich_text"][0]["text"]["content"] if description_prop["rich_text"] else None
                else:
                    properties_data["Description"] = None

                projects_dict[project_name] = {
                    "id": page["id"],
                    "properties": properties_data
                }
            except (KeyError, IndexError, TypeError) as e:
                # Log or handle pages with unexpected structure
                print(f"Skipping page due to error: {e}")
                continue
        return projects_dict
    else:
        # Log the error or handle it more gracefully
        print(f"Notion API error: {response.status_code} - {response.text}")
        return {}

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

def update_notion_project_details(page_id, properties_to_update):
    """
    Update an existing project in Notion with new details.
    - page_id: ID of the Notion page to update (string)
    - properties_to_update: Dictionary of properties to update, e.g., {'Category': 'New Category'}
    """
    api_key = get_secret("notion-api-key")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    # Format properties for Notion API
    notion_properties = {}
    if "Category" in properties_to_update:
        if properties_to_update["Category"] is None:
            notion_properties["Category"] = {"select": None} # Send null to clear
        else:
            notion_properties["Category"] = {"select": {"name": properties_to_update["Category"]}}
    if "Source" in properties_to_update:
        # Ensure Source is not None before creating rich_text structure
        if properties_to_update["Source"] is not None:
            notion_properties["Source"] = {"rich_text": [{"text": {"content": properties_to_update["Source"]}}]}
        else: # If Source is None, treat as empty text. Or API might require specific null structure for rich_text.
              # For simplicity, sending empty text if None. Or, could skip if None.
            notion_properties["Source"] = {"rich_text": [{"text": {"content": ""}}]}
    if "Last Synced" in properties_to_update:
        # Ensure Last Synced is not None before creating date structure
        if properties_to_update["Last Synced"] is not None:
            notion_properties["Last Synced"] = {"date": {"start": properties_to_update["Last Synced"]}}
        else: # API might require "date": null to clear. For now, skipping if None.
            pass # Or handle clearing explicitly if needed
    if "Description" in properties_to_update:
        # Ensure Description is not None
        if properties_to_update["Description"] is not None:
            notion_properties["Description"] = {"rich_text": [{"text": {"content": properties_to_update["Description"]}}]}
        else: # If Description is None, treat as empty text.
            notion_properties["Description"] = {"rich_text": [{"text": {"content": ""}}]}
    # Add other properties as needed, following their specific Notion structure

    # Only proceed if there are properties to update after potential None filtering
    if not notion_properties:
        # This check might be redundant if Source and Last Synced are always included
        # and guaranteed to be non-null by the caller (`sync_todoist_to_notion`)
        return {"message": "No valid properties provided to update."}

    data = {
        "properties": notion_properties
    }

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
    from datetime import datetime # Ensure datetime is imported
    todoist_projects, todoist_project_map = get_todoist_projects()
    notion_projects_data = get_notion_projects() # This is the dictionary
    
    results = {
        "checked": len(todoist_projects),
        "created": 0,
        "skipped": 0,
        "updated": 0, # New counter
        "errors": []
    }
    
    for project in todoist_projects:
        project_name = project["name"]
        parent_id = project.get("parent_id")
        description_from_todoist = project.get("description", "") # Use a distinct variable name

        category_name = None
        if parent_id:
            category_name = todoist_project_map.get(str(parent_id))

        source = "Todoist"
        last_synced = datetime.utcnow().isoformat()

        if project_name in notion_projects_data:
            # Project exists, check for updates
            notion_page_id = notion_projects_data[project_name]['id']
            current_notion_properties = notion_projects_data[project_name]['properties']
            properties_to_update = {}

            # Compare Category
            # Update if category_name from Todoist is different from Notion's current category
            # or if category_name is provided and Notion has no category
            # or if category_name is None and Notion has a category (to clear it)
            current_category = current_notion_properties.get('Category')
            if category_name != current_category:
                 # This also handles category_name being None and current_category having a value,
                 # effectively clearing it. And category_name having a value and current_category being None.
                properties_to_update['Category'] = category_name

            # Compare Description
            current_description = current_notion_properties.get('Description')
            if description_from_todoist != current_description:
                properties_to_update['Description'] = description_from_todoist

            # Always update Source and Last Synced for existing projects being processed
            properties_to_update['Source'] = source
            properties_to_update['Last Synced'] = last_synced

            if properties_to_update:
                # Remove None values from Category before sending to Notion if we want to clear it
                # The update_notion_project_details function needs to handle None for "select" appropriately
                # For now, we assume if 'Category' is in properties_to_update with value None,
                # the update function should attempt to clear it.
                # However, Notion API for select might require {"select": null} or specific handling.
                # The current `update_notion_project_details` for a select property expects a name.
                # If category_name is None, we should skip adding it to properties_to_update
                # unless we specifically want to clear it.
                # Let's adjust: only set Category if category_name is not None.
                # Clearing a select property often means setting it to `None` or an empty value,
                # which might need special handling in `update_notion_project_details`.
                # For now, if category_name is None, we won't add it to properties_to_update,
                # meaning it won't be explicitly cleared if it was already set.
                # This simplifies the logic based on current `update_notion_project_details`.
                # A more robust solution would involve `update_notion_project_details`
                # understanding how to clear a select property (e.g. by passing `{"select": null}`).

                final_properties_to_update = {}
                if properties_to_update.get('Category') is not None:
                    final_properties_to_update['Category'] = properties_to_update['Category']
                elif current_category is not None and category_name is None: # Explicitly clear if it was set
                     final_properties_to_update['Category'] = None # This signals to clear

                if 'Description' in properties_to_update:
                    final_properties_to_update['Description'] = properties_to_update['Description']

                final_properties_to_update['Source'] = source # Always update
                final_properties_to_update['Last Synced'] = last_synced # Always update

                # Check again if there's anything to update after category None handling
                # The only things that could make it empty now are if only Category was None and it was already None
                # or if only Category was None and it was previously set (now it will be sent as None)
                # The always-updated Source and Last Synced mean it will rarely be empty.

                try:
                    update_notion_project_details(notion_page_id, final_properties_to_update)
                    results['updated'] += 1
                except Exception as e:
                    results['errors'].append(f"Failed to update '{project_name}': {str(e)}")
            else:
                results['skipped'] += 1
        else:
            # Project does not exist, create it
            try:
                create_notion_project(
                    project_name,
                    category_name=category_name,
                    source=source,
                    last_synced=last_synced,
                    description=description_from_todoist
                )
                results['created'] += 1
            except Exception as e:
                results['errors'].append(f"Failed to create '{project_name}' (Category: {category_name}): {str(e)}")
    
    return results

@functions_framework.http
def sync_projects(request):
    """Main function entry point"""
    try:
        results = sync_todoist_to_notion()
        
        message = f"Sync complete! Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}."
        if results['errors']:
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
