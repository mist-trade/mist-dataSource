# TDX Builtin Realtime Bridge 运维

`mist_tdx_realtime_bridge.py` 在 TDX 终端环境中运行，是 realtime native SDK 的唯一
owner。脚本目标语法为 Python 3.7+，只依赖标准库与官方 `tqcenter`，没有 fake SDK、
自建线程、子进程或监听端口。

## 首次安装

1. 将脚本放入 `TDX_INSTALL_DIR/PYPlugins/user/`。
2. 在 TQ 策略管理器中注册脚本并启用自动运行。
3. 记录安装文件 SHA-256。
4. 确认 `mist-tdx-datasource` 已运行在 `http://127.0.0.1:9001`。

首次注册属于人工操作。后续 TDX 正常重启由终端自动启动已注册脚本；deploy 和
recovery workflow 不复制、注册或删除策略。

## 运行链路

脚本启动后：

1. `tq.initialize(__file__)`。
2. `POST /tdx/bridge/owner` 注册 owner。
3. 每秒 `poll` desired revision。
4. 用 `subscribe_hq` / `unsubscribe_hq` 收敛完整订阅集合。
5. 回调后调用 `get_market_snapshot` 并 POST native snapshot。
6. owner 被 fencing 后退出或重新注册，不与新实例并行写入。

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:9001/tdx/bridge/health
```

重点字段：

- `tdxRealtimeBridgeReady=true`
- `ownerId` 与 `ownerAgeSeconds`
- `desiredRevision == convergedRevision`
- `desiredSymbols == convergedSymbols`
- `lastFailureCode` 为空

Public `/health` 提供摘要；lease 和 evidence 细节只允许 loopback 访问。

## 停止与卸载

停止或卸载只能在 TQ 策略管理器中人工执行。停止后 owner 约 10 秒变 stale；新实例
经过 bounded takeover grace 接管，旧实例收到 lease fencing 后退出。不要让 Action
按 PID 强杀任意 Python 进程。

## 常见问题

- `tqcenter not available`：确认从 TQ 策略管理器启动，并检查 `numpy`、native DLL
  与 Python 环境。
- `OWNER_ACTIVE`：保持新实例重试，等待旧 owner stale/takeover；不要重复注册多个
  自动运行项。
- `NOT_CONVERGED`：检查 backend desired set、revision 和 TDX subscription 结果。
- `lease lost`：通常发生于 datasource 重启，脚本会重新注册。
- `native code is missing`：检查 symbol canonicalization；TDX native code 与
  `600030.SH` 等 product code 不得混用。
