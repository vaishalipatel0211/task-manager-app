import importlib
import os
import tempfile
import unittest

class TaskManagerAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_task_manager.db")
        os.environ["TASK_MANAGER_DB"] = self.db_path

        import app as task_app_module
        self.task_app_module = importlib.reload(task_app_module)
        self.task_app_module.init_db()
        self.client = self.task_app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dashboard_renders_with_structured_layout(self):
        self.client.post(
            "/register",
            data={
                "name": "Alice",
                "email": "alice@example.com",
                "password": "secret123",
                "confirm_password": "secret123",
            },
        )
        self.client.post(
            "/login",
            data={"email": "alice@example.com", "password": "secret123"},
        )
        self.client.post(
            "/tasks/new",
            data={
                "title": "Finish report",
                "description": "Prepare the semester report",
                "priority": "High",
                "category": "Study",
                "due_date": "2026-08-01",
            },
        )

        dashboard_response = self.client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        html = dashboard_response.get_data(as_text=True)
        self.assertIn("dashboard-shell", html)
        self.assertIn("dashboard-content", html)

    def test_registration_and_task_creation_flow(self):
        register_response = self.client.post(
            "/register",
            data={
                "name": "Alice",
                "email": "alice@example.com",
                "password": "secret123",
                "confirm_password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertEqual(register_response.status_code, 200)
        self.assertIn("Login", register_response.get_data(as_text=True))

        login_response = self.client.post(
            "/login",
            data={"email": "alice@example.com", "password": "secret123"},
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("Dashboard", login_response.get_data(as_text=True))

        create_task_response = self.client.post(
            "/tasks/new",
            data={
                "title": "Finish report",
                "description": "Prepare the semester report",
                "priority": "High",
                "category": "Study",
                "due_date": "2026-08-01",
            },
            follow_redirects=True,
        )
        self.assertEqual(create_task_response.status_code, 200)
        self.assertIn("Finish report", create_task_response.get_data(as_text=True))

        dashboard_response = self.client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("1", dashboard_response.get_data(as_text=True))

    def test_admin_can_add_new_user(self):
        self.client.post(
            "/register",
            data={
                "name": "Admin User",
                "email": "admin@example.com",
                "password": "secret123",
                "confirm_password": "secret123",
            },
        )

        db = self.task_app_module.get_db()
        db.execute("UPDATE users SET role = 'admin' WHERE email = ?", ("admin@example.com",))
        db.commit()

        self.client.post(
            "/login",
            data={"email": "admin@example.com", "password": "secret123"},
        )

        response = self.client.post(
            "/admin/users/add",
            data={
                "name": "Bob Smith",
                "email": "bob@example.com",
                "password": "welcome123",
                "confirm_password": "welcome123",
                "role": "user",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Bob Smith", response.get_data(as_text=True))
        self.assertIn("bob@example.com", response.get_data(as_text=True))

        user_row = db.execute("SELECT id FROM users WHERE email = ?", ("bob@example.com",)).fetchone()
        self.assertIsNotNone(user_row)


if __name__ == "__main__":
    unittest.main()
