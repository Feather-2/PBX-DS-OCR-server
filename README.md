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

CI/CD (GitHub Actions)
- Workflow `.github/workflows/docker.yml` builds `ghcr.io/<owner>/dsocr-server:latest` (CPU) and `:gpu` tags.
- Requires repository Packages permission (granted by default to GITHUB_TOKEN in this workflow).

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
