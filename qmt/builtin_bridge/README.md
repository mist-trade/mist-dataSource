# QMT Builtin Realtime Bridge 运维

`mist_qmt_realtime_bridge.py` 在大 QMT 内置 Python 3.6 环境中运行，是 QMT realtime 与
historical command gateway 的唯一 owner。

## 安装与升级

1. 操作员在大 QMT 客户端中手动放置或覆盖已注册的 `mist_qmt_realtime_bridge.py`。
2. 每次 bridge 版本变化都必须重新覆盖 installed file；datasource checkout 中的同名
   文件更新不代表终端已加载新版本。
3. 由操作员自行维护 installed path 和文件版本，然后让 QMT 终端重新加载脚本。
4. 确认 `GET http://127.0.0.1:9002/qmt/bridge/health` 的 owner、generation 和
   `bridgeBuildId` 与本次发布一致。

大 QMT 策略编辑器可能不定义 Python `__file__`。这种运行方式下 bridge 仍须正常启动，
并将运行时 `bridgeArtifactSha256` 报告为 `unavailable`；该字段仅用于运行时诊断，不作为
发布门禁。installed path 和文件摘要不作为 datasource/deploy workflow 输入；自动化只
核验 owner、generation、`bridgeBuildId` 与协议行为。

Deploy、datasource manager 和 recovery workflow 不复制、注册、删除或升级 QMT
terminal bridge。它们只管理 datasource/终端生命周期并验证现有 installed bridge。
