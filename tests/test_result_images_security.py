from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(app_instance):
    with TestClient(app_instance) as c:
        yield c


def test_result_images_rejects_disallowed_extensions(client, tmp_storage_root):
    # Arrange: create a fake job with an images directory and a .txt file
    from app.storage import new_job

    task_id, paths = new_job(tmp_storage_root, filename="input.pdf")
    paths.images_dir.mkdir(parents=True, exist_ok=True)
    txt = paths.images_dir / "not_image.txt"
    txt.write_text("x", encoding="utf-8")

    # Act: try to download the .txt through the endpoint
    r = client.get(f"/v1/tasks/{task_id}/result-images/not_image.txt")

    # Assert: blocked by extension whitelist (403)
    assert r.status_code == 403


def test_result_images_allows_png(client, tmp_storage_root):
    # Arrange: create a fake job with a png file
    from app.storage import new_job

    task_id, paths = new_job(tmp_storage_root, filename="input.pdf")
    paths.images_dir.mkdir(parents=True, exist_ok=True)
    png = paths.images_dir / "ok.png"
    # minimal PNG header + IHDR + IEND (not strictly validated by FileResponse)
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    # Act: request the file
    r = client.get(f"/v1/tasks/{task_id}/result-images/ok.png")

    # Assert: served
    assert r.status_code == 200


def test_result_images_allow_subdirs_when_enabled(client, app_instance, tmp_storage_root, monkeypatch):
    # Enable subdirs in settings
    app_instance.state.settings.result_images_allow_subdirs = True

    from app.storage import new_job
    task_id, paths = new_job(tmp_storage_root, filename="input.pdf")
    sub = paths.images_dir / "a" / "b"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # Directly access with subdirectory path
    r = client.get(f"/v1/tasks/{task_id}/result-images/a/b/x.png")
    assert r.status_code == 200
