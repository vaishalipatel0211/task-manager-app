import os
import sqlite3
import csv
from io import StringIO
from functools import wraps
from datetime import datetime
from flask_mail import Mail, Message

from flask import Flask, g, render_template, request, redirect, url_for, session, flash, jsonify, make_response, Response
from werkzeug.security import generate_password_hash, check_password_hash

from flask_apscheduler import APScheduler

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["DATABASE"] = os.environ.get("TASK_MANAGER_DB", os.path.join(os.path.dirname(__file__), "task_manager.db"))
# ==========================================
# Flask-Mail Configurations
# ==========================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'vaishalipatel2170@gmail.com'
app.config['MAIL_PASSWORD'] = 'lvdd iuod glcm math'
app.config['MAIL_DEFAULT_SENDER'] = ('Task Manager', 'vaishalipatel2170@gmail.com')

mail = Mail(app)

def send_task_email(to_email, task_title, priority, due_date):
    try:
        msg = Message(
            subject=f"📌 New Task Created: {task_title}",
            recipients=[to_email]
        )
        msg.body = f"Hello,\n\nYour task '{task_title}' (Priority: {priority}, Due Date: {due_date}) has been created successfully!\n\nRegards,\nTask Manager"
        mail.send(msg)
        print("Notification Email Sent Successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")
    
scheduler = APScheduler()

def check_due_tasks():
    with app.app_context():
        today_str = datetime.now().strftime('%Y-%m-%d')
        db = get_db()
        
        query = """
            SELECT tasks.title, tasks.priority, tasks.due_date, users.email 
            FROM tasks 
            JOIN users ON tasks.user_id = users.id 
            WHERE tasks.due_date = ? AND tasks.status != 'Completed'
        """
        due_tasks = db.execute(query, (today_str,)).fetchall()
        
        for task in due_tasks:
            try:
                msg = Message(
                    subject=f"⏰ Reminder: Task Due Today - {task['title']}",
                    recipients=[task['email']]
                )
                msg.body = f"Hello,\n\nThis is an automated reminder that your task '{task['title']}' (Priority: {task['priority']}) is due TODAY!\n\nBest regards,\nTask Manager"
                mail.send(msg)
                print(f"Reminder sent to {task['email']} for task: {task['title']}")
            except Exception as e:
                print(f"Failed to send reminder email: {e}")

app.config['SCHEDULER_API_ENABLED'] = True
scheduler.init_app(app)

@scheduler.task('interval', id='daily_reminder_job', seconds=60)
def scheduled_job():
    check_due_tasks()

scheduler.start()

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT NOT NULL DEFAULT 'Medium',
                category TEXT NOT NULL DEFAULT 'Personal',
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS sub_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        db.commit()
init_db()
def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill out all fields.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        db = get_db()
        existing_user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing_user:
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("register"))

        db.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), "user"),
        )
        db.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_role"] = user["role"]
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    tasks = db.execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY due_date IS NULL, due_date, created_at DESC",
        (session["user_id"],),
    ).fetchall()

    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task["status"] == "Completed")
    pending_tasks = total_tasks - completed_tasks
    overdue_tasks = sum(
        1
        for task in tasks
        if task["status"] != "Completed" and task["due_date"] and task["due_date"] < datetime.now().strftime("%Y-%m-%d")
    )

    return render_template(
        "dashboard.html",
        tasks=tasks,
        stats={
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
        },
    )
@app.route("/tasks")
@login_required
def tasks_page():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    category = request.args.get("category", "")

    db = get_db()
    sql = "SELECT * FROM tasks WHERE user_id = ?"
    params = [session["user_id"]]

    if query:
        sql += " AND title LIKE ?"
        params.append(f"%{query}%")
    if status:
        sql += " AND status = ?"
        params.append(status)
    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY due_date IS NULL, due_date, created_at DESC"
    tasks = db.execute(sql, params).fetchall()
    all_user_tasks = db.execute("SELECT * FROM tasks WHERE user_id = ?", [session["user_id"]]).fetchall()
    
    stats = {
        'pending': sum(1 for t in all_user_tasks if t['status'] == 'Pending'),
        'completed': sum(1 for t in all_user_tasks if t['status'] == 'Completed'),
        'high': sum(1 for t in all_user_tasks if t['priority'] == 'High'),
        'medium': sum(1 for t in all_user_tasks if t['priority'] == 'Medium'),
        'low': sum(1 for t in all_user_tasks if t['priority'] == 'Low')
    }
    return render_template(
        "tasks.html",
        tasks=tasks,
        stats=stats,
        q=query,
        status=status,
        priority=priority,
        category=category,
    )


