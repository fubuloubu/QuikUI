from enum import Enum
from functools import cache
from typing import ClassVar

import pytest
from fastapi import FastAPI, Form, status
from fastapi.testclient import TestClient
from jinja2 import DictLoader, Environment

import quikui as qk


class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@pytest.fixture
def app():
    app = FastAPI()

    templates = {
        "Task.html": '<div class="task">{{ title }} - {{ status.value }}</div>',
        "Task.table.html": "<tr><td>{{ title }}</td><td>{{ status.value }}</td></tr>",
    }
    env = Environment(loader=DictLoader(templates))
    qk.register_filters(env)

    class Task(qk.BaseComponent):
        id: int
        title: str
        status: Status = Status.ACTIVE

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    @app.get("/task/{task_id}")
    @qk.render_component()
    def get_task(task_id: int):
        return Task(id=task_id, title=f"Task {task_id}", status=Status.ACTIVE)

    @app.get("/tasks")
    @qk.render_component()
    def get_tasks():
        return [
            Task(id=1, title="Task 1", status=Status.ACTIVE),
            Task(id=2, title="Task 2", status=Status.INACTIVE),
        ]

    @app.post("/tasks", status_code=status.HTTP_201_CREATED)
    @qk.render_component()
    def create_task(title: str = Form(...)):
        return Task(id=1, title=title, status=Status.ACTIVE)

    @app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
    @qk.render_component()
    def delete_task(task_id: int):
        return None

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_html_response_mode(client):
    response = client.get("/task/1", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Task 1" in response.text


def test_json_response_mode(client):
    response = client.get("/task/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Task 1"
    assert data["status"] == "active"


def test_list_response_html(client):
    response = client.get("/tasks", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Task 1" in response.text
    assert "Task 2" in response.text


def test_list_response_json(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Task 1"


def test_post_html_mode(client):
    response = client.post("/tasks", data={"title": "New Task"}, headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "New Task" in response.text


def test_post_json_mode(client):
    response = client.post("/tasks", data={"title": "New Task"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "New Task"


def test_delete_html_mode_returns_empty_string(client):
    response = client.delete("/tasks/1", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.text == ""


def test_delete_json_mode_returns_204(client):
    response = client.delete("/tasks/1")
    assert response.status_code == 204
    assert response.text == ""


def test_variant_via_header(client):
    response = client.get("/task/1", headers={"Accept": "text/html", "Qk-Variant": "table"})
    assert response.status_code == 200
    assert "<tr>" in response.text
    assert "<td>" in response.text


def test_html_only_error_without_html_accept():
    """Test HtmlResponseOnlyError when html_only=True and no HTML Accept header."""
    app = FastAPI()

    class Item(qk.BaseComponent):
        name: str

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            env = Environment(loader=DictLoader({"Item.html": "<div>{{ name }}</div>"}))
            qk.register_filters(env)
            return env

    @app.get("/html-only")
    @qk.render_component(html_only=True)
    def get_html_only() -> Item:
        return Item(name="test")

    client = TestClient(app)
    response = client.get("/html-only")
    assert response.status_code == 406
    assert "can only provide HTML responses" in response.text


@pytest.mark.asyncio
async def test_streaming_html_responses():
    """Test streaming HTML responses with async generator."""
    app = FastAPI()

    class Task(qk.BaseComponent):
        title: str

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            env = Environment(loader=DictLoader({"Task.html": "<div>{{ title }}</div>"}))
            qk.register_filters(env)
            return env

    @app.get("/tasks/stream")
    @qk.render_component(streaming=True)
    async def stream_tasks():
        async def generate():
            for i in range(3):
                yield Task(title=f"Task {i}")

        return generate()

    client = TestClient(app)
    response = client.get("/tasks/stream", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "data: <div>Task 0</div>" in content
    assert "data: <div>Task 1</div>" in content
    assert "data: <div>Task 2</div>" in content


def test_streaming_sync_generator_html():
    """Test streaming HTML responses with sync generator."""
    app = FastAPI()

    class Task(qk.BaseComponent):
        title: str

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            env = Environment(loader=DictLoader({"Task.html": "<div>{{ title }}</div>"}))
            qk.register_filters(env)
            return env

    @app.get("/tasks/stream-sync")
    @qk.render_component(streaming=True)
    def stream_tasks_sync():
        def generate():
            for i in range(3):
                yield Task(title=f"Task {i}")

        return generate()

    client = TestClient(app)
    response = client.get("/tasks/stream-sync", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "data: <div>Task 0</div>" in content
    assert "data: <div>Task 1</div>" in content
    assert "data: <div>Task 2</div>" in content


@pytest.mark.asyncio
async def test_streaming_json_responses():
    """Test streaming JSON responses with async generator."""
    app = FastAPI()

    class Task(qk.BaseComponent):
        title: str

    @app.get("/tasks/stream-json")
    @qk.render_component(streaming=True)
    async def stream_tasks_json():
        async def generate():
            for i in range(3):
                yield Task(title=f"Task {i}")

        return generate()

    client = TestClient(app)
    response = client.get("/tasks/stream-json")
    assert response.status_code == 200
    assert "application/jsonl" in response.headers["content-type"]
    lines = response.text.strip().split("\n")
    assert len(lines) == 3
    assert '"title":"Task 0"' in lines[0]
    assert '"title":"Task 1"' in lines[1]
    assert '"title":"Task 2"' in lines[2]


def test_streaming_sync_generator_json():
    """Test streaming JSON responses with sync generator."""
    app = FastAPI()

    class Task(qk.BaseComponent):
        title: str

    @app.get("/tasks/stream-json-sync")
    @qk.render_component(streaming=True)
    def stream_tasks_json_sync():
        def generate():
            for i in range(3):
                yield Task(title=f"Task {i}")

        return generate()

    client = TestClient(app)
    response = client.get("/tasks/stream-json-sync")
    assert response.status_code == 200
    assert "application/jsonl" in response.headers["content-type"]
    lines = response.text.strip().split("\n")
    assert len(lines) == 3
    assert '"title":"Task 0"' in lines[0]


def test_wrapper_with_list_response():
    """Test wrapper functionality to wrap list responses."""
    app = FastAPI()

    class Task(qk.BaseComponent):
        title: str

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            env = Environment(
                loader=DictLoader({"Task.html": "<div>{{ title }}</div>"}), autoescape=True
            )
            qk.register_filters(env)
            return env

    class TaskList(qk.BaseComponent):
        # Use Any to accept BaseComponent instances
        items: list = []

        def __init__(self, *tasks, **data):
            # Store tasks (BaseComponent instances) as a regular field
            super().__init__(items=list(tasks), **data)

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            env = Environment(
                loader=DictLoader(
                    # Components with __html__() auto-render when autoescape is enabled
                    {
                        "TaskList.html": "<ul>{% for item in items %}<li>{{ item }}</li>{% endfor %}</ul>"
                    }
                ),
                autoescape=True,
            )
            qk.register_filters(env)
            return env

    @app.get("/tasks-wrapped")
    @qk.render_component(wrapper=TaskList)
    def get_tasks_wrapped():
        return [
            Task(title="Task 1"),
            Task(title="Task 2"),
        ]

    client = TestClient(app)
    response = client.get("/tasks-wrapped", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "<ul>" in response.text
    # The wrapper receives BaseComponent instances which get rendered in the template via __html__()
    assert "<li><div>Task 1</div></li>" in response.text
    assert "<li><div>Task 2</div></li>" in response.text


def test_component_html_method():
    """Test __html__() method for Jinja2 auto-rendering."""

    class Task(qk.BaseComponent):
        title: str

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            env = Environment(loader=DictLoader({"Task.html": "<div>{{ title }}</div>"}))
            qk.register_filters(env)
            return env

    task = Task(title="Test Task")
    html = task.__html__()
    assert html == "<div>Test Task</div>"

    # Also test that it works in Jinja2 template rendering with autoescape enabled
    env = Environment(
        loader=DictLoader({"wrapper.html": "<section>{{ task }}</section>"}), autoescape=True
    )
    env.filters.update({"is_component": qk.is_component})
    template = env.get_template("wrapper.html")
    result = template.render(task=task)
    assert "<section><div>Test Task</div></section>" in result


def test_template_variant_rendering():
    """Test rendering components with template variants."""

    class Task(qk.BaseComponent):
        title: str
        description: str = "No description"

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            env = Environment(
                loader=DictLoader(
                    {
                        "Task.html": "<div>{{ title }}</div>",
                        "Task.compact.html": "<span>{{ title }}</span>",
                    }
                )
            )
            qk.register_filters(env)
            return env

    task = Task(title="Test Task", description="A test task")

    # Test default template
    html_default = task.model_dump_html()
    assert html_default == "<div>Test Task</div>"

    # Test variant template
    html_compact = task.model_dump_html(template_variant="compact")
    assert html_compact == "<span>Test Task</span>"
