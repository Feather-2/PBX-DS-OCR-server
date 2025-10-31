# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog. Dates in YYYY-MM-DD.

## [Unreleased]

### Added
- Tests: Minimal pytest suite covering:
  - Security utilities (`validate_task_id`, `validate_path_in_storage`)
  - Endpoints basic flow (upload, progress) and `result-images` path traversal
  - Token create/consume for local backend (single-use download)
  - `result-images` extension whitelist and optional subdirectory access
- Configuration (env/Settings):
  - `APP_IMAGE_MAX_WIDTH` / `APP_IMAGE_MAX_HEIGHT` to constrain rendered/single image size
  - `APP_RESULT_IMAGES_ALLOWED_EXTS` to control allowed file types for downloads
  - `APP_RESULT_IMAGES_FILENAME_MAXLEN` for download filename length limit
  - `APP_RESULT_IMAGES_ALLOW_SUBDIRS` to optionally allow subdirs under `images/`

### Changed
- PDF rendering now resizes pages to configured max size to avoid OOM
- Single-image inputs are further resized to settings’ max size
- Saving markdown_images now writes only the filename into `images/` to prevent path escape
- `result-images` endpoint enforces filename length and allowed extensions (configurable)

### Docs
- `.env.example` updated with new image/download security variables
- `README.md` documents new settings under "Images & downloads security"
- Docker Compose (cpu/gpu/vllm) and Helm `values.yaml` include the new envs

### Notes
- For quick health checks without model load: set `APP_ENABLE_DS_MODEL=false`
- Recommended to run tests via `uv`:
  - `uv pip install -r requirements.txt && uv pip install pytest httpx && uv run pytest -q`
