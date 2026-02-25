import functions_framework
import os
import json
import uuid
import requests
from datetime import date, timedelta
from google.cloud import secretmanager
from notion_client import Client
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Project

# --- Configuration ---
PROJECT_ID = "notion-todoist-sync-464419"  # Secret Manager project
NOTION_PROJECTS_DB_ID = "21d89c4a21dd805d971eef334fea9640"
NOTION_TASKS_DB_ID = "21d89c4a21dd80f0a679e685cc7a3496"
NOTION_TODOIST_TASKS_DB_ID = "28789c4a21dd801bac9afec0722348a0"
NOTION_SECRET_NAME = "notion-api-key"
TODOIST_SECRET_NAME = "todoist-api-key"
ACTIVE_NOTION_STATUSES = {"Planning", "In Progress", "Ongoing"}
TODOIST_SYNC_URL = "https://api.todoist.com/api/v1/sync"

PARA_LABELS = [
    "PROSPER \ud83d\udcc1",
    "WORK \ud83d\udcc1",
    "HEALTH \ud83d\udcc1",
    "PERSONAL & FAMILY \ud83d\udcc1",
    "HOME \ud83d\udcc1",
    "FINANCIAL \ud83d\udcc1",
    "FUN \ud83d\udcc1",
]

# --- Helper Functions ---

def get_secret(secret_name, version="latest"):
    """Retrieves a secret from Google Secret Manager."""
    print(f"Attempting to retrieve secret: {secret_name}")
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/{version}"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")
        print(f"Successfully retrieved secret: {secret_name}")
        return secret_value
    except Exception as e:
        print(f"Error retrieving secret {secret_name}: {e}")
        raise


def resolve_date(val):
    """Resolve natural language date strings to YYYY-MM-DD."""
    today = date.today()
    v = val.lower().strip()
    if v == "today":
        return today.isoformat()
    if v == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if v == "friday":
        diff = (4 - today.weekday() + 7) % 7 or 7
        return (today + timedelta(days=diff)).isoformat()
    if v in ("saturday", "weekend", "this weekend"):
        diff = (5 - today.weekday() + 7) % 7 or 7
        return (today + timedelta(days=diff)).isoformat()
    if v in ("monday", "next week"):
        diff = (7 - today.weekday()) % 7 or 7
        return (today + timedelta(days=diff)).isoformat()
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        return v
    return None


def parse_instructions(instructions):
    """
    Parse instruction string like '1->today, 2,3->friday, 4->complete, 5->skip'
    into {task_num: action}.
    """
    import re
    parsed = {}
    segments = re.split(r'(?<=\w)\s*,\s*(?=\d)', instructions)
    for seg in segments:
        seg = seg.strip()
        match = re.match(r'^([\d\s,]+)\s*[\u2192\->=:]+\s*(.+)$', seg)
        if match:
            nums = re.split(r'[\s,]+', match.group(1).strip())
            action = match.group(2).strip()
            for n in nums:
                n = n.strip()
                if n:
                    parsed[n] = action
    return parsed


# --- Existing: sync_projects ---

def create_notion_project(notion_client, todoist_project):
    """Creates a new project page in the Notion projects database."""
    print(f"Creating Notion project for: {todoist_project.name}")
    try:
        notion_client.pages.create(
            parent={"database_id": NOTION_PROJECTS_DB_ID},
            properties={
                "Name": {"title": [{"text": {"content": todoist_project.name}}]},
                "Todoist Project ID": {"rich_text": [{"text": {"content": todoist_project.id}}]},
                "Status": {"select": {"name": "Planning"}},
            },
        )
        print(f"Successfully created Notion project: {todoist_project.name}")
    except Exception as e:
        print(f"Error creating Notion project {todoist_project.name}: {e}")
        raise


@functions_framework.http
def sync_projects(request):
    """HTTP Cloud Function to sync Todoist projects to Notion."""
    print("Starting Todoist to Notion project sync...")
    try:
        todoist_api_key = get_secret(TODOIST_SECRET_NAME)
        notion_api_key = get_secret(NOTION_SECRET_NAME)
    except Exception as e:
        return (f"Error retrieving secrets: {e}", 500)
    try:
        todoist_api = TodoistAPI(todoist_api_key)
        notion_client = Client(auth=notion_api_key)
    except Exception as e:
        return (f"Error initializing API clients: {e}", 500)
    try:
        todoist_projects = todoist_api.get_projects()
        print(f"Retrieved {len(todoist_projects)} projects from Todoist.")
    except Exception as e:
        return (f"Error fetching Todoist projects: {e}", 500)
    try:
        notion_response = notion_client.databases.query(
            database_id=NOTION_PROJECTS_DB_ID,
            filter={"property": "Status", "select": {"is_not_empty": True}},
        )
        existing_notion_projects = {
            page["properties"]["Name"]["title"][0]["plain_text"]: page
            for page in notion_response.get("results", [])
            if page["properties"]["Name"]["title"]
        }
        print(f"Found {len(existing_notion_projects)} existing projects in Notion.")
    except Exception as e:
        return (f"Error fetching Notion projects: {e}", 500)
    created_count = 0
    skipped_count = 0
    for project in todoist_projects:
        if project.name not in existing_notion_projects:
            try:
                create_notion_project(notion_client, project)
                created_count += 1
            except Exception as e:
                print(f"Failed to create project {project.name}: {e}")
                skipped_count += 1
        else:
            print(f"Project already exists in Notion: {project.name}")
            skipped_count += 1
    return (
        f"Sync complete. Created: {created_count}, Skipped/Existing: {skipped_count}",
        200,
    )


