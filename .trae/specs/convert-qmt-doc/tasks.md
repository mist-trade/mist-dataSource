# Tasks

- [x] Task 1: 生成 QMT.md 文件 - 模块概述与接口概述部分
  - [x] SubTask 1.1: 写入模块标题和介绍
  - [x] SubTask 1.2: 写入接口概述（运行逻辑、接口分类、常用类型说明、请求限制）

- [x] Task 2: 生成 QMT.md 文件 - 行情接口部分
  - [x] SubTask 2.1: 订阅类接口（subscribe_quote, subscribe_whole_quote, unsubscribe_quote, run）
  - [x] SubTask 2.2: 模型类接口（subscribe_formula, unsubscribe_formula, call_formula, call_formula_batch, generate_index_data）
  - [x] SubTask 2.3: 数据获取接口（get_market_data, get_local_data, get_full_tick, get_divid_factors, get_full_kline）
  - [x] SubTask 2.4: 数据下载接口（download_history_data, download_history_data2, download_history_contracts, download_holiday_data）
  - [x] SubTask 2.5: 其他行情接口（get_holidays, get_trading_calendar, download_cb_data, get_cb_info, get_ipo_info, get_period_list, download_etf_info, get_etf_info）

- [x] Task 3: 生成 QMT.md 文件 - 财务数据接口部分
  - [x] SubTask 3.1: get_financial_data, download_financial_data, download_financial_data2

- [x] Task 4: 生成 QMT.md 文件 - 基础行情信息部分
  - [x] SubTask 4.1: 合约信息接口（get_instrument_detail, get_instrument_type）
  - [x] SubTask 4.2: 交易日与板块接口（get_trading_dates, get_sector_list, get_stock_list_in_sector, download_sector_data）
  - [x] SubTask 4.3: 板块操作接口（create_sector_folder, create_sector, add_sector, remove_stock_from_sector, remove_sector, reset_sector）
  - [x] SubTask 4.4: 指数权重接口（get_index_weight, download_index_weight）

- [x] Task 5: 生成 QMT.md 文件 - 附录部分
  - [x] SubTask 5.1: 行情数据字段列表（tick, K线, 除权数据, l2quote, l2order, l2transaction, l2quoteaux, l2orderqueue）
  - [x] SubTask 5.2: 数据字典（证券状态、委托类型、委托方向、成交标志、现金替代标志）
  - [x] SubTask 5.3: 财务数据字段列表（Balance, Income, CashFlow, PershareIndex, Capital, Top10holder, Holdernum）
  - [x] SubTask 5.4: 合约信息字段列表
  - [x] SubTask 5.5: 代码示例（时间戳转换）

# Task Dependencies
- Task 2-5 依赖 Task 1（文件需要先创建并写入头部内容）
- Task 2-5 之间可以并行（不同章节）
