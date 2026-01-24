# camera_operation API 文档

对应代码：`backend/api/device_management/camera_operation.py`

## 基本信息

- **FastAPI Router 前缀**：`/api/device`
- **Tag**：`camera_operation`
- **返回通用字段**：大多数接口返回 JSON，通常包含 `success: bool`，失败时 FastAPI 会返回 HTTP 4xx/5xx 并带 `detail`。

---

# 1) 从数据库加载摄像头到内存

- **函数名**：`load_cameras_from_db`
- **功能描述**：从 pickle 数据库读取所有 Camera 实例加载到内存注册表。
- **接口地址**：`POST /api/device/cameras/load_from_db`
- **接收变量**：无
- **返回格式**：
  - `success: bool`
  - `message: str`
  - `loaded_count: int`
- **返回实例**：

```json
{
  "success": true,
  "message": "成功从数据库加载 3 个摄像头",
  "loaded_count": 3
}
```

---

# 2) 保存内存摄像头到数据库

- **函数名**：`save_cameras_to_db`
- **功能描述**：将当前内存中的所有 Camera 实例保存到 pickle 数据库。
- **接口地址**：`POST /api/device/cameras/save_to_db`
- **接收变量**：无
- **返回格式**：
  - `success: bool`
  - `message: str`
  - `saved_count: int`
- **返回实例**：

```json
{
  "success": true,
  "message": "成功保存 3 个摄像头到数据库",
  "saved_count": 3
}
```

---

# 3) 添加摄像头

- **函数名**：`add_camera`
- **功能描述**：根据请求体信息创建 Camera 并加入内存注册表。
- **接口地址**：`POST /api/device/cameras/add`
- **接收变量**：JSON Body（`CameraData` 或 dict），必填字段：
  - `camera_id: str`
  - `camera_ip: str`
  - `camera_name: str`
  - `camera_location: (float, float)`
  - `accessible: bool`
  - `protocal_in: str`（输入流地址，通常是 RTSP/HTTP URL）
  - `protocal_out: str`（输出协议/地址）

- **返回格式**：
  - `success: bool`
  - `message: str`
  - `camera_id: str`
  - `camera_name: str`

- **返回实例**：

```json
{
  "success": true,
  "message": "成功添加摄像头: cam_001",
  "camera_id": "cam_001",
  "camera_name": "LobbyCam"
}
```

---

# 4) 删除摄像头

- **函数名**：`remove_camera`
- **功能描述**：根据 `camera_id` 从内存注册表移除摄像头。
- **接口地址**：`DELETE /api/device/cameras/remove/{camera_id}`
- **接收变量**：Path 参数
  - `camera_id: str`
- **返回格式**：
  - `success: bool`
  - `message: str`
  - `camera_id: str`（存在时返回）

- **返回实例**（成功删除）：

```json
{
  "success": true,
  "message": "成功删除摄像头: cam_001",
  "camera_id": "cam_001"
}
```

- **返回实例**（摄像头不存在）：

```json
{
  "success": true,
  "message": "摄像头cam_001不存在"
}
```

---

# 5) 获取单个摄像头状态（并执行一次 ping/流可用性检测）

- **函数名**：`get_camera_status`
- **功能描述**：对指定摄像头执行一次 `ping_camera` 检测，并返回该摄像头基本状态。
- **接口地址**：`GET /api/device/cameras/one_status/{camera_id}`
- **接收变量**：Path 参数
  - `camera_id: str`
- **返回格式**：
  - `success: bool`
  - `camera_status: str | object`

其中 `camera_status` 在成功时为对象：
  - `camera_id: str`
  - `camera_name: str`
  - `is_online: bool`
  - `camera_ip: str`
  - `camera_location: (float, float)`
  - `status_code: int`

- **返回实例**（成功）：

```json
{
  "success": true,
  "camera_status": {
    "camera_id": "cam_001",
    "camera_name": "LobbyCam",
    "is_online": false,
    "camera_ip": "192.168.1.10",
    "camera_location": [0.0, 0.0],
    "status_code": -1
  }
}
```

- **返回实例**（未找到摄像头）：

```json
{
  "success": false,
  "camera_status": "没有找到摄像头：cam_404"
}
```

---

# 6) 获取所有摄像头状态（并执行一次全量 ping/流可用性检测）

- **函数名**：`get_all_cameras_status`
- **功能描述**：对所有摄像头执行一次 `ping_all_cameras`，并返回状态列表。
- **接口地址**：`GET /api/device/cameras/status`
- **接收变量**：无
- **返回格式**：
  - `success: bool`
  - `total: int`
  - `cameras: list<object>`

其中 `cameras[i]`：
  - `camera_id: str`
  - `camera_name: str`
  - `is_online: bool`
  - `camera_ip: str`
  - `camera_location: (float, float)`
  - `status_code: int`

