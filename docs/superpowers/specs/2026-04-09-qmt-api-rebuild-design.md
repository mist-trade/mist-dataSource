# QMT 服务 API 重建设计

## Context

QMT 服务当前仅有 2 个端点（`/stocks`、`/market-data`）和 WebSocket。QMT.md 已更新包含完整 xtquant SDK 文档。本设计将 QMT 路由结构对齐 TDX，行情模块完整实现，交易模块仅在 adapter 层保留 NotImplementedError 存根。

## 设计原则

1. **与 TDX 路由结构一致** — 相同的路由分组、命名模式、响应格式
2. **行情完整，交易存根** — XtData 功能完整实现路由+adapter，XtTrader 仅 adapter 层 `raise NotImplementedError`
3. **QMT 有则实现，无则跳过** — value.py 和 client.py 是 TDX 专属功能，QMT 不创建对应路由
4. **复用已有 base adapter 方法** — 不重复造轮子，base.py 已有的存根直接在 QMTAdapter 中实现
5. **统一签名优先** — base.py 签名冲突时，选更完整/灵活的签名（倾向 QMT），TDX adapter 和路由同步调整

## 路由结构

与 TDX 对齐，创建 6 个路由文件（跳过 value.py 和 client.py）：

### 1. `qmt/routes/market.py` — 行情数据

前缀: `/api/qmt/market`，标签: `Market`

| 方法 | 路径 | 参数 | 对应 xtdata SDK |
|------|------|------|-----------------|
| GET | `/stock-list-in-sector` | `sector: str` | `get_stock_list_in_sector(sector)` |
| GET | `/market-data` | `stocks, fields, period, start_time, end_time, dividend_type, count, fill_data` | `get_market_data(...)` |
| GET | `/local-data` | `stocks, fields, period, start_time, end_time, dividend_type, count, fill_data` | `get_local_data(...)` |
| GET | `/full-tick` | `codes: str` | `get_full_tick(code_list)` |
| GET | `/full-kline` | `stocks, fields, period, start_time, end_time, count, dividend_type` | `get_full_kline(...)` |
| GET | `/divid-factors` | `stock_code, start_time, end_time` | `get_divid_factors(...)` |
| POST | `/download-history-data` | body: `{stock_code, period, start_time, end_time, incrementally}` | `download_history_data(...)` |
| POST | `/download-history-data2` | body: `{stock_list, period, start_time, end_time}` | `download_history_data2(...)` |
| GET | `/trading-dates` | `market, start_time, end_time, count` | `get_trading_dates(...)` |
| GET | `/trading-calendar` | `market, start_time, end_time` | `get_trading_calendar(...)` |
| GET | `/holidays` | 无 | `get_holidays()` |
| POST | `/download-holiday-data` | 无 | `download_holiday_data()` |
| GET | `/period-list` | 无 | `get_period_list()` |

TDX 有但 QMT 不实现的端点：`market-snapshot`、`gb-info`、`refresh-cache`、`refresh-kline`、`download-file`。

### 2. `qmt/routes/stock.py` — 合约信息

前缀: `/api/qmt/stock`，标签: `Stock`

| 方法 | 路径 | 参数 | 对应 xtdata SDK |
|------|------|------|-----------------|
| GET | `/instrument-detail` | `stock_code, iscomplete: bool` | `get_instrument_detail(stock_code, iscomplete)` |
| GET | `/instrument-type` | `stock_code` | `get_instrument_type(stock_code)` |

TDX 有但 QMT 不实现的端点：`stock-list`、`stock-info`、`report-data`、`more-info`、`relation`。

### 3. `qmt/routes/financial.py` — 财务数据

前缀: `/api/qmt/financial`，标签: `Financial`

| 方法 | 路径 | 参数 | 对应 xtdata SDK |
|------|------|------|-----------------|
| GET | `/financial-data` | `stocks, tables, start_time, end_time, report_type` | `get_financial_data(...)` |
| POST | `/download-financial-data` | body: `{stock_list, table_list}` | `download_financial_data(...)` |
| POST | `/download-financial-data2` | body: `{stock_list, table_list, start_time, end_time}` | `download_financial_data2(...)` |

TDX 有但 QMT 不实现的端点：`financial-data-by-date`、`gp-one-data`。

### 4. `qmt/routes/sector.py` — 板块管理

前缀: `/api/qmt/sector`，标签: `Sector`

