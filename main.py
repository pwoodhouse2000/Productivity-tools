import functions_framework.http

@functions_framework.http
def sync_projects(request):
    """Our first cloud function!"""
    return {
        'status': 'success',
        'message': 'Hello from your Todoist-Notion sync app!'
    }