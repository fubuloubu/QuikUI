"""Tests for HTMX-friendly error handling."""

import pytest
from fastapi import FastAPI, Form, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

import quikui as qk
from quikui.error_handlers import ErrorDetail


class PersonModel(BaseModel):
    name: str = Field(min_length=1)
    age: int = Field(ge=0, le=150)


@pytest.fixture
def app():
    """Create a FastAPI app with error handlers for testing."""
    app = FastAPI()

    # Setup error handlers
    qk.setup_error_handlers(app)

    @app.get("/test-404")
    @qk.render_component()
    def not_found():
        raise HTTPException(status_code=404, detail="Item not found")

    @app.get("/test-400")
    @qk.render_component()
    def bad_request():
        raise HTTPException(status_code=400, detail="Bad request")

    @app.post("/test-validation")
    def validate_data(
        name: str = Form(..., min_length=1),
        age: int = Form(..., ge=0, le=150),
    ):
        # Validation happens automatically via FastAPI
        # Don't use @qk.render_component for this test since we just want to test error handling
        return {"name": name, "age": age}

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


def test_http_exception_json_response(client):
    """Test that HTTPException returns JSON for JSON requests."""
    response = client.get(
        "/test-404",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"detail": "Item not found"}


def test_http_exception_html_response(client):
    """Test that HTTPException returns HTML for HTMX requests."""
    response = client.get(
        "/test-404",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Item not found" in response.text
    assert "Not Found" in response.text


def test_http_exception_html_accept_header(client):
    """Test that HTTPException returns HTML when Accept header includes text/html."""
    response = client.get(
        "/test-404",
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Item not found" in response.text


def test_validation_error_json_response(client):
    """Test that validation errors return JSON for JSON requests."""
    response = client.post(
        "/test-validation",
        data={"name": "", "age": 200},  # Invalid: name too short, age too high
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "detail" in data
    assert isinstance(data["detail"], list)


def test_validation_error_html_response(client):
    """Test that validation errors return HTML for HTMX requests."""
    response = client.post(
        "/test-validation",
        data={"name": "", "age": 200},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert "text/html" in response.headers["content-type"]
    assert "Validation Error" in response.text
    assert "body.name" in response.text
    assert "body.age" in response.text


def test_error_detail_model():
    """Test ErrorDetail model for validation errors."""
    detail = ErrorDetail(
        loc=["body", "name"],
        msg="Field required",
        type="missing",
    )
    assert detail.loc == ["body", "name"]
    assert detail.msg == "Field required"
    assert detail.type == "missing"


def test_setup_error_handlers_with_template_env():
    """Test setup_error_handlers with custom template environment."""
    from jinja2 import DictLoader, Environment

    app = FastAPI()

    # Setup with custom template environment
    custom_env = Environment(
        loader=DictLoader(
            {
                "HTTPException.html": "<div>Custom error: {{ detail }}</div>",
            }
        ),
        autoescape=True,
    )

    qk.setup_error_handlers(app, template_env=custom_env)

    @app.get("/test")
    def test_route():
        raise HTTPException(status_code=400, detail="Test error")

    client = TestClient(app)
    response = client.get("/test", headers={"HX-Request": "true"})

    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
    assert "Custom error: Test error" in response.text


def test_different_http_status_codes(client):
    """Test various HTTP status codes return appropriate responses."""
    app = FastAPI()
    qk.setup_error_handlers(app)

    @app.get("/test-403")
    def forbidden():
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.get("/test-500")
    def server_error():
        raise HTTPException(status_code=500, detail="Internal error")

    test_client = TestClient(app)

    # Test 403
    response = test_client.get("/test-403", headers={"HX-Request": "true"})
    assert response.status_code == 403
    assert "Forbidden" in response.text

    # Test 500
    response = test_client.get("/test-500", headers={"HX-Request": "true"})
    assert response.status_code == 500
    assert "Internal error" in response.text