| 方法 | 路径 | 参数 | 对应 xtdata SDK |
|------|------|------|-----------------|
| GET | `/sector-list` | 无 | `get_sector_list()` |
| POST | `/download-sector-data` | 无 | `download_sector_data()` |
| GET | `/index-weight` | `index_code` | `get_index_weight(index_code)` |
| POST | `/download-index-weight` | 无 | `download_index_weight()` |
| POST | `/create-sector-folder` | body: `{parent_node, folder_name, overwrite}` | `create_sector_folder(...)` |
| POST | `/create-sector` | body: `{parent_node, sector_name, overwrite}` | `create_sector(...)` |
| POST | `/add-sector` | body: `{sector_name, stock_list}` | `add_sector(...)` |
| POST | `/remove-stock-from-sector` | body: `{sector_name, stock_list}` | `remove_stock_from_sector(...)` |
| POST | `/remove-sector` | body: `{sector_name}` | `remove_sector(sector_name)` |
| POST | `/reset-sector` | body: `{sector_name, stock_list}` | `reset_sector(...)` |

TDX 有但 QMT 不实现的端点：`user-sectors`、`rename-sector`、`clear-sector`、`send-user-block`。QMT 比 TDX 多：`create-sector-folder`、`add-sector`、`remove-stock-from-sector`、`remove-sector`、`reset-sector`、`download-sector-data`、`download-index-weight`。

### 5. `qmt/routes/etf.py` — ETF/可转债/IPO

前缀: `/api/qmt/etf`，标签: `ETF`

| 方法 | 路径 | 参数 | 对应 xtdata SDK |
|------|------|------|-----------------|
| GET | `/cb-info` | `stock_code` | `get_cb_info(stockcode)` |
| POST | `/download-cb-data` | 无 | `download_cb_data()` |
| GET | `/ipo-info` | `start_time, end_time` | `get_ipo_info(start_time, end_time)` |
| GET | `/etf-info` | 无 | `get_etf_info()` |
| POST | `/download-etf-info` | 无 | `download_etf_info()` |

TDX 有但 QMT 不实现的端点：`kzz-info`（TDX 命名，QMT 用 `cb-info`）、`trackzs-etf-info`。

### 6. `qmt/routes/ws.py` — WebSocket

现有实现保持不变。

### 不创建的路由

| TDX 路由 | 原因 |
|----------|------|
| `value.py` | bkjy/gpjy/scjy 是 TDX 专属数据，QMT SDK 无对应 |
| `client.py` | exec-to-tdx 是 TDX 客户端控制，QMT 无对应 |

## Adapter 层变更

### QMTAdapter (`src/adapter/qmt/client.py`)

在现有 5 个方法基础上，新增以下行情方法实现（每个方法映射到一个 xtdata SDK 调用）：

**行情数据**: `get_local_data`, `get_full_tick`, `get_full_kline`, `get_divid_factors`, `download_history_data`, `download_history_data2`, `get_trading_dates`, `get_trading_calendar`, `get_holidays`, `download_holiday_data`, `get_period_list`

**合约信息**: `get_instrument_detail`, `get_instrument_type`

**财务数据**: `get_financial_data`, `download_financial_data`, `download_financial_data2`

**板块管理**: `get_sector_list`, `download_sector_data`, `get_index_weight`, `download_index_weight`, `create_sector_folder(parent_node, folder_name, overwrite)`, `create_sector(parent_node, sector_name, overwrite)`, `add_sector`, `remove_stock_from_sector`, `remove_sector`, `reset_sector`

**ETF/可转债**: `get_cb_info`, `download_cb_data`, `get_ipo_info(start_time, end_time)`, `get_etf_info`, `download_etf_info`

**交易存根** (NotImplementedError): `order_stock`, `order_stock_async`, `cancel_order_stock`, `cancel_order_stock_async`, `query_stock_asset`, `query_stock_orders`, `query_stock_order`, `query_stock_trades`, `query_stock_positions`, `query_stock_position`, `fund_transfer`, `query_credit_detail`, `query_stk_compacts`, `query_credit_subjects`, `query_credit_slo_code`, `query_credit_assure`, `query_account_infos`, `query_account_status`, `query_new_purchase_limit`, `query_ipo_data`, `query_com_fund`, `query_com_position`

### QMTMockAdapter (`src/adapter/mock/qmt_mock.py`)

为所有新增行情方法提供 mock 实现，交易存根保持 NotImplementedError。

### Base Adapter (`src/adapter/base.py`)

**需要修改签名的方法**（选更完整的签名，TDX 跟着改）：

| 方法 | 当前签名 | 修改后签名 | TDX 适配 |
|------|---------|-----------|----------|
| `create_sector` | `(self, name: str, stocks: list[str])` | `(self, parent_node: str, sector_name: str, overwrite: bool = True)` | TDX 路由改为传 `('', block_name, True)` |
| `get_ipo_info` | `(self, ipo_type: int = 0, ipo_date: int = 0)` | `(self, start_time: str = '', end_time: str = '')` | TDX 路由改为传日期字符串 |

