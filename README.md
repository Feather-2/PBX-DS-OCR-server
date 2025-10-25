DeepSeek-OCR Server (FastAPI)

A high-performance document OCR server based on DeepSeek-OCR (Transformers),a serverized architecture with DS-OCR. Includes job queue, storage, and optional OSS publishing hooks, plus CI/CD via GitHub Actions to build Docker images (CPU and GPU).

Features
- FastAPI HTTP API with API key auth
- In-memory job queue with bounded capacity
- Storage layout: full.md, layout.json, images/
- GPU-aware concurrency gating (NVML) and idle model unload
- DeepSeek-OCR Transformers integration with PDF page rendering via PyMuPDF
- Dockerfiles for CPU and GPU; GitHub Actions builds and pushes to GHCR
- Lightweight Prometheus metrics at `/metrics` (enable via `APP_METRICS_ENABLED=true`)

Quickstart (local)
- Install dependencies: `pip install -r requirements.txt`
- Run server: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

Docker
CPU image:
- Build: `docker build -f Dockerfile.cpu -t dsocr-server:cpu .`
- Run: `docker run --rm -p 8000:8000 -e APP_API_KEYS="sk_xxx" dsocr-server:cpu`

GPU image (needs NVIDIA runtime):
- Build: `docker build -f Dockerfile.gpu -t dsocr-server:gpu .`
- Run: `docker run --rm --gpus all -p 8000:8000 -e APP_API_KEYS="sk_xxx" dsocr-server:gpu`

Endpoints
- POST `/v1/tasks` create from URL
- POST `/v1/tasks/upload` upload a file
- GET `/v1/tasks/{task_id}` progress + result links
- GET `/v1/tasks/{task_id}/result.md` merged markdown
- GET `/v1/tasks/{task_id}/result.json` aggregated JSON
- GET `/healthz` health
- GET `/metrics` Prometheus metrics

Pass `Authorization: Bearer <API_KEY>` if you set `APP_API_KEYS`.

Key Settings (env vars)
- `APP_API_KEYS`: comma-separated keys, e.g. `sk_xxx,sk_yyy`
- `APP_MAX_WORKERS`: default 1, DS model is heavy; use GPU + NVML gating
- `APP_FORCE_CPU`: `true` to force CPU mode
- `APP_DS_MODEL_PATH`: default `deepseek-ai/DeepSeek-OCR`
- `APP_DS_USE_FLASH_ATTN`: `true` to enable flash_attention_2
- `APP_DS_DTYPE`: `bfloat16|float16|float32` (default bfloat16)
- `APP_DS_BASE_SIZE`: 1024; `APP_DS_IMAGE_SIZE`: 640; `APP_DS_CROP_MODE`: true
- `APP_DS_PROMPT_OVERRIDE`: custom prompt text
- `APP_BACKEND`: `hf` (default) or `vllm` (requires vLLM installed)
- `APP_METRICS_ENABLED`: `true` to expose `/metrics`
- `APP_REQUIRE_AUTH`: `true` to enforce API key for all requests (default true)
- `APP_CONSOLE_ENABLED`: enable web console (default true)
- `APP_CONSOLE_PASSWORD`: protect web console with password; if set, `/` 等静态资源需先登录
- `APP_CONSOLE_SESSION_MAX_AGE`: cookie max-age seconds (default 86400)
- `APP_SESSION_SECRET`: optional HMAC secret for console session (random if unset)
- `APP_COOKIE_SECURE`: set `true` for HTTPS-only cookies in production

CI/CD (GitHub Actions)
- Workflow `.github/workflows/docker.yml` builds Docker Hub images:
  - `docker.io/feather2dev/pbx-dsocr-server:latest` (CPU)
  - `docker.io/feather2dev/pbx-dsocr-server:cpu`
  - `docker.io/feather2dev/pbx-dsocr-server:gpu`
  - `docker.io/feather2dev/pbx-dsocr-server:vllm`
- Set secrets in repository:
  - `DOCKERHUB_USERNAME`
  - `DOCKERHUB_TOKEN` (or password)
- Manual run supported via workflow_dispatch; tag pushes (`v*.*.*`) produce versioned tags.

Docker Hub
- Pull examples:
  - `docker pull feather2dev/pbx-dsocr-server:cpu`
  - `docker pull feather2dev/pbx-dsocr-server:gpu`
  - `docker pull feather2dev/pbx-dsocr-server:vllm`

Notes
- By default, transformers is installed; torch is unpinned to allow CPU/GPU variants.
- For best GPU performance, ensure CUDA-compatible torch and optional flash-attn are available in the environment.
- vLLM image (GPU, nightly):
  - Build: `docker build -f Dockerfile.vllm -t dsocr-server:vllm .`
  - Run: `docker run --rm --gpus all -p 8000:8000 -e APP_API_KEYS="sk_xxx" -e APP_BACKEND=vllm dsocr-server:vllm`

Monitoring (Compose)
- CPU example: `docker compose -f docker-compose.cpu.yml -f docker-compose.monitoring.yml --env-file .env.example up -d`
- GPU vLLM: `docker compose -f docker-compose.vllm.yml -f docker-compose.monitoring.yml --env-file .env.example up -d`
- Prometheus: http://localhost:9090 (scrapes dsocr:8000/metrics)
- Grafana: http://localhost:3000 (anonymous Viewer)
  - Dashboard auto-loaded: DSOCR Overview

Helm (Kubernetes)
- Edit values: deploy/helm/dsocr/values.yaml (set `image.repository` and `image.tag`)
- Install: `helm install dsocr deploy/helm/dsocr -n default`
- Enable ServiceMonitor (Prometheus Operator): set `serviceMonitor.enabled=true`
- GPU scheduling: set `resources.limits.nvidia.com/gpu: 1` in values and install NVIDIA device plugin

MCP (fastmcp)
- MCP 是对 REST API 的轻量封装，默认不单独运行服务；由你的 MCP 客户端以子进程启动。
- 代码：`mcp/dsocr_mcp.py`
- 依赖：`fastmcp` 已在 `requirements.txt`
- 环境变量：
  - `DSOCR_BASE_URL`（默认 `http://localhost:8000`）
  - `DSOCR_API_KEY`（必填，服务开启 `APP_REQUIRE_AUTH=true` 时需要）
  - `DSOCR_ENABLE_MCP=true|false`（默认 true，false 时脚本直接退出）
- 启动（独立测试）：
  - `DSOCR_BASE_URL=http://localhost:8000 DSOCR_API_KEY=sk_xxx python mcp/dsocr_mcp.py`
- 在 MCP 客户端（示例）：
  - 命令：`python`
  - 参数：`mcp/dsocr_mcp.py`
  - 环境：`DSOCR_BASE_URL=http://your-host:8000`，`DSOCR_API_KEY=sk_xxx`
  - 工具列表（示例）：`set_base_url`、`set_api_key`、`health`、`create_task_url`、`upload_file`、`task_status`、`get_result`
