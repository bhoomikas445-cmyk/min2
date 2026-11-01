"""
Unit tests for PALIMPSEST REST API Endpoints
Covers API routes, input validation, document uploads, and error responses.
"""

import io
import pytest
from app import create_app
from config import TestConfig
from models import db, Project


@pytest.fixture
def client():
    app = create_app(TestConfig)
    with app.test_client() as c:
        with app.app_context():
            yield c


def test_api_project_creation_and_listing(client):
    """Test project creation API and validation."""
    # Empty name should fail with 400
    res = client.post("/api/projects", json={"name": ""})
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False

    # Valid creation
    res2 = client.post("/api/projects", json={
        "name": "API Test Project",
        "description": "Integration testing",
        "objective": "API Validation",
        "token_budget": 2048,
    })
    assert res2.status_code == 201
    p_data = res2.get_json()
    assert p_data["success"] is True
    project_id = p_data["project"]["id"]

    # List projects
    res3 = client.get("/api/projects")
    assert res3.status_code == 200
    list_data = res3.get_json()
    assert any(p["id"] == project_id for p in list_data["projects"])


def test_api_message_ingestion_and_processing(client):
    """Test message addition and memory processing through API."""
    # Create project
    p_res = client.post("/api/projects", json={"name": "Process Test"})
    proj_id = p_res.get_json()["project"]["id"]

    # Create conversation
    c_res = client.post("/api/conversations", json={"project_id": proj_id, "title": "Session 1"})
    conv_id = c_res.get_json()["conversation"]["id"]

    # Add message
    m_res = client.post(f"/api/conversations/{conv_id}/messages", json={
        "role": "user",
        "content": "Mandatory database constraint: Must use PostgreSQL.",
    })
    assert m_res.status_code == 201

    # Process memories
    proc_res = client.post("/api/memory/process", json={"project_id": proj_id, "version_label": "V1 Specs"})
    assert proc_res.status_code == 200
    proc_data = proc_res.get_json()
    assert proc_data["processed_count"] == 1
    assert proc_data["version"]["short_hash"] is not None


def test_api_document_upload_validation(client):
    """Test document upload API with file extension validation."""
    p_res = client.post("/api/projects", json={"name": "Upload Test"})
    proj_id = p_res.get_json()["project"]["id"]
    c_res = client.post("/api/conversations", json={"project_id": proj_id, "title": "Upload Session"})
    conv_id = c_res.get_json()["conversation"]["id"]

    # Disallowed extension (e.g. .exe)
    data = {
        "file": (io.BytesIO(b"malicious payload"), "script.exe")
    }
    res = client.post(f"/api/conversations/{conv_id}/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "Invalid file extension" in res.get_json()["error"]

    # Valid markdown upload
    valid_data = {
        "file": (io.BytesIO(b"# Architecture Requirements\n\nMust use PostgreSQL with async SQLAlchemy.\n\nAll routes use /api/v1/."), "spec.md")
    }
    res_valid = client.post(f"/api/conversations/{conv_id}/upload", data=valid_data, content_type="multipart/form-data")
    assert res_valid.status_code == 201
    assert res_valid.get_json()["paragraphs_ingested"] >= 2


def test_api_context_reconstruct_endpoint(client):
    """Test context reconstruction endpoint."""
    p_res = client.post("/api/projects", json={"name": "Recon Test"})
    proj_id = p_res.get_json()["project"]["id"]

    res = client.post("/api/context/reconstruct", json={
        "project_id": proj_id,
        "query": "Which database?",
        "token_budget": 500,
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "package" in data
