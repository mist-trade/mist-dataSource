# Mist-Datasource

数据源桥接层 - 将通达信 (TDX) 和 miniQMT 的本地 SDK 接口包装为 HTTP/WebSocket 服务。

## 项目定位

mist-datasource 是 NestJS 后端的**数据源桥接层**，核心职责：

- 将通达信 (TDX) 和 miniQMT 的本地 SDK 接口包装为 HTTP/WebSocket 服务
- 通过 WebSocket 将实时行情推送到 NestJS 后端
- 托管 AKTools HTTP 服务（后续迁移）

**不是**一个通用的 WebSocket 微服务平台，而是一个**适配器层 (Adapter Layer)**。

## 架构总览

```
通达信终端 (Windows)          miniQMT 客户端 (Windows)
      │                              │
      │ tqcenter SDK                 │ xtquant SDK
      ▼                              ▼
┌─────────────┐              ┌─────────────┐
│  Instance 1 │              │  Instance 2 │
│  TDX Adapter│              │  QMT Adapter│
│  Port: 9001 │              │  Port: 9002 │
│  FastAPI     │              │  FastAPI     │
└──────┬──────┘              └──────┬──────┘
       │ WebSocket                  │ WebSocket
       ▼                            ▼
┌──────────────────────────────────────────┐
│           NestJS Backend                 │
│  mist(8001) / saya(8002) / chan(8008)    │
└──────────────────────────────────────────┘
```

## 技术栈

| 项目 | 选型 | 原因 |
|------|------|------|
| Python | 3.12 | xtquant 最高支持 3.12；tqcenter 支持 3.7-3.14 |
| 包管理 | uv | 速度快，lockfile 可靠 |
| 框架 | FastAPI | 异步支持好，自动 OpenAPI 文档 |
| 配置 | pydantic-settings | 类型安全的环境变量管理 |
| 代码质量 | ruff + pyright + pre-commit | 统一工具链 |
| 测试 | pytest + pytest-asyncio | 异步测试支持 |

## 端口规划

| Instance | 端口 | 用途 |
|----------|------|------|
| Instance 1 | 9001 | TDX 适配器 |
| Instance 2 | 9002 | QMT 适配器 |
| Instance 3 | 8080 | AKTools |

## 快速开始

### 安装依赖

```bash
# 使用 uv (推荐)
pip install uv
uv sync

# 或使用 pip
pip install -e ".[dev]"
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件配置参数
```

### 启动服务

```bash
# macOS 开发 - 单独启动
uv run uvicorn instance1.main:app --port 9001 --reload
uv run uvicorn instance2.main:app --port 9002 --reload
```

### 运行测试

```bash
uv run pytest
```

## 跨平台策略

### macOS 开发
- TDX/QMT 适配器自动切换为 Mock 模式（`APP_ENV=development`）
- Mock 返回随机数据，WebSocket 定期推送模拟行情
- 可以正常开发/测试 REST API 和 WebSocket 推送逻辑

### Windows 生产
- `APP_ENV=production`，使用真实 SDK
- 前置条件：通达信终端 / MiniQMT 客户端已启动
- 使用 NSSM 注册为 Windows 服务

## 目录结构

```
mist-datasource/
├── src/                      # 共享核心代码
│   ├── core/                 # 配置、日志、异常
│   ├── adapter/              # 适配器层
│   └── ws/                   # WebSocket 管理
├── instance1/                # TDX 适配器服务 (Port 9001)
├── instance2/                # QMT 适配器服务 (Port 9002)
├── instance3/                # AKTools (Port 8080)
├── tests/                    # 测试
└── scripts/                  # 启动脚本
```

## API 文档

启动服务后访问：
- Instance 1: http://localhost:9001/docs
- Instance 2: http://localhost:9002/docs

## 许可证

BSD-3-Clause
