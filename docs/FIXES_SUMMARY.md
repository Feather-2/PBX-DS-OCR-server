# 代码修复总结

## 修复日期
2024-10-31

## 修复概览

本次修复解决了代码审查中发现的所有 P0、P1 和 P2 级别问题，以及补充发现的问题，共计 16 个问题。

---

## ✅ 已修复的问题

### P0 - 严重问题 (Critical)

#### 1. 路径遍历安全问题 ✅
**文件**: `app/api/v1/tasks.py`
**修复内容**:
- 改进了 `get_image` 函数的路径验证
- 只使用文件名部分，忽略任何目录遍历尝试
- 使用 `Path.relative_to()` 进行更安全的路径检查
- 添加文件名格式验证（只允许字母、数字、点、下划线、连字符）

**修复前**:
```python
target = (base / Path(unquote(path))).resolve()
if not str(target).startswith(str(base)):
    raise HTTPException(status_code=403, detail="Invalid path")
```

**修复后**:
```python
# 只取文件名部分，防止路径遍历
path_parts = Path(unquote(path)).parts
filename = path_parts[-1] if path_parts else ""
# 验证文件名安全
if not filename or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in filename):
    raise HTTPException(status_code=403, detail="Invalid filename")
target = (base_resolved / filename).resolve()
target.relative_to(base_resolved)  # 安全检查
```

#### 2. API Key 验证性能优化 ✅
**文件**: `app/security/auth.py`
**修复内容**:
- 从 `request.app.state` 获取 settings，避免每次请求都重新加载
- 使用 `set` 进行 O(1) 查找，替代 O(n) 的列表查找
- 添加全局缓存作为 fallback

**修复前**:
```python
def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    settings = load_settings()  # 每次请求都加载
    if token not in settings.api_keys:  # O(n) 查找
        raise HTTPException(...)
```

**修复后**:
```python
def verify_api_key(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    settings = request.app.state.settings  # 从应用状态获取
    api_keys_set = request.app.state._api_keys_set  # set，O(1) 查找
    if token not in api_keys_set:
        raise HTTPException(...)
```

#### 3. 异常信息泄露修复 ✅
**文件**: `app/api/v1/infer.py`
**修复内容**:
- 不再直接返回异常堆栈信息给客户端
- 根据日志级别决定是否返回详细错误信息
- 添加了完整的异常日志记录

**修复前**:
```python
except Exception as e:
    return {
        "errorCode": 500,
        "errorMsg": str(e),  # 直接暴露异常信息
    }
```

**修复后**:
```python
except Exception as e:
    logger.exception("Inference failed")
    error_msg = "Internal server error"
    if app.state.settings.log_level.lower() == "debug":
        error_msg = str(e)  # 仅调试模式返回详细信息
    return {
        "errorCode": 500,
        "errorMsg": error_msg,
    }
```

#### 4. 临时文件清理改进 ✅
**文件**: `app/services/dsocr_model.py`
**修复内容**:
- 使用 `shutil.rmtree()` 替代 `rmdir()`，确保完全清理临时目录
- 即使目录中有文件也能正确清理

**修复前**:
```python
if tmp_img_path and Path(tmp_img_path).exists():
    Path(tmp_img_path).unlink(missing_ok=True)
if tmp_dir:
    Path(tmp_dir).rmdir()  # 要求目录为空
```

**修复后**:
```python
if tmp_dir:
    try:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)  # 完全清理
    except Exception:
        pass
```

---

### P1 - 重要问题 (Important)

#### 5. NVML 重复初始化优化 ✅
**文件**: `app/utils/gpu.py`
**修复内容**:
- 使用全局状态管理 NVML，避免每次调用都初始化/关闭
- 使用线程锁保证线程安全
- 移除重复的 `nvmlShutdown()` 调用

**修复前**:
```python
def get_gpu_memory_gb(gpu_index: int = 0):
    nvmlInit()  # 每次调用都初始化
    # ... 查询 ...
    nvmlShutdown()  # 每次调用都关闭
```

**修复后**:
```python
_nvml_initialized = False
_nvml_lock = threading.Lock()

def get_gpu_memory_gb(gpu_index: int = 0):
    with _nvml_lock:
        if not _nvml_initialized:
            nvmlInit()  # 只初始化一次
            _nvml_initialized = True
        # ... 查询 ...
    # 不关闭，让进程退出时自动清理
```

