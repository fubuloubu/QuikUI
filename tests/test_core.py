from enum import Enum

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
        def quikui_environment(cls):
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
