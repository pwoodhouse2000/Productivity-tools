import functions_framework

@functions_framework.http
def hello(request):
    return {'message': 'Hello from test function'}