TDX adapter 实现和 TDX 路由（`tdx/routes/sector.py`、`tdx/routes/etf.py`）需同步修改调用方式。

**需要新增的方法存根**（base.py 尚未定义的）：

**行情/数据**:
- `get_period_list()` → `list[str]`

**板块管理 (QMT 专属)**:
- `create_sector_folder(parent_node, folder_name, overwrite)` → `str`
- `add_sector(sector_name, stock_list)` → `None`
- `remove_stock_from_sector(sector_name, stock_list)` → `bool`
- `remove_sector(sector_name)` → `None`
- `reset_sector(sector_name, stock_list)` → `bool`

**ETF/可转债 (QMT 专属)**:
- `get_cb_info(stock_code)` → `dict`
- `download_cb_data()` → `None`
- `get_etf_info()` → `dict`
- `download_etf_info()` → `None`

**财务 (QMT 专属)**:
- `download_financial_data2(stock_list, table_list, start_time, end_time)` → `None`

**交易存根 (XtTrader，仅 NotImplementedError)**:
- `order_stock_async(stock_code, order_type, volume, price_type, price, strategy_name, order_remark)` → `int`
- `cancel_order_stock_async(order_id)` → `int`
- `query_stock_order(order_id)` → `dict | None`
- `query_stock_trades()` → `list[dict]`
- `query_stock_position(stock_code)` → `dict | None`
- `fund_transfer(transfer_direction, price)` → `int`
- `query_credit_detail()` → `dict`
- `query_stk_compacts()` → `list[dict]`
- `query_credit_subjects()` → `list[dict]`
- `query_credit_slo_code()` → `list[dict]`
- `query_credit_assure()` → `list[dict]`
- `query_account_infos()` → `list[dict]`
- `query_account_status()` → `list[dict]`
- `query_new_purchase_limit()` → `dict`
- `query_ipo_data()` → `list[dict]`
- `query_com_fund()` → `dict`
- `query_com_position()` → `list[dict]`

## main.py 注册

```python
from qmt.routes.etf import router as etf_router
from qmt.routes.financial import router as financial_router
from qmt.routes.market import router as market_router
from qmt.routes.sector import router as sector_router
from qmt.routes.stock import router as stock_router
from qmt.routes.ws import router as ws_router

app.include_router(market_router, prefix="/api/qmt", tags=["Market"])
app.include_router(stock_router, prefix="/api/qmt", tags=["Stock"])
app.include_router(financial_router, prefix="/api/qmt", tags=["Financial"])
app.include_router(sector_router, prefix="/api/qmt", tags=["Sector"])
app.include_router(etf_router, prefix="/api/qmt", tags=["ETF"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
```

## 路由约定

所有路由文件遵循 TDX 已建立的模式：

1. 模块级文档字符串，说明对应 QMT SDK
2. `_get_adapter()` 延迟导入 `qmt.main.qmt_adapter`
3. `router = APIRouter()` 模块级单例
4. 每个 endpoint 先 `adapter = _get_adapter()`，检查 `if not adapter: raise HTTPException(503)`
5. GET 用 `Query(...)` 参数，POST 用 Pydantic `BaseModel`
6. 逗号分隔列表参数用 `[s.strip() for s in stocks.split(",")]`
7. 响应统一 `{"data": ...}` 或 `{"stocks": [...], "count": int}`
8. 异常包裹为 `HTTPException(status_code=500, detail=str(e))`

## 端点汇总

| 路由文件 | 端点数 |
|----------|--------|
| market.py | 13 |
| stock.py | 2 |
| financial.py | 3 |
| sector.py | 10 |
| etf.py | 5 |
| ws.py | 1 (已有) |
| **合计** | **34** |

## 破坏性变更说明

当前 QMT 服务已有端点 `/api/qmt/market/stocks` 将被重命名为 `/api/qmt/market/stock-list-in-sector`。由于 QMT 服务尚未投入生产使用，不保留旧端点别名。

## 验证方式

```bash
# 启动服务
uv run uvicorn qmt.main:app --port 9002 --reload

# 验证端点
curl http://localhost:9002/api/qmt/market/stock-list-in-sector
curl http://localhost:9002/api/qmt/stock/instrument-detail?stock_code=600000.SH
curl http://localhost:9002/api/qmt/financial/financial-data?stocks=600000.SH&tables=Balance
curl http://localhost:9002/api/qmt/sector/sector-list
curl http://localhost:9002/api/qmt/etf/cb-info?stock_code=113001.SH
curl http://localhost:9002/api/qmt/market/trading-calendar?market=SH

# 查看 OpenAPI 文档
open http://localhost:9002/docs
```
