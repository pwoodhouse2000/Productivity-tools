import functions_framework
from src.sync import run_full_sync


@functions_framework.http
def sync_projects(request):
    """
    Cloud Function entry point. Triggers a full, one-way sync from Todoist to Notion.
    """
    try:
        print("Sync function triggered.")
        results = run_full_sync()
        print(f"Sync function completed successfully. Results: {results}")
        return {
            "status": "success",
            "message": "Sync completed.",
            "details": results
        }
    except Exception as e:
        print(f"Sync function failed with error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }, 500