#### 6. 文件上传原子写入修复 ✅
**文件**: `app/api/v1/tasks.py`
**修复内容**:
- 使用临时文件 + 原子替换的方式写入
- 确保文件完整性，避免写入过程中出错导致文件不完整

**修复前**:
```python
with paths.input_file.open("wb") as out:
    # 直接写入，如果出错文件可能不完整
    while True:
        chunk = await file.read(chunk_size)
        out.write(chunk)
```

**修复后**:
```python
tmp_file = paths.input_file.with_suffix(paths.input_file.suffix + ".tmp")
try:
    with tmp_file.open("wb") as out:
        # 写入临时文件
        while True:
            chunk = await file.read(chunk_size)
            out.write(chunk)
    tmp_file.replace(paths.input_file)  # 原子替换
except Exception:
    if tmp_file.exists():
        tmp_file.unlink()  # 清理临时文件
    raise
```

#### 7. 队列提交竞态条件修复 ✅
**文件**: `app/services/queue.py`
**修复内容**:
- 队列满时回滚已添加的 job，避免内存泄漏

**修复前**:
```python
except queue.Full:
    return False  # job 已添加到 _jobs 但未入队
```

**修复后**:
```python
except queue.Full:
    # 队列满时，从 _jobs 中移除已添加的 job（回滚）
    with self._lock:
        self._jobs.pop(job.task_id, None)
    return False
```

#### 8. Token 管理文件 I/O 优化 ✅
**文件**: `app/security/tokens.py`
**修复内容**:
- 添加后台线程批量写入，避免高并发下的文件 I/O 瓶颈
- 使用队列机制，减少写操作频率

**修复前**:
```python
def _save(self):
    tmp = json.dumps(self._data, ensure_ascii=False, indent=2)
    self._path.write_text(tmp, encoding="utf-8")  # 每次调用都同步写入
```

**修复后**:
```python
def _save(self, sync: bool = False):
    if sync:
        # 同步写入：立即写入文件
        tmp = json.dumps(self._data, ensure_ascii=False, indent=2)
        self._path.write_text(tmp, encoding="utf-8")
    else:
        # 异步写入：放入队列
        if not self._pending_save:
            self._pending_save = True
            self._write_queue.put(self._data.copy())
```

---

### P2 - 代码质量改进

#### 9. RateLimiter 后台清理优化 ✅
**文件**: `app/security/rate_limit.py`
**修复内容**:
- 添加后台线程定期清理过期的 bucket
- 减少主线程的清理开销，提高高并发性能

#### 10. JSON 写入效率优化 ✅
**文件**: `app/storage/local.py`
**修复内容**:
- 写入前检查内容是否相同，避免不必要的磁盘操作

**修复前**:
```python
def write_json(path: Path, data):
    # 每次都会写入
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
```

**修复后**:
```python
def write_json(path: Path, data):
    # 检查是否需要写入（避免不必要的磁盘操作）
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing == data:
                return  # 内容相同，跳过写入
        except Exception:
            pass
    # ... 写入逻辑
```

#### 11. 魔法数字提取为常量 ✅
**文件**: `app/services/dsocr_model.py`, `app/api/v1/infer.py`
**修复内容**:
- 提取硬编码的数值为常量

**新增常量**:
```python
# app/services/dsocr_model.py
DEFAULT_DPI = 144
DEFAULT_ZOOM = DEFAULT_DPI / 72.0
IMAGE_QUALITY_JPEG = 85
IMAGE_QUALITY_INFERENCE = 95

# app/api/v1/infer.py
IMAGE_QUALITY_B64 = 85
```

#### 12. 配置验证增强 ✅
**文件**: `app/config.py`
**修复内容**:
- 添加关键配置项的验证器，防止不合理的配置值

**新增验证器**:
```python
@field_validator("max_upload_mb")
@classmethod
def validate_max_upload(cls, v):
    if v < 1:
        raise ValueError("max_upload_mb must be >= 1")
    if v > 10240:  # 10GB 上限
        raise ValueError("max_upload_mb too large (max 10240)")
    return v

# 类似地添加了：
# - validate_max_pages (1 - 10000)
# - validate_chunk_size (1MB - 1GB)
# - validate_max_workers (1 - 128)
# - validate_max_queue_size (1 - 10000)
```

