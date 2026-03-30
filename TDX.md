# 快速开始

```python
# 策略说明：如果运行时间点价格高出昨收5%, 则进入涨幅选股板块，否则清空该板块
import pandas as pd
import numpy as np
from datetime import datetime
from tqcenter import tq 

# 初始化tq
tq.initialize(__file__)

# 1. 基础配置
batch_codes = tq.get_stock_list_in_sector('通达信88')     # 目标板块
start_time = "20251025"                                  # 数据起始日期
target_end = datetime.now().strftime("%Y%m%d")           # 数据结束日期（当前日期）
target_gain = 5.0                                        # 目标涨幅（%），可修改
target_block_name = 'ZFXG'                               # 目标自定义板块简称

# 2. 获取并整理收盘价数据
df_real = tq.get_market_data(
    field_list=['Close'],
    stock_list=batch_codes,
    start_time=start_time,
    end_time=target_end,
    dividend_type='front',  # 前复权
    period='1d',            # 日线
    fill_data=True          # 填充缺失数据
)
# 转换为「日期×股票代码」的收盘价宽表
close_df = tq.price_df(df_real, 'Close', column_names=batch_codes)

# 3. 核心：计算当日相较于昨日的涨幅（%）
# 昨日收盘价（向下平移1行）
prev_close = close_df.shift(1)
# 计算涨幅：(当日收盘价 - 昨日收盘价) / 昨日收盘价 × 100%
daily_gain = (close_df - prev_close) / prev_close * 100

# 4. 筛选符合条件的股票（最新交易日涨幅超target_gain%）
latest_date = daily_gain.index[-1]              # 最新交易日
latest_daily_gain = daily_gain.loc[latest_date] # 每只股票最新交易日的涨幅
# 筛选条件：涨幅 > target_gain%（排除NaN，避免数据异常）
target_stocks = latest_daily_gain[latest_daily_gain > target_gain].sort_values(ascending=False)
target_stocks_list = target_stocks.index.tolist()  # 提取符合条件的股票代码列表

# 5. 结果输出与自定义板块操作（可按需注释）
print(f"\n=== 筛选结果（当日涨幅＞{target_gain}%）===")
if not target_stocks.empty:
    # ===================== 模块1：打印筛选结果 =====================
    print("【模块1：打印筛选结果】")
    print(f"符合条件的股票共 {len(target_stocks)} 只：")
    print(f"{'股票代码':<12} {'昨日收盘价':<12} {'当日收盘价':<12} {'当日涨幅':<10}")
    print("-" * 50)
    for stock_code, gain in target_stocks.items():
        prev_price = prev_close.loc[latest_date, stock_code]
        curr_price = close_df.loc[latest_date, stock_code]
        print(f"{stock_code:<12} {prev_price:<12.2f} {curr_price:<12.2f} {gain:<.2f}%")
    print("-" * 50)

    # ===================== 模块2：添加至自定义板块 =====================
    try:
        print("【模块2：自定义板块操作】")
        tq.send_user_block(block_code=target_block_name, stocks=target_stocks_list, show=True)
        print(f"✅ 已成功将股票添加至自定义板块「{target_block_name}」")
    except Exception as e:
        print(f"❌ 添加自定义板块失败：{e}")
    print("-" * 50)



else:
    # ===================== 模块1：打印空结果 =====================
    print("【模块1：打印筛选结果】")
    print(f"暂无当日涨幅＞{target_gain}%的股票")
    print("-" * 50)

    # ===================== 模块2：清空自定义选板块 =====================
    try:
        print("【模块2：自定义板块操作】")
        tq.send_user_block(block_code=target_block_name, stocks=[],show=True)
        print(f"✅ 已清空自定义板块「{target_block_name}」")
    except Exception as e:
        print(f"❌ 清空自定义板块失败：{e}")
    print("-" * 50)
```

# 通用函数

