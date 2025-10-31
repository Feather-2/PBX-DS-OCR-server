from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def tmp_storage_root():
    d = tempfile.mkdtemp(prefix="dsocr_tests_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def app_instance(tmp_storage_root):
    # Prepare isolated env for settings before creating app
    os.environ["APP_REQUIRE_AUTH"] = "false"
    os.environ["APP_CONSOLE_ENABLED"] = "false"
    os.environ["APP_STORAGE_ROOT"] = tmp_storage_root
    os.environ["APP_TOKEN_STORE_PATH"] = str(Path(tmp_storage_root) / "tokens.json")
    os.environ.setdefault("APP_RATE_LIMIT_ENABLED", "false")  # avoid rate limit flakiness in tests

    from app.main import create_app
    from app.security.tokens import TokenManager
    from contextlib import contextmanager

    app = create_app()
    # Ensure settings reflect our test env explicitly
    app.state.settings.require_auth = False
    app.state.settings.console_enabled = False
    app.state.settings.storage_root = tmp_storage_root
    app.state.settings.token_store_path = os.environ["APP_TOKEN_STORE_PATH"]
    # Recreate token manager with updated settings
    app.state.token_manager = TokenManager(app.state.settings)

    # Stub out model inference to avoid heavy ML deps during tests
    class _DummyRes:
        def markdown(self):
            return {"markdown_texts": "ok", "markdown_images": {}}

        def save_to_json(self, save_path: str):
            pass

        def save_to_markdown(self, save_path: str):
            pass

        def json(self):
            return {"res": {"text": "ok"}, "page_index": 1}

    class _DummyModel:
        def predict(self, input_arg: str, **kwargs):
            return [_DummyRes()]

    @contextmanager
    def _dummy_ctx(*args, **kwargs):
        yield _DummyModel()

    app.state.model_manager.inference_context = _dummy_ctx  # type: ignore[attr-defined]
    return app
