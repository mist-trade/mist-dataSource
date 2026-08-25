# tdx/builtin_bridge — 通达信内置实时桥接脚本

`mist_tdx_realtime_bridge.py` 运行于 Windows 通达信终端的 Python 插件环境中，是 TDX 实时原生 SDK（`tqcenter`）的唯一持有者（Owner）。

---

## 🎯 模块职责

- **原生行情驱动**：通过通达信 `tqcenter` SDK 的 `subscribe_hq` / `unsubscribe_hq` 接口管理行情订阅。
- **快照直推**：捕获实时行情 Snapshot 并通过 TCP 直推至容器网关（`:9003`），由容器转为 WebSocket 分发。
- **租约与防并发 (Fencing)**：向 `tdx-datasource` 注册 Owner 租约并定期心跳，防止多终端冲突。

---

## 📦 安装与运维步骤

1. **部署路径**：将 `mist_tdx_realtime_bridge.py` 复制到通达信目录 `TDX_INSTALL_DIR/PYPlugins/user/`。
2. **注册启用**：在通达信“TQ 策略管理器”中注册该脚本并勾选“自动运行”。
3. **版本更新**：代码更新时由操作员手动覆盖文件并触发 TDX 重新加载。

---

## 🩺 诊断与健康检查

```powershell
# 查询宿主侧 Bridge 状态
Invoke-RestMethod http://127.0.0.1:9001/tdx/bridge/health
```

- 核心检查项：`bridge.ready == true`、`desiredRevision == convergedRevision`、无 `lastFailureCode`。
