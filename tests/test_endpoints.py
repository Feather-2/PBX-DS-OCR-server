from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(app_instance):
    with TestClient(app_instance) as c:
        yield c


def test_create_task_upload_and_get_result_paths(client, tmp_storage_root):
    # Upload a tiny fake PDF (just bytes, page count may be 0; pipeline will likely fail later, but endpoints should work)
    files = {"file": ("a.pdf", b"%PDF-1.4\n%EOF", "application/pdf")}
    r = client.post("/v1/tasks/upload", files=files)
    assert r.status_code == 200
    data = r.json()
    task_id = data["task_id"]

    # get task progress (may be queued or processing quickly)
    r2 = client.get(f"/v1/tasks/{task_id}")
    assert r2.status_code in (200,)
    prog = r2.json()
    assert prog["task_id"] == task_id

    # image path traversal blocked
    r3 = client.get(f"/v1/tasks/{task_id}/result-images/..%2F..%2Fetc%2Fpasswd")
    assert r3.status_code in (403, 404)  # 403 invalid filename or 404 not found

    # Disallowed extension rejected
    # create a fake .txt file in images dir then try to fetch it
    from app.storage import get_job_paths
    paths = get_job_paths(tmp_storage_root, task_id)
    (paths.images_dir).mkdir(parents=True, exist_ok=True)
    (paths.images_dir / "note.txt").write_text("x", encoding="utf-8")
    r4 = client.get(f"/v1/tasks/{task_id}/result-images/note.txt")
    assert r4.status_code == 403


def test_token_flow_local_backend(client, app_instance, tmp_storage_root):
    # Arrange a fake job output
    from app.storage import new_job
    storage_root = Path(tmp_storage_root)
    task_id, paths = new_job(str(storage_root), filename="input.pdf")
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    (paths.output_dir / "full.md").write_text("hello", encoding="utf-8")

    # Create token for md
    r = client.post(f"/v1/tasks/{task_id}/tokens", params={"kind": "md"})
    assert r.status_code == 200
    token = r.json()["data"]["token"]

    # Download by token
    r2 = client.get(f"/v1/download/{token}")
    assert r2.status_code == 200
    assert r2.text == "hello"

    # Token should decrement; consume until exhausted
    r3 = client.get(f"/v1/download/{token}")
    # default max_downloads=1, so second use should be invalid/expired
    assert r3.status_code in (404,)
