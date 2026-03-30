# 重命名 instance 文件夹计划

## 目标

将三个 instance 文件夹从无意义的编号命名改为语义化命名：

| 原名 | 新名 | 含义 |
|------|------|------|
| `instance1/` | `tdx/` | 通达信适配器服务 |
| `instance2/` | `qmt/` | miniQMT 适配器服务 |
| `instance3/` | `aktools/` | AKTools 封装服务 |

## 影响范围

共涉及 **13 个文件** 中的 **36 处引用**，按类别分类如下：

### 1. 文件夹内代码（需修改 import 路径）— 9 个文件

| 文件 | 修改内容 |
|------|----------|
| `instance1/main.py` → `tdx/main.py` | `from instance1.routes.*` → `from tdx.routes.*` |
| `instance1/routes/market.py` → `tdx/routes/market.py` | `from instance1.main import tdx_adapter` → `from tdx.main import tdx_adapter` |
| `instance1/routes/ws.py` → `tdx/routes/ws.py` | `from instance1.main import ws_manager` → `from tdx.main import ws_manager` |
| `instance1/services/tdx_service.py` → `tdx/services/tdx_service.py` | `from instance1.main import tdx_adapter` → `from tdx.main import tdx_adapter` |
| `instance2/main.py` → `qmt/main.py` | `from instance2.routes.*` → `from qmt.routes.*` |
| `instance2/routes/market.py` → `qmt/routes/market.py` | `from instance2.main import qmt_adapter` → `from qmt.main import qmt_adapter` |
| `instance2/routes/trade.py` → `qmt/routes/trade.py` | `from instance2.main import qmt_adapter` → `from qmt.main import qmt_adapter` |
| `instance2/routes/ws.py` → `qmt/routes/ws.py` | `from instance2.main import ws_manager` → `from qmt.main import ws_manager` |
| `instance2/services/qmt_service.py` → `qmt/services/qmt_service.py` | `from instance2.main import qmt_adapter` → `from qmt.main import qmt_adapter` |

### 2. instance3 内部代码 — 1 个文件

| 文件 | 修改内容 |
|------|----------|
| `instance3/main.py` → `aktools/main.py` | `from instance3 import PORT` → `from aktools import PORT` |

### 3. 测试文件 — 3 个文件

| 文件 | 修改内容 |
|------|----------|
| `tests/conftest.py` | `from instance1.main import ...` → `from tdx.main import ...`，`from instance2.main import ...` → `from qmt.main import ...` |
| `tests/integration/test_tdx_service.py` | `from instance1.services.*` → `from tdx.services.*`，`import instance1.*` → `import tdx.*` |
| `tests/integration/test_qmt_service.py` | `from instance2.services.*` → `from qmt.services.*`，`import instance2.*` → `import qmt.*` |

### 4. 脚本文件 — 1 个文件

| 文件 | 修改内容 |
|------|----------|
| `scripts/start_all.sh` | `uvicorn instance1.main:app` → `uvicorn tdx.main:app`，`uvicorn instance2.main:app` → `uvicorn qmt.main:app` |

### 5. 文档文件 — 2 个文件

| 文件 | 修改内容 |
|------|----------|
| `CLAUDE.md` | 所有 `instance1` → `tdx`，`instance2` → `qmt`，`instance3` → `aktools`（约 10 处） |
| `README.md` | 所有 `instance1` → `tdx`，`instance2` → `qmt`，`instance3` → `aktools`（约 6 处） |

## 执行步骤

### Step 1: 重命名文件夹（git mv）
```bash
git mv instance1 tdx
git mv instance2 qmt
git mv instance3 aktools
```

### Step 2: 修改 tdx/ 内部文件（4 个文件）
- `tdx/main.py` — 修改 2 处 import
- `tdx/routes/market.py` — 修改 1 处 import
- `tdx/routes/ws.py` — 修改 1 处 import
- `tdx/services/tdx_service.py` — 修改 1 处 import

### Step 3: 修改 qmt/ 内部文件（5 个文件）
- `qmt/main.py` — 修改 3 处 import
- `qmt/routes/market.py` — 修改 1 处 import
- `qmt/routes/trade.py` — 修改 1 处 import
- `qmt/routes/ws.py` — 修改 1 处 import
- `qmt/services/qmt_service.py` — 修改 1 处 import

### Step 4: 修改 aktools/ 内部文件（1 个文件）
- `aktools/main.py` — 修改 1 处 import
- `aktools/__init__.py` — 更新 docstring

### Step 5: 修改测试文件（3 个文件）
- `tests/conftest.py` — 修改 2 处 import
- `tests/integration/test_tdx_service.py` — 修改 2 处 import
- `tests/integration/test_qmt_service.py` — 修改 2 处 import

### Step 6: 修改脚本文件（1 个文件）
- `scripts/start_all.sh` — 修改 2 处 uvicorn 命令

### Step 7: 修改文档文件（2 个文件）
- `CLAUDE.md` — 全局替换 instance1→tdx, instance2→qmt, instance3→aktools
- `README.md` — 全局替换 instance1→tdx, instance2→qmt, instance3→aktools

### Step 8: 验证
- 运行 `ruff check .` 确保无 lint 错误
- 运行 `pyright src/ tdx/ qmt/ aktools/` 确保类型检查通过
- 运行 `uv run pytest` 确保测试通过