数据订阅函数：包括对行情数据进行订阅/取消订阅、刷新和缓存等函数。
与客户端交互函数：包括发生消息到TQ策略管理器界面、发生信号到客户端个股界面、发送预警到客户端TQ策略信号等。
数据信息文件包：我们提供各类特定的数据信息文件包。具体见download_file。

## 初始化initialize

```python
from tqcenter import tq

tq.initialize(__file__)
```

注意事项:
1."initialize"不可修改。
2.该函数用于初始化，任何一个策略都必须有该函数。

## 订阅行情subscribe_hq

订阅股票实时更新

```python
tq.subscribe_hq(stock_list=batch_codes)
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|订阅的证券代码|
|callback|Y|str|回调函数|

订阅股票更新 传入回调函数，订阅的股票有更新时，系统会调用回调函数，最多订阅100条
回调函数格式定义为on_data(datas) datas格式为 {"Code":"XXXXXX.XX","ErrorId":"0"}

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

# 回调函数 功能为收到更新后请求最新的report数据
def my_callback_func(data_str):
    print("Callback received data:", data_str)
    code_json = json.loads(data_str)
    print(f"codes = {code_json.get('Code')}")
    report_ptr = tq.get_report_data(code_json.get('Code'))
    print(report_ptr)
    return None

sub_hq = tq.subscribe_hq(stock_list=['688318.SH'], callback=my_callback_func)
print(sub_hq)

# 收到更新时策略需要正在运行
#while True:
# time.sleep(1)
```

数据样本

```json
{
   "Error" : "订阅688318.SH更新成功.",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

## 取消订阅更新unsubscribe_hq

取消订阅股票实时更新

```python
unsubscribe_hq(stock_list: List[str] = []):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码|

