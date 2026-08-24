from fastapi.testclient import TestClient

from main import app


def test_demo_ui_serves_html() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "workflow-copilot demo UI" in response.text
    assert "Generate workflow plan" in response.text
    assert "Save plan" in response.text
    assert "Acting user" in response.text
    assert "Submit for approval" in response.text
    assert "Audit trail" in response.text
    assert "Recent saved plans" in response.text
    assert "Progress:" in response.text
    assert "Updated:" in response.text
