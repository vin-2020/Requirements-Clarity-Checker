# db/database.py
import sqlite3
from datetime import datetime

DATABASE_NAME = "reqcheck_projects.db"

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Create Projects Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    ''')

    # Create Documents Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL,
            clarity_score INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    ''')

    # Create Requirements Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            req_id_string TEXT NOT NULL,
            req_text TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def add_project(project_name):
    """Adds a new project to the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", 
                       (project_name, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        return "Project name already exists."
    finally:
        conn.close()
    return "Project added successfully."

def get_all_projects():
    """Retrieves a list of all projects."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM projects ORDER BY name")
    projects = cursor.fetchall()
    conn.close()
    return projects

def delete_project(project_id: int) -> str:
    conn = sqlite3.connect(DATABASE_NAME)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()

        # Remove children first (manual cascade)
        cur.execute(
            "DELETE FROM requirements WHERE document_id IN "
            "(SELECT id FROM documents WHERE project_id = ?)",
            (project_id,)
        )
        cur.execute("DELETE FROM documents WHERE project_id = ?", (project_id,))
        cur.execute("DELETE FROM projects  WHERE id = ?", (project_id,))

        conn.commit()
        return "Project deleted successfully."
    finally:
        conn.close()