- **返回实例**：

```json
{
  "success": true,
  "total": 2,
  "cameras": [
    {
      "camera_id": "cam_001",
      "camera_name": "LobbyCam",
      "is_online": true,
      "camera_ip": "192.168.1.10",
      "camera_location": [0.0, 0.0],
      "status_code": 0
    },
    {
      "camera_id": "cam_002",
      "camera_name": "GateCam",
      "is_online": false,
      "camera_ip": "192.168.1.11",
      "camera_location": [1.0, 1.0],
      "status_code": -1
    }
  ]
}
```

---

# 7) 获取所有摄像头列表（不 ping）

- **函数名**：`list_all_cameras`
- **功能描述**：列出当前内存中的所有摄像头基础信息（不执行 ping）。
- **接口地址**：`GET /api/device/cameras/list`
- **接收变量**：无
- **返回格式**：
  - `success: bool`
  - `total: int`
  - `cameras: list<object>`

其中 `cameras[i]`：
  - `camera_id: str`
  - `camera_name: str`
  - `camera_ip: str`
  - `camera_location: (float, float)`
  - `accessible: bool`
  - `protocal_in: str`
  - `protocal_out: str`

- **返回实例**：

```json
{
  "success": true,
  "total": 1,
  "cameras": [
    {
      "camera_id": "cam_001",
      "camera_name": "LobbyCam",
      "camera_ip": "192.168.1.10",
      "camera_location": [0.0, 0.0],
      "accessible": false,
      "protocal_in": "rtsp://user:pass@192.168.1.10/stream1",
      "protocal_out": "http://example/live"
    }
  ]
}
```

---

# 8) 获取摄像头统计信息

- **函数名**：`get_camera_stats`
- **功能描述**：获取注册表统计信息（总数/在线/离线、db_path）。
- **接口地址**：`GET /api/device/cameras/stats`
- **接收变量**：无
- **返回格式**：
  - `success: bool`
  - `total: int`
  - `online: int`
  - `offline: int`
  - `db_path: str`

- **返回实例**：

```json
{
  "success": true,
  "total": 3,
  "online": 1,
  "offline": 2,
  "db_path": "../../DataBase/cameras_db.pkl"
}
```

---

# 9) 启动后台定期健康检查

- **函数名**：`start_cameras_healthcheck`
- **功能描述**：启动后台任务，按固定周期对所有摄像头执行一次可用性检测（内部会区分 RTSP/HTTP）。
- **接口地址**：`POST /api/device/cameras/healthcheck/start`
- **接收变量**：Query 参数
  - `interval_s: float = 30.0`（检查周期秒）
  - `timeout_s: float = 5.0`（单个摄像头检查超时秒）
- **返回格式**：
  - `success: bool`
  - `running: bool`
  - `interval_s: float`
  - `timeout_s: float`

- **返回实例**：

```json
{
  "success": true,
  "running": true,
  "interval_s": 30.0,
  "timeout_s": 5.0
}
```

---

# 10) 停止后台定期健康检查

- **函数名**：`stop_cameras_healthcheck`
- **功能描述**：停止后台定期健康检查任务。
- **接口地址**：`POST /api/device/cameras/healthcheck/stop`
- **接收变量**：无
- **返回格式**：
  - `success: bool`
  - `running: bool`

- **返回实例**：

```json
{
  "success": true,
  "running": false
}
```

---

# 11) 查询后台定期健康检查状态

- **函数名**：`get_cameras_healthcheck_status`
- **功能描述**：查询后台定期健康检查是否在运行。
- **接口地址**：`GET /api/device/cameras/healthcheck/status`
- **接收变量**：无
- **返回格式**：
  - `success: bool`
  - `running: bool`

- **返回实例**：

```json
{
  "success": true,
  "running": true
}
```

---

# 12) 手动触发一次全量健康检查

- **函数名**：`run_cameras_healthcheck_once`
- **功能描述**：立即对所有摄像头执行一次可用性检测（不依赖后台周期任务）。
- **接口地址**：`POST /api/device/cameras/healthcheck/run_once`
- **接收变量**：Query 参数
  - `timeout_s: float = 5.0`
- **返回格式**：
  - `success: bool`
  - `total: int`
  - `results: list<any>`（每个元素通常为 dict，包含 `Camera_Id`、`Online` 等；异常时可能是异常对象或 dict，取决于底层实现）

- **返回实例**：

```json
{
  "success": true,
  "total": 2,
  "results": [
    {"Camera_Name": "LobbyCam", "Camera_Id": "cam_001", "Online": true},
    {"Camera_Id": "cam_002", "Online": false, "error": "TimeoutError: ..."}
  ]
}
```
