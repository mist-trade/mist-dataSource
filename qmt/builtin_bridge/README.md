# QMT Builtin Realtime Bridge 运维

`mist_qmt_bridge.py` 在大 QMT 内置 Python 3.6 环境中运行，是 QMT realtime 与
historical command gateway 的唯一 owner。

## 安装与升级

1. 操作员在大 QMT 客户端中手动放置或覆盖已注册的 `mist_qmt_bridge.py`。
2. 每次 bridge 版本变化都必须重新覆盖 installed file；datasource checkout 中的同名
   文件更新不代表终端已加载新版本。
3. 记录 installed path 和 SHA-256，然后让 QMT 终端重新加载脚本。
4. 确认 `GET http://127.0.0.1:9002/qmt/bridge/health` 的 owner、generation、build 和
   artifact identity 与本次发布一致。

Deploy、datasource manager 和 recovery workflow 不复制、注册、删除或升级 QMT
terminal bridge。它们只管理 datasource/终端生命周期并验证现有 installed bridge。