# --- NEW: todoist_review ---

@functions_framework.http
def todoist_review(request):
    """
    HTTP Cloud Function - GET
    Fetches all overdue + undated Todoist tasks with a PARA label.
    Returns numbered list + task_map for use with todoist_execute.
    """
    if request.method == "OPTIONS":
        return ("", 204, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET", "Access-Control-Allow-Headers": "Content-Type"})
    headers = {"Access-Control-Allow-Origin": "*"}
    try:
        todoist_api_key = get_secret(TODOIST_SECRET_NAME)
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500, headers)
    try:
        r = requests.post(
            TODOIST_SYNC_URL,
            headers={"Authorization": f"Bearer {todoist_api_key}"},
            json={"sync_token": "*", "resource_types": ["items"]},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return (json.dumps({"error": f"Todoist API error: {e}"}), 500, headers)
    today_str = date.today().isoformat()
    tasks = [t for t in data.get("items", []) if not t.get("checked") and not t.get("is_deleted")]
    overdue = []
    undated = []
    for t in tasks:
        para_label = next((l for l in t.get("labels", []) if l in PARA_LABELS), None)
        if not para_label:
            continue
        t["_para"] = para_label
        if not t.get("due"):
            undated.append(t)
        elif t["due"]["date"].split("T")[0] < today_str:
            overdue.append(t)
    num = 1
    lines = []
    task_map = {}
    for label in PARA_LABELS:
        od = [t for t in overdue if t["_para"] == label]
        ud = [t for t in undated if t["_para"] == label]
        if od:
            lines.append(f"\n\U0001f4cb {label} - OVERDUE")
            for t in od:
                lines.append(f"  {num}. [{t['due']['date']}] {t['content']}")
                task_map[str(num)] = t["id"]
                num += 1
        if ud:
            lines.append(f"\n\U0001f4cb {label} - NO DATE")
            for t in ud:
                lines.append(f"  {num}. {t['content']}")
                task_map[str(num)] = t["id"]
                num += 1
    total = len(overdue) + len(undated)
    header = f"\n\U0001f5c2  TODOIST DAILY REVIEW - {today_str}\n\U0001f4cc {len(overdue)} overdue | \U0001f4c5 {len(undated)} undated | Total: {total}\n" + "-" * 50
    text = header + "\n".join(lines)
    if total > 0:
        text += '\n\nTell Claude your instructions, e.g.: "1->today, 2,3->friday, 4->complete, 5->skip"'
    else:
        text += "\n\nAll clear - nothing to review!"
    result = {"date": today_str, "overdue_count": len(overdue), "undated_count": len(undated), "total": total, "task_map": task_map, "text": text}
    return (json.dumps(result), 200, {**headers, "Content-Type": "application/json"})


# --- NEW: todoist_execute ---

@functions_framework.http
def todoist_execute(request):
    """
    HTTP Cloud Function - POST
    Applies batch instructions to Todoist tasks.
    Body: {"instructions": "1->today, 2->friday", "task_map": {"1": "task_id", ...}}
    """
    if request.method == "OPTIONS":
        return ("", 204, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type"})
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
    try:
        body = request.get_json(force=True)
    except Exception:
        return (json.dumps({"error": "Invalid JSON body"}), 400, headers)
    if not body or "instructions" not in body or "task_map" not in body:
        return (json.dumps({"error": "Required: 'instructions' and 'task_map'"}), 400, headers)
    instructions = body["instructions"]
    task_map = body["task_map"]
    try:
        todoist_api_key = get_secret(TODOIST_SECRET_NAME)
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500, headers)
    parsed = parse_instructions(instructions)
    commands = []
    results = []
    for num_str, action in parsed.items():
        task_id = task_map.get(num_str)
        if not task_id:
            results.append(f"  #{num_str}: not found")
            continue
        cmd_uuid = str(uuid.uuid4())
        lower = action.lower().strip()
        if lower in ("skip", "s"):
            results.append(f"  #{num_str}: skipped")
        elif lower in ("complete", "done", "c"):
            commands.append({"type": "item_close", "uuid": cmd_uuid, "args": {"id": task_id}})
            results.append(f"  #{num_str}: complete")
        elif lower in ("no date", "remove date", "nodate"):
            commands.append({"type": "item_update", "uuid": cmd_uuid, "args": {"id": task_id, "due": None}})
            results.append(f"  #{num_str}: date removed")
        else:
            resolved = resolve_date(action)
            if resolved:
                commands.append({"type": "item_update", "uuid": cmd_uuid, "args": {"id": task_id, "due": {"date": resolved}}})
                results.append(f"  #{num_str}: -> {resolved}")
            else:
                results.append(f"  #{num_str}: unknown action '{action}'")
    if not commands:
        return (json.dumps({"commands_sent": 0, "all_ok": True, "results": results}), 200, headers)
    try:
        r = requests.post(
            TODOIST_SYNC_URL,
            headers={"Authorization": f"Bearer {todoist_api_key}"},
            json={"commands": commands},
            timeout=30,
        )
        r.raise_for_status()
        sync_resp = r.json()
    except Exception as e:
        return (json.dumps({"error": f"Todoist API error: {e}", "results": results}), 500, headers)
    all_ok = all(v == "ok" for v in sync_resp.get("sync_status", {}).values())
    return (
        json.dumps({"commands_sent": len(commands), "all_ok": all_ok, "sync_status": sync_resp.get("sync_status"), "results": results}),
        200,
        headers,
    )
