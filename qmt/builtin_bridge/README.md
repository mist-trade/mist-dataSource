# qmt/builtin_bridge — 原生大 QMT 内置桥接脚本

`mist_qmt_realtime_bridge.py` 运行于原生大 QMT（ThinkTrader）内置的 Python 3.6 环境中，是 QMT 实时订阅与历史数据提取的唯一桥接者。

---

## 🎯 模块职责

- **原生行情订阅**：调用 QMT 官方 SDK 的 `subscribe_quote` / `subscribe_whole_quote` 回调接收全推行情。
- **Thin Callback 高性能转发**：极简回调将数据压入内存队列，由主线程排队并通过 TCP 直推容器（`:9004`）。
- **历史数据查询代理**：响应容器网关派发的 `get_market_data_ex` 命令，提取原生历史 K 线并返回。

---

## 📦 安装与运维步骤

1. **部署路径**：在原生大 QMT 策略编辑器中导入或覆盖 `mist_qmt_realtime_bridge.py`。
2. **运行环境要求**：大 QMT 内置 Python 3.6（严格禁止使用 3.7+ 语法，如 `from __future__ import annotations` 等）。
3. **版本更新**：代码变更后在 QMT 界面重新编译并启动脚本。

---

## 🩺 诊断与健康检查

```powershell
# 查询宿主侧 QMT Bridge 状态
Invoke-RestMethod http://127.0.0.1:9002/qmt/bridge/health
```

- 核心检查项：`ready == true`、`ownerAgeSeconds` 正常刷新、无未捕获异常。