订阅股票更新 传入回调函数，订阅的股票有更新时，系统会调用回调函数，最多订阅100条
回调函数格式定义为on_data(datas) datas格式为 {"Code":"XXXXXX.XX","ErrorId":"0"}

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
un_sub_ptr = tq.unsubscribe_hq(stock_list=['688318.SH'])
print(un_sub_ptr)
```

数据样本

```json
{
   "Error" : "取消全部订阅更新失败.",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

## 获得订阅列表get_subscribe_hq_stock_list

获得当前策略订阅的股票列表

```python
get_subscribe_hq_stock_list():
```

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

sub_list = tq.get_subscribe_hq_stock_list()
print(sub_list)
```

数据样本

```python
['600519.SH']
```

## 刷新行情缓存(最新snapshot和K线数据)refresh_cache

刷新行情缓存(最新snapshot和K线数据)。如果不调用，首次取snapshot和K线时系统会自动刷新一次行情

```python
def refresh_cache(market: str = 'AG',
     force: bool = False):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|force|Y|bool|是否强制刷新|
|market|Y|str|指定刷新的市场|

force为false时距离上次刷新不足10分钟则不会刷新，为true时强制刷新。
market赋值： 'AG'表示A股，'HK'表示港股，'US'表示美股，'QH'表示国内期货，'QQ'表示股票期权，'NQ'表示新三板，'ZZ'表示中证和国证指数，'OF'表示基金净值，'ZS' 表示沪深京指数，'OJ' 表示期货期权。

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
refresh_cache = tq.refresh_cache()
print(refresh_cache)
```

数据样本

使用后会在客户端弹出刷新数据的加载界面，加载完成后才会有返回

```json
{
   "Error" : "Refresh Cache Success.",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

## 刷新历史K线缓存refresh_kline

根据股票和周期刷新历史K线缓存，如果本地没有下载完整的日线等数据，则可以调用这个函数定向下载某些品种某些周期的历史K线数据

```python
refresh_kline(stock_list: List[str] = [], period: str = '')
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表，证券代码格式为6位数+市场后缀（.SH/.SZ/.BJ等）|
|period|Y|str|周期 1d为日线、1m为一分钟线、5m为五分钟线，只支持这三种，其它周期的数据均由这三种数据生成|

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

refresh_ptr = tq.refresh_kline(stock_list=['600519.SH'], period='1d')
print(refresh_ptr)
```

数据样本

注：如果在盘中交易时间段下载1m和5m分钟线，只能下载到截止上个交易日的数据
使用后会在客户端弹出刷新数据的加载界面，加载完成后才会有返回

```json
{
   "Error" : "refresh kline cache success.",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

# 行情类信息

## 获取K线行情get_market_data

根据股票，获取历史行情

```python
get_market_data(field_list: List[str] = [],
    stock_list: List[str] = [],
    period: str = '',
    start_time: str = '',
    end_time: str = '',
    count: int = -1,
    dividend_type: Optional[str] = None,
    fill_data: bool = True) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|field_list|N|List[str]|字段筛选，传空则返回全部字段|
|stock_list|Y|List[str]|证券代码列表|
|period|Y|str|周期 1d为日线、1m为一分钟线、5m为五分钟线，只支持这三种，其它周期的数据均由这三种数据生成|
|start_time|N|str|起始时间|
|end_time|N|str|结束时间|
|count|N|str|返回数据个数（每只股票）|
|dividend_type|N|str|复权类型 (opens new window)：none不复权、front前复权、back后复权|
|fill_data|N|bool|是否向后填充空缺数据|

count<=0时，即返回start_time和end_time之间的全部数据

返回数据

返回dict { field1 : value1, field2 : value2, ... }
field1, field2, ... ：数据字段
value1, value2, ... ：pd.DataFrame 数据集，index为stock_list，columns为time_list
各字段对应的DataFrame维度相同、索引相同
只有dividend_type传入为none时，会返回有效的前复权因子ForwardFactor
后复权数据与取的数据个数有关，只在返回的数据中进行后复权
一次最多返回24000条数据，要获取完整分钟线需要多次分批获取
返回复权数据时，若该组数据时间内未发生权息变动，则复权价与未复权价相同，

|数据|默认返回|数据类型|数据说明|
|---|---|---|---|
|Date|Y|str|日期|
|Time|Y|str|时间|
|Open|Y|str|开盘价|
|High|Y|str|最高价|
|Low|Y|str|最低价|
|Close|Y|str|收盘价|
|Volume|Y|str|成交量|
|Amount|Y|str|成交额|
|ForwardFactor|Y|str|前复权因子，当dividend_type=none时候返回有效值|
|VolInStock|N|str|持仓量|

期货数据时Amount为0，非期货数据时VolInStock为0

接口使用

获取688318.SH从2025-12-20到今为止最新一条日K线的不复权数据

```python
from tqcenter import tq
tq.initialize(__file__)
df = tq.get_market_data(
        field_list=[],
        stock_list=['688318.SH'],
        start_time='20251220',
        end_time='',
        count=1,
        dividend_type='none',
        period='1d',
        fill_data=True
    )
print(df)
```

数据样本

```json
{'Amount':             688318.SH
2025-12-24   29394.81,
'Low':             688318.SH
2025-12-24      128.0,
'Date':              688318.SH
2025-12-24  20251224.0,
'Volume':             688318.SH
2025-12-24  2257325.0,
'Close':             688318.SH
2025-12-24     131.58,
'Open':             688318.SH
2025-12-24     128.01,
'Time':             688318.SH
2025-12-24        0.0,
'High':             688318.SH
2025-12-24     131.87,
'ForwardFactor':             688318.SH
2025-12-24        1.0}
```

## 获取快照数据get_market_snapshot

根据股票，获取最新行情数据

```python
def get_market_snapshot(stock_code: str,
                    field_list: List = []) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|
|field_list|N|List[str]|字段筛选，传空则返回全部|

返回数据

|数据|默认返回|数据类型|数据说明|
|---|---|---|---|
|ItemNum|Y|str|快照笔数|
|LastClose|Y|str|前收盘价|
|Open|Y|str|开盘价|
|Max|Y|str|最高价|
|Min|Y|str|最低价|
|Now|Y|str|现价|
|Volume|Y|str|总手|
|NowVol|Y|str|现手|
|Amount|Y|str|总成交金额|
|Inside|Y|str|内盘 板块指数时为跌停家数|
|Outside|Y|str|外盘 板块指数时为涨停家数|
|TickDiff|Y|str|笔涨跌|
|InOutFlag|Y|str|内外盘标志 0:Buy 1:Sell 2:Unknown|
|Jjjz|Y|str|基金净值|
|Buyp|Y|List[str]|五个买价|
|Buyv|Y|List[str]|对应的五个买盘量|
|Sellp|Y|List[str]|五个卖价|
|Sellv|Y|List[str]|对应的五个卖盘量|
|UpHome|Y|str|上涨家数 对于指数有效|
|DownHome|Y|str|下跌家数 对于指数有效|
|Before5MinNow|Y|str|5分钟前价格|
|Average|Y|str|均价|
|XsFlag|Y|str|小数位数|
|Zangsu|Y|str|涨速|
|ZAFPre3|Y|str|3日涨幅|

接口使用

获取688318.SH从2025-12-20到今为止最新一条日K线的不复权数据

```python
from tqcenter import tq

tq.initialize(__file__)

market_snapshot = tq.get_market_snapshot(stock_code = '688260.SH', field_list=[])
print(market_snapshot)
```

数据样本

```json
{'ItemNum': '3342', 
'LastClose': '34.21', 
'Open': '33.78', 
'Max': '36.49', 
'Min': '32.50', 
'Now': '35.06', 
'Volume': '122881', 
'NowVol': '1449', 
'Amount': '43068.48', 
'Inside': '60373', 
'Outside': '62509', 
'TickDiff': '0.00', 
'InOutFlag': '2', 
'Jjjz': '0.00', 
'Buyp': ['35.05', '35.04', '35.02', '35.01', '35.00'], 
'Buyv': ['154', '9', '49', '136', '154'], 
'Sellp': ['35.06', '35.07', '35.08', '35.09', '35.10'], 
'Sellv': ['4', '31', '139', '4', '4'], 
'UpHome': '0', 
'DownHome': '0', 
'Before5MinNow': '35.15', 
'Average': '35.05', 
'XsFlag': '2', 
'Zangsu': '-0.25', 
'ZAFPre3': '-1.83', 
'ErrorId': '0'}
```

# 调用通达信公式

## 格式化K线数据formula_format_data

格式化get_market_data获取的K线数据

```python
def formula_format_data(data_dict: Dict = {}):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|data_dict|Y|Dict|get_market_data获取格式的K线Dict|

get_market_data获取的K线数据不能直接用于设置公式参数，须先调用formula_format_data进行格式化
formula_format_data返回值为List[Dict]，其中Dict的Key须有["Amount", "Volume", "Close", "Open", "High", "Low"]，用户可以直接提供符合条件的List提供给tdx_formula_set_data。

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

test_md = tq.get_market_data(stock_list=['688318.SH'], count=5, period='1d')
format_md = tq.formula_format_data(test_md)
print(format_md)
```

数据样本

```json
{'688318.SH': [
{'Date': '2026-01-20 00:00:00', 'Amount': 33930.29, 'Volume': 2345401.0, 'Close': 144.4, 'Open': 146.5, 'High': 146.98, 'Low': 142.65}, 
{'Date': '2026-01-21 00:00:00', 'Amount': 35841.09, 'Volume': 2472760.0, 'Close': 144.77, 'Open': 144.49, 'High': 146.5, 'Low': 143.1}, 
{'Date': '2026-01-22 00:00:00', 'Amount': 41598.79, 'Volume': 2878793.0, 'Close': 143.03, 'Open': 145.0, 'High': 147.0, 'Low': 142.5}, 
{'Date': '2026-01-23 00:00:00', 'Amount': 47131.04, 'Volume': 3256538.0, 'Close': 144.39, 'Open': 142.58, 'High': 146.88, 'Low': 142.58}, 
{'Date': '2026-01-26 00:00:00', 'Amount': 54141.73, 'Volume': 3761141.0, 'Close': 141.84, 'Open': 143.7, 'High': 146.77, 'Low': 141.8}]}
```
