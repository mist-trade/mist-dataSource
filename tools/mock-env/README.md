# Mock 环境（Phase 2：全链路本地验证）

macOS 本地全链路验证环境：真实 datasource（本机 uv 进程）+ backend mock 模式
（MIST_MOCK_MODE=true）+ monitoring exporter。`mock-drive.py` 扮演**终端**角色，
通过 datasource 的 bridge HTTP 路由注入真实 fixture 数据——链路是真实的，
只有终端是 mock 的。

**订阅不模拟**：backend 用 lifecycle=off + allowlist env（`TDX_REALTIME_ALLOWLIST` /
`QMT_REALTIME_ALLOWLIST`）走 mock 分支内存解析，WS 就绪后对 datasource 发**真实的**
`sync_subscriptions`（生产 coordinator 的同款机制）。注入器不碰订阅控制面，
只推数据帧。

## 拓扑

```
127.0.0.1
  redis 容器 (6379)  <- candle 封存
  tdx-datasource (9001) / qmt-datasource (9002)   uv run uvicorn（真实代码）
  mist-backend (8001)                              pnpm start:dev（MIST_MOCK_MODE=true）
  monitoring exporter (9109)                       go run ./cmd/exporter
mock-drive.py -> bridge HTTP（扮演终端）
```

## 前置依赖

- docker（仅 redis 容器，~50MB）
- uv（mist-datasource 仓）
- pnpm（mist 仓，需已 `pnpm install`）
- go（mist-monitoring 仓）

## 使用

```bash
# 1. 启动（redis 容器 + 三仓进程 + 等健康）
bash tools/mock-env/run-mock.sh

# 2. 注入帧（终端角色；--frames 0 = 持续注入，Ctrl-C 停）
python3 tools/mock-env/mock-drive.py --source tdx --frames 5
python3 tools/mock-env/mock-drive.py --source qmt --frames 5
python3 tools/mock-env/mock-drive.py --source tdx --frames 0 --rate 1   # 持续
python3 tools/mock-env/mock-drive.py --source tdx --pause 30            # 暂停观察停滞

# 3. 全链路验证（帧持续到达 + 聚合；sealed 需交易时段）
bash tools/mock-env/mock-verify.sh

# 4. 清理（杀进程 + 删 redis 容器）
bash tools/mock-env/stop-mock.sh
```

## 注入时间语义（重要）

- **TDX**：eventTime 取 bridge 的 `capturedAt`；**QMT**：eventTime 取 native 的
  `timetag`（注入器会把 `--captured-at` 同步写入 timetag）。
- 聚合器要求帧的 bucket 未结束（或结束 ≤ grace）——**非交易时段注入需用未来
  session 时间**（如 `--captured-at "2026-08-08T10:00:00+08:00"`，凌晨注入当天
  10:00 的 bucket 即可聚合，candidates 增长）。
- **sealed 是时间驱动的**：bucket 结束 + grace 后 due scanner 才封存。凌晨/周末
  无法验证 sealed——**交易时段**注入「当前运行中的 bucket」（不传 --captured-at
  即用当前时间）后，`mock-verify.sh` 会自动断言 sealed 增长（oldestLagMs > 0）。
- QMT 订阅已存在时（之前跑过），注入器探测式直接推帧，无需重新执行订阅命令。

## 调试

- 日志：`tools/mock-env/.mock-pids/*.log`（tdx-datasource / qmt-datasource /
  backend / monitoring）
- 三仓均可热重载/断点：backend 换 `pnpm start:debug`（node inspector），
  datasource 换 `uv run uvicorn --reload`，monitoring 直接 go run
- 直接看 redis：`redis-cli`（容器内 `docker exec -it mist-mock-redis redis-cli`）

## 已知事项

- **exporter candle 契约漂移**：backend candle health 响应包含 exporter 未知字段，
  exporter 报 `mist_realtime_candle_contract_violation_total{kind="unexpected_field"}`、
  `mist_component_up{component="realtime-candles"}=0`。这是 monitoring 仓 schema
  未同步（生产同样存在），需 monitoring 仓单独 change 修复；mock-env 不改 exporter 代码。
- macOS Python 的 urllib 默认读系统代理设置——注入器/verify 已显式禁用代理，
  否则本地请求可能拿到过期响应。

## 验证闭环（跑通标准）

1. 注入 → backend 收到帧（tdx/qmt 诊断 lastAcceptedAt 持续更新）
2. `mock-verify.sh` 链路断言全绿（帧到达 + 聚合候选 + exporter 可达）
3. 交易时段：due 到期后 sealed 增长（verify 自动断言）
4. 暂停注入 → sealed 停滞 → 恢复注入 → 自愈

## 边界

- 不跑 prometheus（直接 curl exporter /metrics 验证）
- 不做镜像 build、不做 compose、不碰 mist-deploy
- 指标断言矩阵待指标梳理计划完成后扩展（本轮只锁链路级）
- 订阅不模拟（终端/收敛/desired 管理都是真机行为；backend 订阅走真实 sync）
