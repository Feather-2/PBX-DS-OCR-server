from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.security import validate_task_id, validate_path_in_storage
from fastapi import HTTPException


def test_validate_task_id_accepts_uuid():
    assert validate_task_id("123e4567-e89b-12d3-a456-426614174000") is True


@pytest.mark.parametrize(
    "val",
    ["", "../../etc/passwd", "not-a-uuid", None],
)
def test_validate_task_id_rejects_invalid(val):
    assert validate_task_id(val) is False


def test_validate_path_in_storage_allows_child(tmp_path: Path):
    root = tmp_path / "root"
    child = root / "a" / "b.txt"
    child.parent.mkdir(parents=True, exist_ok=True)
    child.write_text("ok", encoding="utf-8")
    # should not raise
    p = validate_path_in_storage(root, child)
    assert p.exists()


@pytest.mark.parametrize(
    "attack",
    ["..", "../x", "..\\x", "/etc/passwd"],
)
def test_validate_path_in_storage_blocks_traversal(tmp_path: Path, attack: str):
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(HTTPException) as ei:
        validate_path_in_storage(root, Path(root) / attack)
    assert ei.value.status_code == 403
