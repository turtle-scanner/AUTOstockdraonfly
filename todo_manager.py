import json
import os
from datetime import datetime

TODO_FILE = "todo.json"

def load_todos():
    if os.path.exists(TODO_FILE):
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_todos(todos):
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

def add_todo(user_id, task):
    todos = load_todos()
    user_id = str(user_id)
    if user_id not in todos:
        todos[user_id] = []
    
    todos[user_id].append({
        "task": task,
        "done": False,
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    save_todos(todos)

def get_todos(user_id):
    todos = load_todos()
    return todos.get(str(user_id), [])

def clear_done_todos(user_id):
    todos = load_todos()
    user_id = str(user_id)
    if user_id in todos:
        todos[user_id] = [t for t in todos[user_id] if not t.get("done", False)]
        save_todos(todos)

def mark_as_done(user_id, index):
    todos = load_todos()
    user_id = str(user_id)
    if user_id in todos and 0 <= index < len(todos[user_id]):
        todos[user_id][index]["done"] = True
        save_todos(todos)
        return True
    return False
