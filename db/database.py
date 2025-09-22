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
        # This error occurs if the project name already exists
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

# We will add more functions here later to save documents and analysis results.