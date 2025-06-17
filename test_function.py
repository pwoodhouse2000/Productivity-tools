import unittest
from unittest.mock import patch, MagicMock, call
import os

# Assuming main.py is in the same directory or accessible in PYTHONPATH
import main

class TestSyncTodoistToNotion(unittest.TestCase):

    @patch.dict(os.environ, {"GCP_PROJECT": "test-project"})
    @patch('main.secret_client')
    def setUp(self, mock_secret_client):
        # Mock get_secret for all tests in this class
        self.mock_get_secret = MagicMock()
        main.get_secret = self.mock_get_secret
        self.mock_get_secret.side_effect = self._get_secret_side_effect

        # Default secrets
        self.secrets = {
            "todoist-api-key": "fake_todoist_key",
            "notion-api-key": "fake_notion_key",
            "notion-database-id": "fake_db_id"
        }

    def _get_secret_side_effect(self, secret_name):
        return self.secrets.get(secret_name)

    # --- Mock API Data ---
    def get_mock_todoist_projects_response(self, with_parent=True, with_child=True, empty=False):
        if empty:
            return []

        projects = [
            {"id": "100", "name": "Parent Project 1", "parent_id": None},
            {"id": "200", "name": "Standalone Project 2", "parent_id": None},
        ]
        if with_parent: # This seems to be a misnomer, more like "with a project that IS a parent"
             # Project 100 is already a parent if a child references it.
            pass # Parent Project 1 is already defined
        if with_child:
            projects.append({"id": "101", "name": "Child Project of 1", "parent_id": "100"})

        projects.extend([
            {"id": "300", "name": "Parent Project 3", "parent_id": None},
            {"id": "301", "name": "Child Project of 3", "parent_id": "300"},
            {"id": "400", "name": "Standalone Project 4", "parent_id": None},
        ])
        return projects

    def get_mock_notion_query_response(self, existing_project_names=None):
        if existing_project_names is None:
            existing_project_names = []

        results = []
        for name in existing_project_names:
            results.append({
                "properties": {
                    "Name": {
                        "title": [{"text": {"content": name}}]
                    }
                }
            })
        return {"results": results}

    # --- Test Cases ---

    @patch('requests.post')
    @patch('requests.get')
    def test_sync_with_parent_and_child_projects(self, mock_requests_get, mock_requests_post):
        # --- MOCK Todoist API ---
        # get_todoist_projects (first call in sync_todoist_to_notion)
        mock_todoist_response = MagicMock()
        mock_todoist_response.status_code = 200
        mock_todoist_projects_data = self.get_mock_todoist_projects_response()
        mock_todoist_response.json.return_value = mock_todoist_projects_data

        # --- MOCK Notion API ---
        # get_notion_projects (second call in sync_todoist_to_notion)
        mock_notion_query_response = MagicMock()
        mock_notion_query_response.status_code = 200
        mock_notion_query_response.json.return_value = self.get_mock_notion_query_response(existing_project_names=[])

        # create_notion_project (called multiple times)
        mock_notion_create_response = MagicMock()
        mock_notion_create_response.status_code = 200
        mock_notion_create_response.json.return_value = {"id": "new_page_id"}

        # Assign mocks to requests.get and requests.post
        # requests.get is used by get_todoist_projects
        # requests.post is used by get_notion_projects and create_notion_project
        mock_requests_get.return_value = mock_todoist_response
        mock_requests_post.side_effect = [
            mock_notion_query_response, # First POST is for querying Notion
            mock_notion_create_response, # Create "Parent Project 1"
            mock_notion_create_response, # Create "Standalone Project 2"
            mock_notion_create_response, # Create "Child Project of 1"
            mock_notion_create_response, # Create "Parent Project 3"
            mock_notion_create_response, # Create "Child Project of 3"
            mock_notion_create_response  # Create "Standalone Project 4"
        ]

        # Call the function to test
        results = main.sync_todoist_to_notion()

        # Assertions
        self.assertEqual(results["checked"], len(mock_todoist_projects_data))
        self.assertEqual(results["created"], len(mock_todoist_projects_data)) # Assuming no existing projects
        self.assertEqual(results["skipped"], 0)
        self.assertEqual(len(results["errors"]), 0)

        # Verify calls to create_notion_project (via requests.post)
        # Expected calls to Notion API to create pages
        # Note: The first call to mock_requests_post is for get_notion_projects
        expected_create_calls = [
            call(
                "https://api.notion.com/v1/pages",
                headers=unittest.mock.ANY,
                json={'parent': {'database_id': 'fake_db_id'}, 'properties': {'Name': {'title': [{'text': {'content': 'Parent Project 1'}}]}, }}
            ),
            call(
                "https://api.notion.com/v1/pages",
                headers=unittest.mock.ANY,
                json={'parent': {'database_id': 'fake_db_id'}, 'properties': {'Name': {'title': [{'text': {'content': 'Standalone Project 2'}}]}, }}
            ),
            call(
                "https://api.notion.com/v1/pages",
                headers=unittest.mock.ANY,
                json={'parent': {'database_id': 'fake_db_id'}, 'properties': {'Name': {'title': [{'text': {'content': 'Child Project of 1'}}]}, 'Category': {'select': {'name': 'Parent Project 1'}}}}
            ),
             call(
                "https://api.notion.com/v1/pages",
                headers=unittest.mock.ANY,
                json={'parent': {'database_id': 'fake_db_id'}, 'properties': {'Name': {'title': [{'text': {'content': 'Parent Project 3'}}]}, }}
            ),
            call(
                "https://api.notion.com/v1/pages",
                headers=unittest.mock.ANY,
                json={'parent': {'database_id': 'fake_db_id'}, 'properties': {'Name': {'title': [{'text': {'content': 'Child Project of 3'}}]}, 'Category': {'select': {'name': 'Parent Project 3'}}}}
            ),
            call(
                "https://api.notion.com/v1/pages",
                headers=unittest.mock.ANY,
                json={'parent': {'database_id': 'fake_db_id'}, 'properties': {'Name': {'title': [{'text': {'content': 'Standalone Project 4'}}]}, }}
            )
        ]
        # Check calls after the first one (which is the query)
        self.assertEqual(mock_requests_post.call_args_list[1:], expected_create_calls)

    @patch('requests.post')
    @patch('requests.get')
    def test_sync_todoist_api_error(self, mock_requests_get, mock_requests_post):
        # Mock Todoist API to return an error
        mock_todoist_response = MagicMock()
        mock_todoist_response.status_code = 500
        mock_todoist_response.text = "Internal Server Error"
        mock_requests_get.return_value = mock_todoist_response

        # Call the function
        results = main.sync_todoist_to_notion()

        # Assertions
        self.assertEqual(results["checked"], 0) # No projects checked due to API error
        self.assertEqual(results["created"], 0)
        self.assertEqual(results["skipped"], 0)
        # The error is printed by get_todoist_projects, sync_todoist_to_notion returns empty
        # This behavior might need adjustment based on desired error reporting for the main function
        self.assertEqual(len(results["errors"]), 0)

        # Ensure Notion API (get_notion_projects and create_notion_project) was not called
        mock_requests_post.assert_not_called()


    @patch('requests.post')
    @patch('requests.get')
    def test_sync_notion_create_project_api_error(self, mock_requests_get, mock_requests_post):
        # Mock Todoist API success
        mock_todoist_response = MagicMock()
        mock_todoist_response.status_code = 200
        # Using a simpler dataset for this test
        mock_todoist_projects_data = [{"id": "500", "name": "Project To Fail", "parent_id": None}]
        mock_todoist_response.json.return_value = mock_todoist_projects_data
        mock_requests_get.return_value = mock_todoist_response

        # Mock Notion get_notion_projects success (empty)
        mock_notion_query_response = MagicMock()
        mock_notion_query_response.status_code = 200
        mock_notion_query_response.json.return_value = self.get_mock_notion_query_response()

        # Mock Notion create_notion_project to fail
        mock_notion_create_response = MagicMock()
        mock_notion_create_response.status_code = 400 # Bad Request or some other error
        mock_notion_create_response.text = "Failed to create page"

        mock_requests_post.side_effect = [
            mock_notion_query_response, # First POST for querying Notion
            mock_notion_create_response  # Second POST for creating "Project To Fail"
        ]

        # Call the function
        results = main.sync_todoist_to_notion()

        # Assertions
        self.assertEqual(results["checked"], 1)
        self.assertEqual(results["created"], 0) # Creation failed
        self.assertEqual(results["skipped"], 0)
        self.assertEqual(len(results["errors"]), 1)
        self.assertIn("Failed 'Project To Fail'", results["errors"][0])

    @patch('requests.post')
    @patch('requests.get')
    def test_sync_skip_existing_projects(self, mock_requests_get, mock_requests_post):
        # Mock Todoist API
        mock_todoist_response = MagicMock()
        mock_todoist_response.status_code = 200
        mock_todoist_projects_data = [
            {"id": "600", "name": "Existing Project", "parent_id": None},
            {"id": "601", "name": "New Project To Create", "parent_id": None}
        ]
        mock_todoist_response.json.return_value = mock_todoist_projects_data
        mock_requests_get.return_value = mock_todoist_response

        # Mock Notion get_notion_projects to return "Existing Project"
        mock_notion_query_response = MagicMock()
        mock_notion_query_response.status_code = 200
        mock_notion_query_response.json.return_value = self.get_mock_notion_query_response(
            existing_project_names=["Existing Project"]
        )

        # Mock Notion create_notion_project success for the new project
        mock_notion_create_response = MagicMock()
        mock_notion_create_response.status_code = 200
        mock_notion_create_response.json.return_value = {"id": "new_page_id"}

        mock_requests_post.side_effect = [
            mock_notion_query_response,   # For get_notion_projects
            mock_notion_create_response   # For create_notion_project("New Project To Create")
        ]

        # Call the function
        results = main.sync_todoist_to_notion()

        # Assertions
        self.assertEqual(results["checked"], 2)
        self.assertEqual(results["created"], 1) # Only "New Project To Create"
        self.assertEqual(results["skipped"], 1) # "Existing Project" was skipped
        self.assertEqual(len(results["errors"]), 0)

        # Ensure create_notion_project was only called for "New Project To Create"
        # The first call to mock_requests_post is get_notion_projects
        self.assertEqual(mock_requests_post.call_count, 2)
        create_call_args = mock_requests_post.call_args_list[1].kwargs['json']
        self.assertEqual(create_call_args['properties']['Name']['title'][0]['text']['content'], "New Project To Create")

if __name__ == '__main__':
    unittest.main()
