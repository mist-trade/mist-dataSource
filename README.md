# Mist Datasource

Mist Datasource 通过两个独立 FastAPI container，把 Windows TDX 与大 QMT
terminal bridge 的本地能力暴露给 Mist。它不是跨 provider 的统一数据模型，也不
负责交易、账户、持仓、委托或成交。

## 当前架构

```text
TDX Desktop
  official POST :17709 ---------------------> TDX datasource /v1/* :9001
  builtin bridge /tdx/bridge/* ------------> /ws/realtime/tdx/*

QMT Desktop builtin Python
  stdlib HTTP polling /qmt/bridge/* --------> QMT datasource :9002
  get_market_data_ex(subscribe=False) ------> /v1/bars/query
  get_full_tick (builtin realtime) ----------> /ws/realtime/qmt/*

TDX/QMT datasource WebSocket --------------> Mist backend leader
```

- TDX 非实时接口走官方 `:17709`，datasource 进程不加载 `tqcenter`。
- TDX realtime 默认 `builtin`，`off` 仅用于受控回滚；终端脚本调用官方
  `get_market_snapshot`。
- QMT 历史 bars 通过 full-QMT 内置 Python 执行 `get_market_data_ex`，不读取 DAT。
- TDX/QMT 在 `off` 时都保留 `/health` 与历史查询，但不创建或挂载对应 realtime
  gateway/collector 与 route。
- 生产路径禁止已退役的轻量客户端/API package、外部 QMT SDK、bridge WebSocket、
  内置脚本线程和子进程。

## Python 边界

| 运行位置 | 兼容目标 | 当前说明 |
|---|---|---|
| Datasource container | Python 3.12 | FastAPI、Pydantic、HTTP client |
| TDX builtin bridge | Python 3.7+ 语法 | 当前实机使用 Python 3.12.10 + `tqcenter` |
| QMT builtin bridge | Python 3.6 语法 | 只使用标准库 HTTP polling |

QMT 脚本不得使用 `from __future__ import annotations`、`dict[...]`、`X | Y` 等
Python 3.6 不支持的语法。

## 端口与接口

#### TDX `:9001`

| 类型 | 路径 |
|---|---|
| Health | `GET /health` |
| Bars | `POST /v1/bars/query` |
| Snapshot | `POST /v1/snapshots/query` |
| Sector | `POST /v1/sectors/query` |
| Finance | `POST /v1/finance/financial-data/query` |
| Instrument | `POST /v1/instruments/convertible-bonds/query` |
| Other | reference、report、formula 与 operator raw `/v1/*` |

- `POST /tdx/bridge/owner|poll|result|snapshot`（loopback）
- `GET /tdx/bridge/health`（loopback）
- `GET /tdx/bridge/evidence/{symbol}`（loopback、bounded evidence）
- `WS /ws/realtime/tdx/{client_id}`

已删除的 `/api/tdx/*` 和 `/ws/quote/*` 不得恢复。

#### QMT `:9002`

- `GET /health`
- `POST /v1/bars/query`，返回 native `data.marketData`
- `POST /qmt/bridge/owner|commands|poll|result`
- `GET /qmt/bridge/commands/{command_id}|health`
- QMT realtime 启用时：`GET /qmt/realtime/health` 与
  `WS /ws/realtime/qmt/{client_id}`

QMT `/v1/bars/query` 使用官方 snake_case 字段，不接受 TDX camelCase 或
`provider` selector。

## 本地开发

```bash
uv sync --frozen --python 3.12
uv run uvicorn tdx.main:app --port 9001 --reload
uv run uvicorn qmt.main:app --port 9002 --reload
```

macOS 只能验证合成 fixture、ASGI、contract 和 guardrail，不得把 mock 结果写成
Windows native HIL。

## 生产镜像

同一个不可变镜像分别启动两个进程：

```bash
docker build -t mist-datasource:test .
docker run --rm mist-datasource:test \
  uvicorn tdx.main:app --host 0.0.0.0 --port 9001
docker run --rm mist-datasource:test \
  uvicorn qmt.main:app --host 0.0.0.0 --port 9002
```

生产 Compose 使用非 root 用户、只读 root filesystem 和 loopback-only port
publish。QMT journal 必须 bind mount 到
`/var/lib/mist-datasource/qmt/subscription-journal.jsonl`。

## 验证

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run python scripts/export_openapi.py --all
```

确定性 OpenAPI 产物：

- `docs/references/tdx-openapi.json`
- `docs/references/tdx-openapi-builtin.json`
- `docs/references/qmt-openapi-off.json`
- `docs/references/qmt-openapi-builtin.json`

Windows smoke、部署和恢复统一从 `mist-deploy` 执行；本仓库不维护第二套生产部署
脚本。

## Windows 与容器生命周期

- `tdx-datasource` 与 `qmt-datasource` 是两个独立 Compose service。
- Datasource restart 使用对应 `Manage Windows ... Datasource` workflow，并且
  只重启所选 source。
- 桌面终端 restart 使用对应 `Recover Windows ... Runtime` workflow。
- Deploy/runner 不复制、注册、删除或强杀终端 bridge。
- TDX bridge 首次由操作员放入 `PYPlugins/user` 并注册自动运行；每次 bridge 版本变化
  仍由操作员手动覆盖 installed file，并让 TDX 重新加载。
- QMT bridge 同样由操作员在大 QMT 内置 Python 环境中手动覆盖；datasource checkout
  中的 `qmt/builtin_bridge/mist_qmt_realtime_bridge.py` 更新不代表终端已加载新版本。
- QMT 登录全自动，recovery 不执行登录点击；终端重启后只会加载操作员已覆盖的已注册
  bridge。
- WinSW datasource 部署已经删除；容器切换完成后的故障只允许 repair-forward。

TDX bridge 运维见 [`tdx/builtin_bridge/README.md`](tdx/builtin_bridge/README.md)，QMT
bridge 运维见 [`qmt/builtin_bridge/README.md`](qmt/builtin_bridge/README.md)。
生产基线与盘中/盘后边界见 `mist` 仓库
`docs/production-baseline-verification.md`。

## 许可证

BSD-3-Clause
