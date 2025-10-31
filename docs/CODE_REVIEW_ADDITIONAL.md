# 代码审查遗漏问题补充

**状态**: ✅ 已全部修复

## 🔴 严重问题 (Critical Issues) - ✅ 已修复

### 1. task_id 路径遍历风险 ✅

**位置**: 所有使用 `task_id` 的端点
- `app/api/v1/tasks.py`: `get_task`, `download_md`, `download_json`, `download_zip`, `delete_task`
- `app/api/v1/publish.py`: `publish_task`, `create_download_token`

**修复内容**:
- 创建了 `app/utils/security.py` 工具模块
- 添加 `validate_task_id()` 函数验证 UUID 格式
- 在所有使用 `task_id` 的端点添加验证

**修复后**:
```python
from ...utils.security import validate_task_id

@router.get("/tasks/{task_id}/result.md")
async def download_md(request: Request, task_id: str):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    # ...
```

### 2. 删除操作缺少路径安全验证 ✅

**位置**: `app/api/v1/tasks.py:214-223`

**修复内容**:
- 使用 `validate_path_in_storage()` 函数验证路径
- 确保删除路径在 `storage_root` 内

**修复后**:
```python
from ...utils.security import validate_path_in_storage

@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    root = validate_path_in_storage(settings.storage_root, Path(settings.storage_root) / task_id)
    # ...
```

---

## 🟡 重要问题 (Important Issues) - ✅ 已修复

### 3. Image.open 潜在的 DoS 风险 ✅

**位置**: `app/services/dsocr_model.py:339`, `app/services/dsocr_vllm.py:135`

**修复内容**:
- 添加 `safe_image_open()` 函数
- 限制图片最大尺寸为 8192x8192
- 添加 `MAX_IMAGE_SIZE` 常量

**修复后**:
```python
MAX_IMAGE_SIZE = (8192, 8192)  # 最大图片尺寸

def safe_image_open(path: Path) -> Image.Image:
    img = Image.open(path)
    if img.size[0] > MAX_IMAGE_SIZE[0] or img.size[1] > MAX_IMAGE_SIZE[1]:
        raise ValueError(f"Image too large: {img.size}, max: {MAX_IMAGE_SIZE}")
    return img.convert("RGB")

# 使用
img = safe_image_open(path)
```

### 4. vLLM 魔法数字未提取 ✅

**位置**: `app/services/dsocr_vllm.py:129`

**修复内容**:
- 从 `dsocr_model` 导入 `DEFAULT_DPI` 常量

**修复后**:
```python
from .dsocr_model import DEFAULT_DPI
pil_images = _pdf_to_images(path, dpi=DEFAULT_DPI, pages=pages)
```

### 5. Token 下载路径验证增强 ✅

**位置**: `app/api/v1/publish.py:101-116`

**修复内容**:
- 在 `download_by_token` 中添加路径验证

**修复后**:
```python
file_path = validate_path_in_storage(settings.storage_root, t.file_path)
```

---

## 🟢 改进建议 (Minor Improvements)

### 6. 异常处理过于宽泛
**位置**: 多处使用 `except Exception:`

**状态**: 部分改进（如 `validate_path_in_storage` 中使用 `from exc`）
**优先级**: P2 (可选)

### 7. 缺少请求超时处理
**位置**: `app/api/v1/tasks.py` 的下载端点

**状态**: 当前实现可接受
**优先级**: P2 (可选)

### 8. OSS 错误处理不完整
**位置**: `app/integrations/oss/client.py`

**状态**: 当前实现可接受
**优先级**: P2 (可选)

---

## 🔧 第三轮加固（配置化与端点收敛） ✅

**新增配置**（`app/config.py`）:
- `APP_IMAGE_MAX_WIDTH` / `APP_IMAGE_MAX_HEIGHT`: 渲染/单图最大宽高（带边界验证）
- `APP_RESULT_IMAGES_ALLOWED_EXTS`: 下载端点扩展名白名单（逗号分隔）
- `APP_RESULT_IMAGES_FILENAME_MAXLEN`: 下载文件名最大长度（带边界验证）
- `APP_RESULT_IMAGES_ALLOW_SUBDIRS`: 是否允许 `images/` 下子目录访问（默认 false）

**端点与流水线收敛**:
- `tasks.get_image`: 增加文件名长度与白名单校验；支持可选子目录（规范化+越界校验）。
- `pipeline`: 保存 `markdown_images` 时仅保留文件名，固定写入 `images/`，防止越界写入。
- `dsocr_model`: PDF 渲染和单图输入根据设置进行尺寸限幅，避免 OOM。

**测试**:
- 新增/扩展测试覆盖非法扩展名 403、合法 PNG 200、`ALLOW_SUBDIRS=true` 时子目录 200。

---

## 📊 总结

### 修复统计
- 🔴 **严重问题**: 2 个 ✅ 全部修复
- 🟡 **重要问题**: 3 个 ✅ 全部修复
- 🟢 **改进建议**: 3 个（可选，当前实现可接受）

### 新增文件
- `app/utils/security.py`: 安全工具函数模块

### 修复效果
1. **安全性大幅提升**: 所有路径操作都有验证，防止路径遍历攻击
2. **DoS 防护**: 图片尺寸限制防止内存耗尽
3. **代码一致性**: 统一使用常量，减少魔法数字

### 总体评价
所有遗漏的严重和重要问题已全部修复。代码安全性进一步提升。

---

## 🛠️ 补充修复与说明

### A. RateLimiter 线程生命周期管理（新增说明） ✅

位置: `app/main.py`, `app/security/rate_limit.py`

- 补充在应用 shutdown 钩子中显式调用 `rl_default.stop()` 与 `rl_login.stop()`，确保后台清理线程优雅退出。
- 影响：提升在容器/进程管理器环境中的可控性，避免线程残留影响关停时序。

代码片段:
```python
@app.on_event("shutdown")
async def on_shutdown():
    app.state.job_queue.stop()
    app.state.model_manager.stop()
    try:
        rl_default.stop()
    except Exception:
        pass
    try:
        rl_login.stop()
    except Exception:
        pass
```

---

## 🚀 部署与运维注意事项（补充）

### 1) 反向代理与真实客户端 IP
- 限流使用 `request.client.host` 作为键；若经由 Nginx/Ingress 等反向代理，请启用代理头支持（如 `uvicorn --proxy-headers` 并正确设置 `FORWARDED_ALLOW_IPS`），否则可能按代理节点 IP 进行限流。

### 2) 多实例环境的限流一致性
- 现有 `RateLimiter` 为进程内内存实现，仅对单实例有效；多副本不会共享计数。如需全局一致限流，建议在 API 网关层实现或引入集中式存储（如 Redis 限流）。

### 3) TTL 与内存占用权衡
- `RateLimiter` 默认 TTL 为 300 秒，后台每 60 秒清理一次。高并发时键空间可能短期增大；可根据实际负载缩短 TTL 或收敛键空间以控制内存。

### 4) 可观测性
- 建议对 429 返回进行指标上报与告警，追踪限流命中率与突发流量（例如在网关或应用层增加 counter）。