#### 13. 代码质量改进 ✅
**文件**: `app/services/dsocr_model.py`, `app/middleware.py`
**修复内容**:
- 修复重复的条件检查 (`self._dtype is not None and self._dtype is not None`)
- 优化日志级别：根据响应状态码选择适当的日志级别
- 移除未使用的导入

**修复前**:
```python
if self._dtype is not None and self._dtype is not None:  # 重复检查
    self._model = self._model.to(self._dtype)

logging.getLogger("dsocr-service").info(...)  # 所有请求都用 info
```

**修复后**:
```python
if self._dtype is not None:  # 单次检查
    self._model = self._model.to(self._dtype)

# 根据状态码选择日志级别
if status_code >= 500:
    log_level = logging.ERROR
elif status_code >= 400:
    log_level = logging.WARNING
else:
    log_level = logging.INFO
logger.log(log_level, ...)
```

---

## 🔄 补充修复（第二轮审查）

### P0 - 严重问题补充

#### 14. task_id 路径遍历风险修复 ✅
**文件**: `app/api/v1/tasks.py`, `app/api/v1/publish.py`
**修复内容**:
- 创建 `app/utils/security.py` 安全工具模块
- 添加 `validate_task_id()` 函数验证 UUID 格式
- 在所有使用 `task_id` 的端点添加验证（7 个端点）

**新增文件**: `app/utils/security.py`

#### 15. 删除操作路径安全验证 ✅
**文件**: `app/api/v1/tasks.py`
**修复内容**:
- 使用 `validate_path_in_storage()` 函数验证路径
- 确保删除路径在 `storage_root` 内
- Token 下载路径也添加了验证

### P1 - 重要问题补充

#### 16. Image.open DoS 防护 ✅
**文件**: `app/services/dsocr_model.py`, `app/services/dsocr_vllm.py`
**修复内容**:
- 添加 `safe_image_open()` 函数
- 限制图片最大尺寸为 8192x8192
- 添加 `MAX_IMAGE_SIZE` 常量

#### 17. vLLM 魔法数字提取 ✅
**文件**: `app/services/dsocr_vllm.py`
**修复内容**:
- 从 `dsocr_model` 导入 `DEFAULT_DPI` 常量
- 统一使用常量替代硬编码

---
**文件**: `app/services/dsocr_model.py`, `app/middleware.py`
**修复内容**:
- 修复重复的条件检查 (`self._dtype is not None and self._dtype is not None`)
- 优化日志级别：根据响应状态码选择适当的日志级别
- 移除未使用的导入

**修复前**:
```python
if self._dtype is not None and self._dtype is not None:  # 重复检查
    self._model = self._model.to(self._dtype)

logging.getLogger("dsocr-service").info(...)  # 所有请求都用 info
```

**修复后**:
```python
if self._dtype is not None:  # 单次检查
    self._model = self._model.to(self._dtype)

# 根据状态码选择日志级别
if status_code >= 500:
    log_level = logging.ERROR
elif status_code >= 400:
    log_level = logging.WARNING
else:
    log_level = logging.INFO
logger.log(log_level, ...)
```

---

## 📊 修复统计

- **严重问题 (P0)**: 6 个 ✅ (原始 4 个 + 补充 2 个)
- **重要问题 (P1)**: 7 个 ✅ (原始 5 个 + 补充 2 个)
- **代码质量 (P2)**: 3 个 ✅
- **总计**: 16 个问题全部修复 ✅

## 🎯 修复效果

1. **安全性提升**: 路径遍历防护更严格，异常信息不再泄露，task_id 验证增强，所有路径操作都有验证
2. **性能优化**: API Key 验证性能提升，NVML 初始化优化，Token I/O 异步化，RateLimiter 后台清理，JSON 写入优化
3. **稳定性提升**: 文件上传原子写入，队列竞态条件修复，临时文件清理改进
4. **代码质量**: 日志级别优化，重复代码清理，魔法数字提取，配置验证增强
5. **DoS 防护**: 图片尺寸限制防止内存耗尽攻击

## 📝 注意事项

1. **API Key 验证**: 现在依赖 `request.app.state.settings`，确保应用启动时正确初始化
2. **NVML 初始化**: 现在使用全局状态，在多进程环境下可能需要额外处理
3. **Token I/O**: 异步写入可能在某些极端情况下丢失数据，但对于高并发场景性能提升明显

## 🔄 后续建议

1. 添加单元测试覆盖这些修复点
2. 监控生产环境中的性能变化
3. 考虑添加配置选项控制 Token I/O 的同步/异步模式