@app.route("/tasks/new", methods=["GET", "POST"])
@login_required
def new_task():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "Medium")
        category = request.form.get("category", "Personal")
        due_date = request.form.get("due_date", "")
        status = request.form.get("status", "Pending")

        if not title:
            flash("Task title is required.", "danger")
            return redirect(url_for("new_task"))

        db = get_db()
        db.execute(
            """
            INSERT INTO tasks (user_id, title, description, priority, category, due_date, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session["user_id"], title, description, priority, category, due_date, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        user_email = session.get('email', 'vaishalipatel2170@gmail.com')
        send_task_email(user_email, title, priority, due_date)
        flash("Task created successfully.", "success")
        return redirect(url_for("tasks_page"))

    return render_template("task_form.html", task=None)

@app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task or task["user_id"] != session["user_id"]:
        flash("Task not found.", "danger")
        return redirect(url_for("tasks_page"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", task["priority"])
        category = request.form.get("category", task["category"])
        due_date = request.form.get("due_date", task["due_date"])
        status = request.form.get("status", task["status"])

        if not title:
            flash("Task title is required.", "danger")
            return redirect(url_for("edit_task", task_id=task_id))

        db.execute(
            """
            UPDATE tasks
            SET title = ?, description = ?, priority = ?, category = ?, due_date = ?, status = ?
            WHERE id = ?
            """,
            (title, description, priority, category, due_date, status, task_id),
        )
        db.commit()
        flash("Task updated successfully.", "success")
        return redirect(url_for("tasks_page"))

    return render_template("task_form.html", task=task)


@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle_task(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task or task["user_id"] != session["user_id"]:
        flash("Task not found.", "danger")
        return redirect(url_for("tasks_page"))

    new_status = "Completed" if task["status"] != "Completed" else "Pending"
    db.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
    db.commit()
    flash("Task status updated.", "success")
    return redirect(url_for("dashboard"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task or task["user_id"] != session["user_id"]:
        flash("Task not found.", "danger")
        return redirect(url_for("tasks_page"))

    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    flash("Task deleted.", "success")
    return redirect(url_for("tasks_page"))


@app.route("/reports")
@login_required
def reports():
    db = get_db()
    tasks = db.execute("SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC", (session["user_id"],)).fetchall()
    completed = [task for task in tasks if task["status"] == "Completed"]
    stats = {
        "total": len(tasks),
        "completed": len(completed),
        "pending": len(tasks) - len(completed),
    }
    return render_template("reports.html", tasks=tasks, stats=stats)

@app.route("/admin")
@login_required
def admin():
    if session.get("user_role") != "admin":
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboard"))

    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    tasks = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    return render_template("admin.html", users=users, tasks=tasks)
@app.route("/admin/users/add", methods=["POST"])
@login_required
def add_user():
    if session.get("user_role") != "admin":
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboard"))

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    role = request.form.get("role", "user").strip().lower()

    if not name or not email or not password:
        flash("Please fill out all fields.", "danger")
        return redirect(url_for("admin"))

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("admin"))

    if role not in {"user", "admin"}:
        role = "user"

    db = get_db()
    existing_user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing_user:
        flash("An account with that email already exists.", "danger")
        return redirect(url_for("admin"))

    db.execute(
        "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash(password), role),
    )
    db.commit()
    flash("User added successfully.", "success")
    return redirect(url_for("admin"))
@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if session.get("user_role") != "admin":
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboard"))

    db = get_db()
    db.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("User removed.", "success")
    return redirect(url_for("admin"))

@app.route("/export/csv")
@login_required
def export_csv():
    db = get_db()
    tasks = db.execute("SELECT title, priority, category, due_date, status FROM tasks WHERE user_id = ?", (session["user_id"],)).fetchall()

    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Title', 'Priority', 'Category', 'Due Date', 'Status'])
    
    for task in tasks:
        writer.writerow([task['title'], task['priority'], task['category'], task['due_date'], task['status']])
        
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=tasks_export.csv"}
    )
if __name__ == "__main__":
    app.run(debug=True)
