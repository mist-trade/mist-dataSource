# Mock 环境（Phase 2：全链路本地验证）

macOS 本地全链路验证环境：真实 datasource（本机 uv 进程）+ backend mock 模式
（MIST_MOCK_MODE=true）+ OpenObserve（OTLP 后端）。`mock-drive.py` 扮演**终端**角色，
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
  openobserve (5080)                              docker container（OTLP 后端）
mock-drive.py -> bridge HTTP（扮演终端）
```

## 前置依赖

- docker（仅 redis 容器，~50MB）
- uv（mist-datasource 仓）
- pnpm（mist 仓，需已 `pnpm install`）

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
  `timetag`（注入器会把 `--captured-at` 同步写入 timetag）。`--captured-at-step`（默认 1s）
  让每帧时间递增——相同 eventTime 会被聚合器按 duplicate 拒绝，导致单帧候选、量额 delta 为 0。
- **backend 时钟偏移**（`MIST_MOCK_CLOCK_OFFSET_MS`，见 `.env.mock`）：把 backend 的
  Clock 前移，墙钟驱动的封存（due/finalize/vwap 校验）在非交易时段自然推进。
  用法：`offset = 目标clock时间 - 当前真实时间` → 写入 `.env.mock` → 重启 backend →
  注入 `--captured-at <目标时间>`（目标 bucket 的开始）。**重启 backend 会有 recovery_gap**
  （聚合从下一个完整 bucket 开始）；backen 重启后 baseline 从 manifest 恢复，**注入量额
  base 必须 ≥ 已封存桶的累计值**（`--volume-base/--amount-base`），否则触发 counter_reset。
- **可复现的异常 case**（2026-08-08 实测）：
  - sealed 封存 / no_snapshot discard / counter_reset discard / vwap 坏桶（HIL THROW）
  - A2 断流形态（注入停、datasource 活着 → backend freshness 停滞）
  - E2 重连恢复（backend 重启 → 重连 → sync → sealed 继续；source isolation）
  - C1 QMT observation 卡死（构造 `context-rebuild-observation.json` + `.processing` 并存
    → qmt 启动抛 `ambiguous QMT context rebuild observation state`；修复=清文件重启）

## 调试

- 日志：`tools/mock-env/.mock-pids/*.log`（tdx-datasource / qmt-datasource /
  backend / openobserve）
- 三仓均可热重载/断点：backend 换 `pnpm start:debug`（node inspector），
  datasource 换 `uv run uvicorn --reload`，openobserve 是 docker 容器
- 直接看 redis：`redis-cli`（容器内 `docker exec -it mist-mock-redis redis-cli`）

## 已知事项

- **QMT subscription journal**：datasource 的 journal 默认路径是 Windows 生产机的
  `F:\quant\MistAPI\...`——run-mock.sh 已用 `MIST_QMT_SUBSCRIPTION_JOURNAL_PATH` 隔离到
  `.mock-pids/`（runtime 目录，gitignore）。早期版本未隔离时 journal 曾落到仓库根目录，
  已删除。
- macOS Python 的 urllib 默认读系统代理设置——注入器/verify 已显式禁用代理，
  否则本地请求可能拿到过期响应。

## 验证闭环（跑通标准）

1. 注入 → backend 收到帧（tdx/qmt 诊断 lastAcceptedAt 持续更新）
2. `mock-verify.sh` 链路断言全绿（帧到达 + 聚合候选 + openobserve 可达）
3. 交易时段：due 到期后 sealed 增长（verify 自动断言）
4. 暂停注入 → sealed 停滞 → 恢复注入 → 自愈

## 边界

- 不跑 prometheus/exporter（直接 curl openobserve API 验证遥测）
- 不做镜像 build、不做 compose、不碰 mist-deploy
- 指标断言矩阵待指标梳理计划完成后扩展（本轮只锁链路级）
- 订阅不模拟（终端/收敛/desired 管理都是真机行为；backend 订阅走真实 sync）
