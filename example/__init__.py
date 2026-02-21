"""
QuikUI Example Application

This example demonstrates how to use QuikUI in a production-like scenario,
showing HTMX fragment rendering with template variants.
The example shows:
- HTMX fragment rendering with template variants
- Create, read, update, and delete operations
- Streaming Server-Sent Events (SSE)
- Form handling with validation

Note: This example uses in-memory storage for simplicity. In production,
you would use SQLModel or another ORM for database persistence.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator

import quikui as qk
from fastapi import FastAPI, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import Field

app = FastAPI(title="QuikUI Example")

# Setup templates
templates = Jinja2Templates(directory="example/templates")
qk.register_filters(templates.env)


# Base Component
class Component(qk.BaseComponent):
    """
    Base class for all models in this application.
    Provides QuikUI's rendering capabilities.
    """

    quikui_template_package_name = "example"


# Domain Models


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Task(Component):
    """
    A task in our todo list application.

    Templates:
    - Task.html: Default detail view
    - Task.table.html: Table row for task list
    """

    id: int
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# In-memory storage (use SQLModel in production)
tasks_db: dict[int, Task] = {}
next_id = 1


# Routes


@app.get("/", include_in_schema=False)
async def redirect_to_home():
    return RedirectResponse("/tasks")


@app.get("/tasks", include_in_schema=False)
@qk.render_component(html_only=True, template="tasks.html", env=templates)
def tasks_page():
    """Main page showing all tasks."""
    return {"tasks": list(tasks_db.values()), "statuses": TaskStatus}


@app.get("/api/tasks")
@qk.render_component()
def get_tasks() -> list[Task]:
    """
    Get all tasks.
    - HTML mode: Returns table rows (using Task.table.html variant)
    - JSON mode: Returns list of task objects
    """
    return sorted(tasks_db.values(), key=lambda t: t.created_at, reverse=True)


@app.get("/api/tasks/{task_id}")
@qk.render_component()
def get_task(task_id: int) -> Task:
    """
    Get a single task.
    - HTML mode: Returns task detail view (using Task.html)
    - JSON mode: Returns task object
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/api/tasks", status_code=status.HTTP_201_CREATED)
@qk.render_component()
def create_task(
    title: str = Form(...),
    description: str = Form(""),
    status_value: str = Form(TaskStatus.TODO.value),
) -> Task:
    """
    Create a new task.
    - HTML mode: Returns table row to prepend to list (using Task.table.html via header)
    - JSON mode: Returns created task object
    """
    global next_id
    task = Task(
        id=next_id,
        title=title,
        description=description,
        status=TaskStatus(status_value),
    )
    tasks_db[next_id] = task
    next_id += 1
    return task


@app.patch("/api/tasks/{task_id}")
@qk.render_component()
def update_task(
    task_id: int,
    title: str = Form(None),
    description: str = Form(None),
    status_value: str = Form(None),
) -> Task:
    """
    Update a task.
    - HTML mode: Returns updated table row (using Task.table.html via header)
    - JSON mode: Returns updated task object
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if status_value is not None:
        task.status = TaskStatus(status_value)

    task.updated_at = datetime.now(timezone.utc)
    return task


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    """
    Delete a task.
    - HTML mode: Element removed by HTMX (hx-swap="delete")
    - JSON mode: Returns 204 No Content
    """
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")

    del tasks_db[task_id]


# Streaming Example


class Notification(Component):
    """
    A notification message.

    Template:
    - Notification.html: Toast-style notification
    """

    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@app.get("/notifications", response_model=None)
@qk.render_component(streaming=True)
async def stream_notifications() -> AsyncIterator[Notification]:
    """
    Stream notifications using Server-Sent Events.
    - HTML mode: Streams Notification.html fragments
    - JSON mode: Streams JSONL (newline-delimited JSON)
    """
    import asyncio

    yield Notification(message="Welcome to QuikUI!")
    await asyncio.sleep(2)
    yield Notification(message="This is a streaming notification example")
    await asyncio.sleep(2)
    yield Notification(message="Notifications appear every 2 seconds")
    await asyncio.sleep(2)
    yield Notification(message="This is the last notification")


if __name__ == "__main__":
    import uvicorn

    # Create some sample tasks
    tasks_db[1] = Task(
        id=1,
        title="Learn QuikUI",
        description="Read the documentation and try the examples",
        status=TaskStatus.IN_PROGRESS,
    )
    tasks_db[2] = Task(
        id=2,
        title="Build an HTMX app",
        description="Use QuikUI with FastAPI and HTMX",
        status=TaskStatus.TODO,
    )
    tasks_db[3] = Task(
        id=3,
        title="Deploy to production",
        description="Share your amazing app with the world",
        status=TaskStatus.TODO,
    )
    next_id = 4

    uvicorn.run(app, host="0.0.0.0", port=8000)
