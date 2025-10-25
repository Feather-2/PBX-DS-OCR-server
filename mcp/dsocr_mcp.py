from __future__ import annotations

"""
MCP server for DeepSeek-OCR service using fastmcp.

Tools:
- set_base_url(url)
- set_api_key(key)
- health()
- create_task_url(url, is_ocr=True, language='ch', enable_formula=True, enable_table=True, page_ranges=None)
- upload_file(path, is_ocr=True, language='ch', enable_formula=True, enable_table=True, page_ranges=None)
- task_status(task_id)
- get_result(task_id, kind='md'|'json'|'zip')

Environment variables:
- DSOCR_BASE_URL (default: http://localhost:8000)
- DSOCR_API_KEY  (optional)
"""

import os
from typing import Optional, Dict, Any

import requests
from fastmcp import FastMCP


app = FastMCP("dsocr-mcp")

BASE_URL = os.environ.get("DSOCR_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("DSOCR_API_KEY", None)


def _headers(required: bool = True) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if not API_KEY and required:
        raise RuntimeError("DSOCR_API_KEY not set; call set_api_key() or set env DSOCR_API_KEY")
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


@app.tool()
def set_base_url(url: str) -> str:
    """Set target dsocr base URL, e.g. http://localhost:8000"""
    global BASE_URL
    BASE_URL = url.rstrip("/")
    return BASE_URL


@app.tool()
def set_api_key(key: str) -> str:
    """Set Authorization Bearer token used for dsocr requests."""
    global API_KEY
    API_KEY = key.strip()
    return "ok"


@app.tool()
def health() -> Dict[str, Any]:
    """Get server health info."""
    resp = requests.get(f"{BASE_URL}/healthz", headers=_headers(required=True), timeout=15)
    resp.raise_for_status()
    return resp.json()


@app.tool()
def create_task_url(
    url: str,
    is_ocr: bool = True,
    language: str = "ch",
    enable_formula: bool = True,
    enable_table: bool = True,
    page_ranges: Optional[str] = None,
) -> Dict[str, Any]:
    """Create async task from URL and return {task_id, status}."""
    payload = {
        "url": url,
        "is_ocr": bool(is_ocr),
        "enable_formula": bool(enable_formula),
        "enable_table": bool(enable_table),
        "language": language,
        "page_ranges": page_ranges,
    }
    resp = requests.post(f"{BASE_URL}/v1/tasks", json=payload, headers=_headers(required=True), timeout=30)
    resp.raise_for_status()
    return resp.json()


@app.tool()
def upload_file(
    path: str,
    is_ocr: bool = True,
    language: str = "ch",
    enable_formula: bool = True,
    enable_table: bool = True,
    page_ranges: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload local file and create async task."""
    headers = _headers(required=True)
    with open(path, "rb") as f:
        files = {"file": (os.path.basename(path), f)}
        data = {
            "is_ocr": str(bool(is_ocr)).lower(),
            "enable_formula": str(bool(enable_formula)).lower(),
            "enable_table": str(bool(enable_table)).lower(),
            "language": language,
        }
        if page_ranges:
            data["page_ranges"] = page_ranges
        resp = requests.post(f"{BASE_URL}/v1/tasks/upload", files=files, data=data, headers=headers, timeout=120)
        resp.raise_for_status()
        return resp.json()


@app.tool()
def task_status(task_id: str) -> Dict[str, Any]:
    """Get task status and result URLs."""
    resp = requests.get(f"{BASE_URL}/v1/tasks/{task_id}", headers=_headers(required=True), timeout=30)
    resp.raise_for_status()
    return resp.json()


@app.tool()
def get_result(task_id: str, kind: str = "md") -> Any:
    """Fetch task result. kind=md|json|zip. Returns text for md/json; returns local path for zip."""
    kind = (kind or "md").lower().strip()
    if kind == "md":
        url = f"{BASE_URL}/v1/tasks/{task_id}/result.md"
        resp = requests.get(url, headers=_headers(required=True), timeout=60)
        resp.raise_for_status()
        return resp.text
    if kind == "json":
        url = f"{BASE_URL}/v1/tasks/{task_id}/result.json"
        resp = requests.get(url, headers=_headers(required=True), timeout=60)
        resp.raise_for_status()
        return resp.json()
    if kind == "zip":
        url = f"{BASE_URL}/v1/tasks/{task_id}/download.zip"
        resp = requests.get(url, headers=_headers(required=True), timeout=120)
        resp.raise_for_status()
        out = os.path.abspath(f"{task_id}.zip")
        with open(out, "wb") as f:
            f.write(resp.content)
        return {"path": out}
    return {"error": f"unknown kind: {kind}"}


if __name__ == "__main__":
    # Optional gating by env var
    if os.environ.get("DSOCR_ENABLE_MCP", "true").lower() != "true":
        raise SystemExit("MCP disabled by DSOCR_ENABLE_MCP!=true")
    app.run()
