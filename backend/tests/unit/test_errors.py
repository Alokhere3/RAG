"""Unit tests for structured error handling."""

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.core.errors import AppException, register_error_handlers


def test_app_exception_formatting():
    """Ensure custom AppException returns canonical error structure."""
    test_app = FastAPI()
    register_error_handlers(test_app)

    @test_app.get("/error-test")
    def trigger_error():
        raise AppException(
            message="Test error message",
            code="TEST_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"field": "test"},
        )

    client = TestClient(test_app)
    response = client.get("/error-test")
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "TEST_ERROR"
    assert data["error"]["message"] == "Test error message"
    assert data["error"]["details"] == {"field": "test"}


def test_unhandled_exception_sanitization():
    """Ensure unhandled exceptions do not leak stack traces."""
    test_app = FastAPI()
    register_error_handlers(test_app)

    @test_app.get("/crash-test")
    def trigger_crash():
        raise RuntimeError("Secret internal failure with sensitive data")

    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.get("/crash-test")
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert data["error"]["message"] == "An unexpected error occurred."
    assert "Secret internal failure" not in response.text
