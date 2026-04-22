import logging
import requests
import secrets

_LOGGER = logging.getLogger(__name__)


class VikunjaAPI:
    def __init__(self, url, vikunja_api_key):
        self.url = url.rstrip("/")
        self.api_token = vikunja_api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {vikunja_api_key}",
        }

    @staticmethod
    def _log_response_content(err):
        resp = getattr(err, "response", None)
        if resp is not None and hasattr(resp, "text"):
            _LOGGER.error("Response content: %s", resp.text)
        return resp

    @staticmethod
    def _is_invalid_token_response(response) -> bool:
        if response is None or getattr(response, "status_code", None) != 401:
            return False
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            if payload.get("code") == 11:
                return True
            message = str(payload.get("message", "")).lower()
            return "invalid token" in message
        text = getattr(response, "text", "")
        return "invalid token" in text.lower()

    def _log_scoped_token_hint(self, response, route_description, remedy):
        if not self._is_invalid_token_response(response):
            return
        _LOGGER.error(
            "Vikunja rejected %s with an invalid-token response. If you're using a scoped API token, Vikunja 2.3.0 tightened token matching to both HTTP method and path. %s",
            route_description,
            remedy,
        )

    def test_connection(self):
        """Simple connectivity check by listing projects."""
        try:
            response = requests.get(
                f"{self.url}/projects", headers=self.headers, timeout=30
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Connection test failed: %s", err)
            resp = getattr(err, "response", None)
            if resp is not None and hasattr(resp, "text"):
                _LOGGER.error("Response content: %s", resp.text)
            return False

    def get_projects(self):
        """Return all accessible projects or [] on failure."""
        try:
            response = requests.get(
                f"{self.url}/projects", headers=self.headers, timeout=30
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to get projects: %s", err)
            resp = getattr(err, "response", None)
            if resp is not None and hasattr(resp, "text"):
                _LOGGER.error("Response content: %s", resp.text)
            return []

    def get_project_users(self, project_id: int):
        """Return all users assigned to a project or [] on failure."""
        try:
            response = requests.get(
                f"{self.url}/projects/{project_id}/projectusers",
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except requests.exceptions.RequestException as err:
            _LOGGER.error(
                "Failed to get users for project %s: %s", project_id, err
            )
            resp = getattr(err, "response", None)
            if resp is not None and hasattr(resp, "text"):
                _LOGGER.error("Response content: %s", resp.text)
            return []

    def get_labels(self):
        try:
            response = requests.get(
                f"{self.url}/labels", headers=self.headers, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to get labels: %s", err)
            resp = getattr(err, "response", None)
            if resp is not None and hasattr(resp, "text"):
                _LOGGER.error("Response content: %s", resp.text)
            return []

    def create_label(self, label_name):
        """Create a new label with a random hex color."""
        payload = {"title": label_name, "hex_color": secrets.token_hex(3)}
        try:
            response = requests.put(
                f"{self.url}/labels", headers=self.headers, json=payload, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to create label '%s': %s", label_name, err)
            resp = getattr(err, "response", None)
            if resp is not None and hasattr(resp, "text"):
                _LOGGER.error("Response content: %s", resp.text)
            return None

    def add_label_to_task(self, task_id: int, label_id: int):
        """Attach existing label to a task. Returns True on success."""
        try:
            response = requests.put(
                f"{self.url}/tasks/{task_id}/labels",
                headers=self.headers,
                json={"label_id": label_id},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as err:
            _LOGGER.error(
                "Failed to attach label %s to task %s: %s", label_id, task_id, err
            )
            resp = self._log_response_content(err)
            self._log_scoped_token_hint(
                resp,
                "label attachment via PUT /tasks/{task}/labels",
                "Recreate the API token and grant access for this route. For task labels, Vikunja usually needs task-update scope in addition to label read/create permissions. If you only need task creation, you can also disable the auto voice label option.",
            )
            return False

    def add_task(self, task_data):
        """Create a new task (requires title, uses project_id then removes it)."""
        project_id = task_data.get("project_id", 1)
        if not task_data.get("title"):
            _LOGGER.error("Cannot create task: missing 'title'")
            return None
        try:
            response = requests.put(
                f"{self.url}/projects/{project_id}/tasks",
                headers=self.headers,
                json=task_data,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to create task in project %s: %s", project_id, err)
            resp = getattr(err, "response", None)
            if resp is not None and hasattr(resp, "text"):
                _LOGGER.error("Response content: %s", resp.text)
            return None

    # --- User / Assignee helpers ---
    def search_users(self, search: str, page: int = 1):
        """Search users by partial string. Returns list or []."""
        try:
            response = requests.get(
                f"{self.url}/users",
                params={"s": search, "page": page},
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            # Expecting list of user objects
            if isinstance(data, list):
                return data
            return []
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to search users with query '%s': %s", search, err)
            return []

    def assign_user_to_task(self, task_id: int, user_id: int):
        """Assign a user to a task. Returns True on success."""
        payload = {
            "max_permission": None,
            "created": "1970-01-01T00:00:00.000Z",
            "user_id": user_id,
            "task_id": task_id,
        }
        try:
            response = requests.put(
                f"{self.url}/tasks/{task_id}/assignees",
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as err:
            _LOGGER.error(
                "Failed to assign user %s to task %s: %s", user_id, task_id, err
            )
            resp = self._log_response_content(err)
            self._log_scoped_token_hint(
                resp,
                "assignee attachment via PUT /tasks/{taskID}/assignees",
                "Recreate the API token and grant access for this route. On newer Vikunja versions, assignee updates may require their own scoped permission in addition to basic task creation.",
            )
            return False
