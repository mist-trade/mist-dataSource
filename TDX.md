# 通达信Quant API文档

## 快速开始

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

## 通用函数

数据订阅函数：包括对行情数据进行订阅/取消订阅、刷新和缓存等函数。
与客户端交互函数：包括发送消息到TQ策略管理器界面、发送信号到客户端个股界面、发送预警到客户端TQ策略信号等。
数据信息文件包：我们提供各类特定的数据信息文件包。具体见download_file。

### 初始化initialize

```python
from tqcenter import tq

tq.initialize(__file__)
```

注意事项:
1."initialize"不可修改。
2.该函数用于初始化，任何一个策略都必须有该函数。

### 订阅行情subscribe_hq

订阅股票实时更新

```python
tq.subscribe_hq(stock_list=batch_codes, callback=my_callback_func)
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

### 取消订阅更新unsubscribe_hq

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

### 获得订阅列表get_subscribe_hq_stock_list

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

### 刷新行情缓存(最新snapshot和K线数据)refresh_cache

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

### 刷新历史K线缓存refresh_kline

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

### 下载特定数据文件download_file

10大股东数据文件、ETF申赎清单文件、最近舆情信息文件、股票综合信息文件

```python
download_file(stock_code: str = '',
			down_time:str = '',
			down_type:int = 1):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|List[str]|证券代码|
|down_time|Y|List[str]|指定日期|
|down_type|Y|List[str]|指定下载类型|

 * down_type=1时，下载10大股东数据文件，down_time为指定日期
 * down_type=2时，下载ETF申赎清单文件，down_time为指定日期
 * down_type=3时，下载最近舆情信息文件，其余两项无效
 * down_type=4时，下载股票综合信息文件，其余两项无效
 * 下载的文件保存在 .\PYPlugins\data 文件夹
 * down_type=1时，下载的文件中含指定日期所在年度的所有10大股东数据和流通股东数据

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
# 下载10大股东数据
down_ptr_10 = tq.download_file(stock_code='688318.SH', down_time='20241231',down_type=1)
print(down_ptr_10)
# 下载ETF申赎数据
dowm_ptr_etf = tq.download_file(stock_code='159109.SH', down_time='20260227',down_type=2)
print(dowm_ptr_etf)
```

数据样本

```json
{
   "ErrorId" : "0",
   "Msg" : "下载十大股东数据[2025]成功。",
   "run_id" : "1"
}

{
   "ErrorId" : "0",
   "Msg" : "下载ETF申述清单[20250101]成功。",
   "run_id" : "1"
}
```

### 获取交易日列表get_trading_dates

根据指定时间段获取交易日列表

```python
get_trading_dates(market: str,
				start_time: str,
				end_time: str,
				count:int = -1) -> List:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|market|Y|str|市场代码（暂固定为SH）|
|start_time|N|str|起始日期|
|end_time|N|str|结束日期|
|count|N|int|返回最近的count个交易日|

 * 需要现在客户端下载上证指数（999999）的盘后数据 目前仅支持A股
 * count > 0时，限制返回从结束日期往前最近的count个在限定时间段中的交易日

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

trade_dates = tq.get_trading_dates(market = 'SH', start_time = '20220101', end_time = '', count = 10);
print(trade_dates)
```

数据样本

```python
['20251211', '20251212', '20251215', '20251216', '20251217', '20251218', '20251219', '20251222', '20251223', '20251224']
```

### 获取股票列表 get_stock_list

获取指定市场或板块的股票列表

```python
get_stock_list(market: str = '0') -> List:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|market|Y|str|市场代码|  

 * market=0或"0"表示沪深京A股，market=1或"1"表示沪深京B股，market=10或"10"表示A股版块，market=91 跟踪指数的ETF信息，market=92: 国内期货主力合约

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
stock_list = tq.get_stock_list(market = '0')
print(stock_list)
print(len(stock_list))
```

数据样本

```python
['000001.SZ', '000002.SZ', '000004.SZ', '000005.SZ', '000006.SZ', '000007.SZ', '000008.SZ', '000009.SZ', '000010.SZ', '000011.SZ', ...]
```

### 获取股票信息 get_stock_info

根据股票代码获取股票基本信息

```python
get_stock_info(stock_code: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
stock_info = tq.get_stock_info(stock_code = '688318.SH')
print(stock_info)
```

### 获取报告数据 get_report_data

根据股票代码获取报告数据

```python
get_report_data(stock_code: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
report_data = tq.get_report_data(stock_code = '688318.SH')
print(report_data)
```

### 获取更多信息 get_more_info

根据股票代码获取更多信息

```python
get_more_info(stock_code: str = '', field_list: List[str] = []) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|
|field_list|N|List[str]|字段筛选，传空则返回全部|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
more_info = tq.get_more_info(stock_code = '688318.SH', field_list=[])
print(more_info)
```

### 价格数据转换 price_df

将get_market_data返回的数据转换为宽表

```python
price_df(data: Dict, field: str, column_names: List[str] = None) -> pd.DataFrame:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|data|Y|Dict|get_market_data返回的数据|
|field|Y|str|字段名|
|column_names|N|List[str]|列名，默认为stock_list|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
df = tq.get_market_data(
        field_list=['Close'],
        stock_list=['688318.SH', '600519.SH'],
        start_time='20251220',
        end_time='',
        count=5,
        dividend_type='front',
        period='1d',
        fill_data=True
    )
close_df = tq.price_df(df, 'Close')
print(close_df)
```

### 获取股票所属板块 get_relation

获取股票所属板块信息

```python
get_relation(stock_code: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
relation = tq.get_relation(stock_code = '688318.SH')
print(relation)
```

### 调用客户端功能接口 exec_to_tdx

调用通达信客户端功能

```python
exec_to_tdx(cmd: str = '', param: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|cmd|Y|str|命令|
|param|N|str|参数|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
exec_result = tq.exec_to_tdx(cmd='open', param='688318.SH')
print(exec_result)
```

### 撤单 cancel_order_stock

撤销股票交易委托

```python
cancel_order_stock(order_id: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|order_id|Y|str|委托订单ID|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
cancel_result = tq.cancel_order_stock(order_id='123456')
print(cancel_result)
```

### 账户资产查询 query_stock_asset

查询账户资产信息

```python
query_stock_asset(account_id: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|account_id|Y|str|账户ID|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
asset = tq.query_stock_asset(account_id='123456')
print(asset)
```

### 获取资金账户句柄 stock_account

获取资金账户句柄

```python
stock_account(account_type: int = 0) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|account_type|Y|int|账户类型|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
account = tq.stock_account(account_type=0)
print(account)
```

### 查询账户委托信息 query_stock_orders

查询账户委托信息

```python
query_stock_orders(account_id: str = '', status: int = -1) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|account_id|Y|str|账户ID|
|status|N|int|委托状态|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
orders = tq.query_stock_orders(account_id='123456', status=1)
print(orders)
```

### 查询账户持仓信息 query_stock_positions

查询账户持仓信息

```python
query_stock_positions(account_id: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|account_id|Y|str|账户ID|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
positions = tq.query_stock_positions(account_id='123456')
print(positions)
```

### 交易执行函数 order_stock

执行股票交易

```python
order_stock(account_id: str = '',
            stock_code: str = '',
            price: float = 0,
            amount: int = 0,
            order_type: int = 0,
            price_type: int = 0) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|account_id|Y|str|账户ID|
|stock_code|Y|str|证券代码|
|price|Y|float|交易价格|
|amount|Y|int|交易数量|
|order_type|Y|int|交易类型：0买入，1卖出，69融资买入，70融券卖出|
|price_type|Y|int|价格类型：0自填价，1市价，2涨停价/笼子上限，3跌停价/笼子下限|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
order_result = tq.order_stock(
    account_id='123456',
    stock_code='688318.SH',
    price=130.0,
    amount=100,
    order_type=0,
    price_type=0
)
print(order_result)
```

### 发送消息到通达信客户端send_message

发送消息给通达信客户端的TQ策略界面

```python
send_message(msg_str: str) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|msg_str|Y|str|消息字符串|

 * 传入的字符串使用 | 可以让客户端将其分为两条（插入 \n 也可以分行显示）

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
msg_str = "这是第一行. | 这是第二行. "
tq.send_message(msg_str)
```

### 发送文件到客户端send_file

往通达信客户端发送文件名，可由TQ策略数据浏览中打开

```python
send_file(file: str) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|file|Y|str|文件路径|

 * 文件放于 .\PYPlugins\file\ 文件夹中时，file可仅传入文件名
 * 文件放于其他位置时，file需要传入绝对路径
 * 目前支持的文件类型：txt，pdf，html

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
file = "test.txt"
tq.send_file(file)
```

### 发送预警信号send_warn

往客户端发送指定股票的预警信号

```python
send_warn(stock_list:        List[str] = [],
			time_list:         List[str] = [],
			price_list:        List[str] = [],
			close_list:        List[str] = [],
			volum_list:        List[str] = [],
			bs_flag_list:      List[str] = [],
			warn_type_list:    List[str] = [],
			reason_list:       List[str] = [],
			count:        int  = 1) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|time_list|Y|List[str]|时间列表|
|price_list|N|List[str]|现价列表|
|close_list|N|List[str]|收盘价列表|
|volum_list|N|List[str]|成交额列表|
|bs_flag_list|N|List[str]|买卖标志：0买1卖2未知|
|warn_type_list|N|List[str]|预警类型：0常规预警（目前仅支持）|
|reason_list|N|List[str]|预警原因|
|count|N|int|有效数据个数|

 * price_list、close_list、volum_list、bs_flag_list、warn_type_list 均要求为纯数字字符串List
 * bs_flag_list 0买1卖2未知，长度小于count的会自动补为2。
 * reason_list每个元素有效长度为25个汉字（50个英文）|
 * count限定入参中每个list中的有效数据个数，即每个list前count个数据会传给客户端
 * stock_list与其他list的元素数据是一一对应的，即stock_list的第一个元素对应的预警信息是其他list的第一个元素，同一只股票的多个预警信息，则在stock_list中加入多次该股票

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
warn_res = tq.send_warn(stock_list = ['688318.SH','688318.SH','600519.SH'],
             time_list = ['20251215141115','20251215142100','20251215143101'],
             price_list= ['123.45','133.45','1823.45'],
             close_list= ['122.50','132.50','1822.50'],
             volum_list= ['1000','2000','15000'],
             bs_flag_list= ['0'],
             warn_type_list= ['0'],
             reason_list= ['价格突破预警线','收盘价突破预警线','成交量突破预警线'],
             count=3)
print(warn_res)
```

数据样本

```json
{'Error': '发送预警信号成功.', 'ErrorId': '0', 'run_id': '1'}
```

### 发送回测数据send_bt_data

往客户端发送指定股票的回测数据

```python
send_bt_data(stock_code:          str  = '',
			time_list:         List[str] = [],
			data_list:         List[List[str]] = [],
			count:        int  = 1) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|List[str]|证券代码|
|time_list|Y|List[str]|时间列表|
|data_list|N|List[List[str]]|回测数据列表|
|count|N|int|有效数据个数|

 * data_list为二维List，每个子元素对应time_list的一个元素时间点，且每个子元素最多有16个有效纯数字字符串，即data_list每个子List的前16个数据为一个时间点的有效数据
 * count限定入参中每个list中的有效数据个数，即每个list前count个数据会传给客户端

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

bt_data = tq.send_bt_data(stock_code = '688318.SH',
                          time_list = ['20251215141115'],
                          data_list = [['11']],
                          count = 1)
print(bt_data)
```

数据样本

```json
{'Error': '发送回测结果成功.', 'ErrorId': '0', 'run_id': '1'}
```

### 导出多组数据到通达信客户端 print_to_tdx

将计算数据导出到通达信客户端展示

```python
print_to_tdx(df_list:          list[pd.DataFrame] = [],
			sp_name:          str  = "",
			xml_filename:     str  = "",
			jsn_filenames:    list[str] = None,
			vertical:         int  = None,
			horizontal:       int  = None,
			height:           list[str | float] = None,
			table_names:      list[str] = None) -> None:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|df_list|Y|list[pd.DataFrame]|多组数据的DataFrame列表，每组table对应1个DataFrame；每个DataFrame非空且第一列为日期（datetime64[ns]或字符串类型），后续列为指标/因子名称；列表长度需等于组数|
|sp_name|N|str|生成.sp文件的名称前缀，为空时默认生成python.sp|
|xml_filename|N|str|生成的xml文件名（需包含.xml后缀），为空会影响通达信面板配置关联，建议必填|
|jsn_filenames|Y|list[str]|每组数据对应的.jsn文件名列表，列表非空且长度需等于组数（与df_list一致），文件名建议包含.jsn后缀|
|vertical|N|int|纵向排列的table组数（≥1），与horizontal二选一，horizontal优先级更高|
|horizontal|N|int|横向排列的table组数（≥1），优先级高于vertical，未指定时默认使用vertical或1组|
|height|N|list[str | float]|自定义每组gridctrl高度列表，长度需等于组数；元素为数值/字符串（高度占比），未指定时自动计算（1/组数，最后一组高度为0）|
|table_names|N|list[str]|每组展示面板的标题列表，长度需等于组数；元素为空时自动使用对应jsn_filenames的前缀作为标题|

 * df_list、jsn_filenames长度必须与vertical/horizontal指定的组数完全一致，否则会抛出ValueError异常
 * height参数值为高度占比（如0.3/"0.3"），表示该面板占整体展示区域的比例，仅支持0-1之间的数值
 * 未指定vertical/horizontal时，默认按1组纵向排列展示，自动计算面板高度

## 行情类信息

### 获取K线行情get_market_data

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
|dividend_type|N|str|复权类型：none不复权、front前复权、back后复权|
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

### 获取每天的股本数据get_gb_info

获取指定股票的股本数据

```python
def get_gb_info(stock_code:str = '',
                date_list: List[str] = [],
                count: int = 1):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|股票代码|
|date_list|Y|List[str]|日期数组|
|count|Y|int|日期有效个数|

 * date_list传入的日期须从小到大排序
 * date_list有效数据个数须不小于count，且不能小于1

输出数据

|名称|类型|数值|说明|
|---|---|---|---|
|Date|double|日期|日期|
|Zgb|double|总股本|总股本|
|Ltgb|double|流通股本|流通股本|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
gb_info = tq.get_gb_info(stock_code = '688318.SH', date_list=['20250101','20250601'], count=2)
print(gb_info)
```

数据样本

```json
[{'Date': 20250101, 'Zgb': 182942480.0, 'Ltgb': 182942480.0},
{'Date': 20250601,  'Zgb': 182942480.0, 'Ltgb': 182942480.0}]
```

### 获取分红配送数据get_divid_factors

根据股票，获取指定时间段内的分红配送数据

```python
get_divid_factors(stock_code: str,
					start_time: str,
					end_time: str) -> pd.DataFrame:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|
|start_time|N|str|起始时间|
|end_time|N|str|结束时间|

返回数据

|数据|默认返回|数据类型|数据说明|
|---|---|---|---|
|Type|Y|str|类型 1:除权除息 11:扩缩股 15:重新调整|
|Bonus|Y|str|红利|
|AlloPrice|Y|str|配股价|
|ShareBonus|Y|str|送股/扩缩股比例|
|Allotment|Y|str|配股|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
divid_factors = tq.get_divid_factors(
        stock_code='688318.SH',
        start_time='',
        end_time='')
print(divid_factors)
```

数据样本

```
           Type  Bonus  AllotPrice  ShareBonus  Allotment
Date
2020-09-29    1    6.0         0.0         0.0        0.0
2021-05-27    1   10.0         0.0         0.0        0.0
2022-06-20    1   14.0         0.0         4.0        0.0
2023-06-13    1    5.0         0.0         4.0        0.0
2024-06-14    1    8.0         0.0         4.0        0.0
```

### 获取快照数据get_market_snapshot

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

## 财务类数据

### 获取专业财务数据get_financial_data

根据股票，获取指定时间段内的专业财务数据，与基础财务数据不同，需要先在客户端中下载专业财务数据

```python
get_financial_data(stock_list: List[str] = [],
					field_list: List[str] = [],
					start_time: str = '',
					end_time: str = '',
					report_type: str = 'announce_time') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|field_list|Y|List[str]|字段筛选，不能为空（如 FN193）|
|start_time|N|str|起始时间|
|end_time|N|str|结束时间|
|report_type|N|str|报告类型：announce_time（公告日期）或 tag_time（报告期）|

 * 需要先在客户端中下载财务数据包

输出数据

|名称|类型|数值|说明|
|---|---|---|---|
|FN1|double|最新提示|最新提示|
|FN2|double|每股收益|每股收益|
|FN3|double|每股净资产|每股净资产|
|FN4|double|每股公积金|每股公积金|
|FN5|double|每股未分配利润|每股未分配利润|
|FN6|double|每股经营现金流|每股经营现金流|
|FN7|double|净资产收益率|净资产收益率|
|FN8|double|净利润|净利润|
|FN9|double|净利润同比|净利润同比|
|FN10|double|净利润环比|净利润环比|
|FN11|double|主营收入|主营收入|
|FN12|double|主营收入同比|主营收入同比|
|FN13|double|主营收入环比|主营收入环比|
|FN14|double|毛利润|毛利润|
|FN15|double|毛利率|毛利率|
|FN16|double|营业利润|营业利润|
|FN17|double|营业利润率|营业利润率|
|FN18|double|净利润率|净利润率|
|FN19|double|总资产|总资产|
|FN20|double|总负债|总负债|
|FN21|double|资产负债率|资产负债率|
|FN22|double|股东权益|股东权益|
|FN23|double|流动比率|流动比率|
|FN24|double|速动比率|速动比率|
|FN25|double|存货周转率|存货周转率|
|FN26|double|应收账款周转率|应收账款周转率|
|FN27|double|总资产周转率|总资产周转率|
|FN28|double|总资产收益率|总资产收益率|
|FN29|double|股东权益比率|股东权益比率|
|FN30|double|固定资产比率|固定资产比率|
|FN31|double|无形资产比率|无形资产比率|
|FN32|double|长期负债比率|长期负债比率|
|FN33|double|流动负债比率|流动负债比率|
|FN34|double|销售费用率|销售费用率|
|FN35|double|管理费用率|管理费用率|
|FN36|double|财务费用率|财务费用率|
|FN37|double|研发费用率|研发费用率|
|FN38|double|营业外收支净额|营业外收支净额|
|FN39|double|所得税费用|所得税费用|
|FN40|double|经营活动现金流|经营活动现金流|
|FN41|double|投资活动现金流|投资活动现金流|
|FN42|double|筹资活动现金流|筹资活动现金流|
|FN43|double|现金及现金等价物净增加额|现金及现金等价物净增加额|
|FN44|double|经营活动现金流/净利润|经营活动现金流/净利润|
|FN45|double|经营活动现金流/营业收入|经营活动现金流/营业收入|
|FN46|double|投资活动现金流/净利润|投资活动现金流/净利润|
|FN47|double|筹资活动现金流/净利润|筹资活动现金流/净利润|
|FN48|double|现金及现金等价物净增加额/净利润|现金及现金等价物净增加额/净利润|
|FN49|double|经营活动现金流/总资产|经营活动现金流/总资产|
|FN50|double|投资活动现金流/总资产|投资活动现金流/总资产|
|FN51|double|筹资活动现金流/总资产|筹资活动现金流/总资产|
|FN52|double|现金及现金等价物净增加额/总资产|现金及现金等价物净增加额/总资产|
|FN53|double|经营活动现金流/股东权益|经营活动现金流/股东权益|
|FN54|double|投资活动现金流/股东权益|投资活动现金流/股东权益|
|FN55|double|筹资活动现金流/股东权益|筹资活动现金流/股东权益|
|FN56|double|现金及现金等价物净增加额/股东权益|现金及现金等价物净增加额/股东权益|
|FN57|double|经营活动现金流/主营业务收入|经营活动现金流/主营业务收入|
|FN58|double|投资活动现金流/主营业务收入|投资活动现金流/主营业务收入|
|FN59|double|筹资活动现金流/主营业务收入|筹资活动现金流/主营业务收入|
|FN60|double|现金及现金等价物净增加额/主营业务收入|现金及现金等价物净增加额/主营业务收入|
|FN61|double|经营活动现金流/营业利润|经营活动现金流/营业利润|
|FN62|double|投资活动现金流/营业利润|投资活动现金流/营业利润|
|FN63|double|筹资活动现金流/营业利润|筹资活动现金流/营业利润|
|FN64|double|现金及现金等价物净增加额/营业利润|现金及现金等价物净增加额/营业利润|
|FN65|double|经营活动现金流/毛利润|经营活动现金流/毛利润|
|FN66|double|投资活动现金流/毛利润|投资活动现金流/毛利润|
|FN67|double|筹资活动现金流/毛利润|筹资活动现金流/毛利润|
|FN68|double|现金及现金等价物净增加额/毛利润|现金及现金等价物净增加额/毛利润|
|FN69|double|经营活动现金流/净利润(TTM)|经营活动现金流/净利润(TTM)|
|FN70|double|投资活动现金流/净利润(TTM)|投资活动现金流/净利润(TTM)|
|FN71|double|筹资活动现金流/净利润(TTM)|筹资活动现金流/净利润(TTM)|
|FN72|double|现金及现金等价物净增加额/净利润(TTM)|现金及现金等价物净增加额/净利润(TTM)|
|FN73|double|经营活动现金流/营业收入(TTM)|经营活动现金流/营业收入(TTM)|
|FN74|double|投资活动现金流/营业收入(TTM)|投资活动现金流/营业收入(TTM)|
|FN75|double|筹资活动现金流/营业收入(TTM)|筹资活动现金流/营业收入(TTM)|
|FN76|double|现金及现金等价物净增加额/营业收入(TTM)|现金及现金等价物净增加额/营业收入(TTM)|
|FN77|double|经营活动现金流/营业利润(TTM)|经营活动现金流/营业利润(TTM)|
|FN78|double|投资活动现金流/营业利润(TTM)|投资活动现金流/营业利润(TTM)|
|FN79|double|筹资活动现金流/营业利润(TTM)|筹资活动现金流/营业利润(TTM)|
|FN80|double|现金及现金等价物净增加额/营业利润(TTM)|现金及现金等价物净增加额/营业利润(TTM)|
|FN81|double|经营活动现金流/毛利润(TTM)|经营活动现金流/毛利润(TTM)|
|FN82|double|投资活动现金流/毛利润(TTM)|投资活动现金流/毛利润(TTM)|
|FN83|double|筹资活动现金流/毛利润(TTM)|筹资活动现金流/毛利润(TTM)|
|FN84|double|现金及现金等价物净增加额/毛利润(TTM)|现金及现金等价物净增加额/毛利润(TTM)|
|FN85|double|经营活动现金流/总资产(TTM)|经营活动现金流/总资产(TTM)|
|FN86|double|投资活动现金流/总资产(TTM)|投资活动现金流/总资产(TTM)|
|FN87|double|筹资活动现金流/总资产(TTM)|筹资活动现金流/总资产(TTM)|
|FN88|double|现金及现金等价物净增加额/总资产(TTM)|现金及现金等价物净增加额/总资产(TTM)|
|FN89|double|经营活动现金流/股东权益(TTM)|经营活动现金流/股东权益(TTM)|
|FN90|double|投资活动现金流/股东权益(TTM)|投资活动现金流/股东权益(TTM)|
|FN91|double|筹资活动现金流/股东权益(TTM)|筹资活动现金流/股东权益(TTM)|
|FN92|double|现金及现金等价物净增加额/股东权益(TTM)|现金及现金等价物净增加额/股东权益(TTM)|
|FN93|double|经营活动现金流/主营业务收入(TTM)|经营活动现金流/主营业务收入(TTM)|
|FN94|double|投资活动现金流/主营业务收入(TTM)|投资活动现金流/主营业务收入(TTM)|
|FN95|double|筹资活动现金流/主营业务收入(TTM)|筹资活动现金流/主营业务收入(TTM)|
|FN96|double|现金及现金等价物净增加额/主营业务收入(TTM)|现金及现金等价物净增加额/主营业务收入(TTM)|
|FN97|double|经营活动现金流/营业利润(TTM)|经营活动现金流/营业利润(TTM)|
|FN98|double|投资活动现金流/营业利润(TTM)|投资活动现金流/营业利润(TTM)|
|FN99|double|筹资活动现金流/营业利润(TTM)|筹资活动现金流/营业利润(TTM)|
|FN100|double|现金及现金等价物净增加额/营业利润(TTM)|现金及现金等价物净增加额/营业利润(TTM)|
|FN101|double|经营活动现金流/毛利润(TTM)|经营活动现金流/毛利润(TTM)|
|FN102|double|投资活动现金流/毛利润(TTM)|投资活动现金流/毛利润(TTM)|
|FN103|double|筹资活动现金流/毛利润(TTM)|筹资活动现金流/毛利润(TTM)|
|FN104|double|现金及现金等价物净增加额/毛利润(TTM)|现金及现金等价物净增加额/毛利润(TTM)|
|FN105|double|经营活动现金流/净利润(季度)|经营活动现金流/净利润(季度)|
|FN106|double|投资活动现金流/净利润(季度)|投资活动现金流/净利润(季度)|
|FN107|double|筹资活动现金流/净利润(季度)|筹资活动现金流/净利润(季度)|
|FN108|double|现金及现金等价物净增加额/净利润(季度)|现金及现金等价物净增加额/净利润(季度)|
|FN109|double|经营活动现金流/营业收入(季度)|经营活动现金流/营业收入(季度)|
|FN110|double|投资活动现金流/营业收入(季度)|投资活动现金流/营业收入(季度)|
|FN111|double|筹资活动现金流/营业收入(季度)|筹资活动现金流/营业收入(季度)|
|FN112|double|现金及现金等价物净增加额/营业收入(季度)|现金及现金等价物净增加额/营业收入(季度)|
|FN113|double|经营活动现金流/营业利润(季度)|经营活动现金流/营业利润(季度)|
|FN114|double|投资活动现金流/营业利润(季度)|投资活动现金流/营业利润(季度)|
|FN115|double|筹资活动现金流/营业利润(季度)|筹资活动现金流/营业利润(季度)|
|FN116|double|现金及现金等价物净增加额/营业利润(季度)|现金及现金等价物净增加额/营业利润(季度)|
|FN117|double|经营活动现金流/毛利润(季度)|经营活动现金流/毛利润(季度)|
|FN118|double|投资活动现金流/毛利润(季度)|投资活动现金流/毛利润(季度)|
|FN119|double|筹资活动现金流/毛利润(季度)|筹资活动现金流/毛利润(季度)|
|FN120|double|现金及现金等价物净增加额/毛利润(季度)|现金及现金等价物净增加额/毛利润(季度)|
|FN121|double|经营活动现金流/总资产(季度)|经营活动现金流/总资产(季度)|
|FN122|double|投资活动现金流/总资产(季度)|投资活动现金流/总资产(季度)|
|FN123|double|筹资活动现金流/总资产(季度)|筹资活动现金流/总资产(季度)|
|FN124|double|现金及现金等价物净增加额/总资产(季度)|现金及现金等价物净增加额/总资产(季度)|
|FN125|double|经营活动现金流/股东权益(季度)|经营活动现金流/股东权益(季度)|
|FN126|double|投资活动现金流/股东权益(季度)|投资活动现金流/股东权益(季度)|
|FN127|double|筹资活动现金流/股东权益(季度)|筹资活动现金流/股东权益(季度)|
|FN128|double|现金及现金等价物净增加额/股东权益(季度)|现金及现金等价物净增加额/股东权益(季度)|
|FN129|double|经营活动现金流/主营业务收入(季度)|经营活动现金流/主营业务收入(季度)|
|FN130|double|投资活动现金流/主营业务收入(季度)|投资活动现金流/主营业务收入(季度)|
|FN131|double|筹资活动现金流/主营业务收入(季度)|筹资活动现金流/主营业务收入(季度)|
|FN132|double|现金及现金等价物净增加额/主营业务收入(季度)|现金及现金等价物净增加额/主营业务收入(季度)|
|FN133|double|经营活动现金流/营业利润(季度)|经营活动现金流/营业利润(季度)|
|FN134|double|投资活动现金流/营业利润(季度)|投资活动现金流/营业利润(季度)|
|FN135|double|筹资活动现金流/营业利润(季度)|筹资活动现金流/营业利润(季度)|
|FN136|double|现金及现金等价物净增加额/营业利润(季度)|现金及现金等价物净增加额/营业利润(季度)|
|FN137|double|经营活动现金流/毛利润(季度)|经营活动现金流/毛利润(季度)|
|FN138|double|投资活动现金流/毛利润(季度)|投资活动现金流/毛利润(季度)|
|FN139|double|筹资活动现金流/毛利润(季度)|筹资活动现金流/毛利润(季度)|
|FN140|double|现金及现金等价物净增加额/毛利润(季度)|现金及现金等价物净增加额/毛利润(季度)|
|FN141|double|经营活动现金流/净利润(年度)|经营活动现金流/净利润(年度)|
|FN142|double|投资活动现金流/净利润(年度)|投资活动现金流/净利润(年度)|
|FN143|double|筹资活动现金流/净利润(年度)|筹资活动现金流/净利润(年度)|
|FN144|double|现金及现金等价物净增加额/净利润(年度)|现金及现金等价物净增加额/净利润(年度)|
|FN145|double|经营活动现金流/营业收入(年度)|经营活动现金流/营业收入(年度)|
|FN146|double|投资活动现金流/营业收入(年度)|投资活动现金流/营业收入(年度)|
|FN147|double|筹资活动现金流/营业收入(年度)|筹资活动现金流/营业收入(年度)|
|FN148|double|现金及现金等价物净增加额/营业收入(年度)|现金及现金等价物净增加额/营业收入(年度)|
|FN149|double|经营活动现金流/营业利润(年度)|经营活动现金流/营业利润(年度)|
|FN150|double|投资活动现金流/营业利润(年度)|投资活动现金流/营业利润(年度)|
|FN151|double|筹资活动现金流/营业利润(年度)|筹资活动现金流/营业利润(年度)|
|FN152|double|现金及现金等价物净增加额/营业利润(年度)|现金及现金等价物净增加额/营业利润(年度)|
|FN153|double|经营活动现金流/毛利润(年度)|经营活动现金流/毛利润(年度)|
|FN154|double|投资活动现金流/毛利润(年度)|投资活动现金流/毛利润(年度)|
|FN155|double|筹资活动现金流/毛利润(年度)|筹资活动现金流/毛利润(年度)|
|FN156|double|现金及现金等价物净增加额/毛利润(年度)|现金及现金等价物净增加额/毛利润(年度)|
|FN157|double|经营活动现金流/总资产(年度)|经营活动现金流/总资产(年度)|
|FN158|double|投资活动现金流/总资产(年度)|投资活动现金流/总资产(年度)|
|FN159|double|筹资活动现金流/总资产(年度)|筹资活动现金流/总资产(年度)|
|FN160|double|现金及现金等价物净增加额/总资产(年度)|现金及现金等价物净增加额/总资产(年度)|
|FN161|double|经营活动现金流/股东权益(年度)|经营活动现金流/股东权益(年度)|
|FN162|double|投资活动现金流/股东权益(年度)|投资活动现金流/股东权益(年度)|
|FN163|double|筹资活动现金流/股东权益(年度)|筹资活动现金流/股东权益(年度)|
|FN164|double|现金及现金等价物净增加额/股东权益(年度)|现金及现金等价物净增加额/股东权益(年度)|
|FN165|double|经营活动现金流/主营业务收入(年度)|经营活动现金流/主营业务收入(年度)|
|FN166|double|投资活动现金流/主营业务收入(年度)|投资活动现金流/主营业务收入(年度)|
|FN167|double|筹资活动现金流/主营业务收入(年度)|筹资活动现金流/主营业务收入(年度)|
|FN168|double|现金及现金等价物净增加额/主营业务收入(年度)|现金及现金等价物净增加额/主营业务收入(年度)|
|FN169|double|经营活动现金流/营业利润(年度)|经营活动现金流/营业利润(年度)|
|FN170|double|投资活动现金流/营业利润(年度)|投资活动现金流/营业利润(年度)|
|FN171|double|筹资活动现金流/营业利润(年度)|筹资活动现金流/营业利润(年度)|
|FN172|double|现金及现金等价物净增加额/营业利润(年度)|现金及现金等价物净增加额/营业利润(年度)|
|FN173|double|经营活动现金流/毛利润(年度)|经营活动现金流/毛利润(年度)|
|FN174|double|投资活动现金流/毛利润(年度)|投资活动现金流/毛利润(年度)|
|FN175|double|筹资活动现金流/毛利润(年度)|筹资活动现金流/毛利润(年度)|
|FN176|double|现金及现金等价物净增加额/毛利润(年度)|现金及现金等价物净增加额/毛利润(年度)|
|FN177|double|经营活动现金流/净利润(半年度)|经营活动现金流/净利润(半年度)|
|FN178|double|投资活动现金流/净利润(半年度)|投资活动现金流/净利润(半年度)|
|FN179|double|筹资活动现金流/净利润(半年度)|筹资活动现金流/净利润(半年度)|
|FN180|double|现金及现金等价物净增加额/净利润(半年度)|现金及现金等价物净增加额/净利润(半年度)|
|FN181|double|经营活动现金流/营业收入(半年度)|经营活动现金流/营业收入(半年度)|
|FN182|double|投资活动现金流/营业收入(半年度)|投资活动现金流/营业收入(半年度)|
|FN183|double|筹资活动现金流/营业收入(半年度)|筹资活动现金流/营业收入(半年度)|
|FN184|double|现金及现金等价物净增加额/营业收入(半年度)|现金及现金等价物净增加额/营业收入(半年度)|
|FN185|double|经营活动现金流/营业利润(半年度)|经营活动现金流/营业利润(半年度)|
|FN186|double|投资活动现金流/营业利润(半年度)|投资活动现金流/营业利润(半年度)|
|FN187|double|筹资活动现金流/营业利润(半年度)|筹资活动现金流/营业利润(半年度)|
|FN188|double|现金及现金等价物净增加额/营业利润(半年度)|现金及现金等价物净增加额/营业利润(半年度)|
|FN189|double|经营活动现金流/毛利润(半年度)|经营活动现金流/毛利润(半年度)|
|FN190|double|投资活动现金流/毛利润(半年度)|投资活动现金流/毛利润(半年度)|
|FN191|double|筹资活动现金流/毛利润(半年度)|筹资活动现金流/毛利润(半年度)|
|FN192|double|现金及现金等价物净增加额/毛利润(半年度)|现金及现金等价物净增加额/毛利润(半年度)|
|FN193|double|经营活动现金流/总资产(半年度)|经营活动现金流/总资产(半年度)|
|FN194|double|投资活动现金流/总资产(半年度)|投资活动现金流/总资产(半年度)|
|FN195|double|筹资活动现金流/总资产(半年度)|筹资活动现金流/总资产(半年度)|
|FN196|double|现金及现金等价物净增加额/总资产(半年度)|现金及现金等价物净增加额/总资产(半年度)|
|FN197|double|经营活动现金流/股东权益(半年度)|经营活动现金流/股东权益(半年度)|
|FN198|double|投资活动现金流/股东权益(半年度)|投资活动现金流/股东权益(半年度)|
|FN199|double|筹资活动现金流/股东权益(半年度)|筹资活动现金流/股东权益(半年度)|
|FN200|double|现金及现金等价物净增加额/股东权益(半年度)|现金及现金等价物净增加额/股东权益(半年度)|
|FN201|double|经营活动现金流/主营业务收入(半年度)|经营活动现金流/主营业务收入(半年度)|
|FN202|double|投资活动现金流/主营业务收入(半年度)|投资活动现金流/主营业务收入(半年度)|
|FN203|double|筹资活动现金流/主营业务收入(半年度)|筹资活动现金流/主营业务收入(半年度)|
|FN204|double|现金及现金等价物净增加额/主营业务收入(半年度)|现金及现金等价物净增加额/主营业务收入(半年度)|
|FN205|double|经营活动现金流/营业利润(半年度)|经营活动现金流/营业利润(半年度)|
|FN206|double|投资活动现金流/营业利润(半年度)|投资活动现金流/营业利润(半年度)|
|FN207|double|筹资活动现金流/营业利润(半年度)|筹资活动现金流/营业利润(半年度)|
|FN208|double|现金及现金等价物净增加额/营业利润(半年度)|现金及现金等价物净增加额/营业利润(半年度)|
|FN209|double|经营活动现金流/毛利润(半年度)|经营活动现金流/毛利润(半年度)|
|FN210|double|投资活动现金流/毛利润(半年度)|投资活动现金流/毛利润(半年度)|
|FN211|double|筹资活动现金流/毛利润(半年度)|筹资活动现金流/毛利润(半年度)|
|FN212|double|现金及现金等价物净增加额/毛利润(半年度)|现金及现金等价物净增加额/毛利润(半年度)|
|FN213|double|经营活动现金流/净利润(季度累计)|经营活动现金流/净利润(季度累计)|
|FN214|double|投资活动现金流/净利润(季度累计)|投资活动现金流/净利润(季度累计)|
|FN215|double|筹资活动现金流/净利润(季度累计)|筹资活动现金流/净利润(季度累计)|
|FN216|double|现金及现金等价物净增加额/净利润(季度累计)|现金及现金等价物净增加额/净利润(季度累计)|
|FN217|double|经营活动现金流/营业收入(季度累计)|经营活动现金流/营业收入(季度累计)|
|FN218|double|投资活动现金流/营业收入(季度累计)|投资活动现金流/营业收入(季度累计)|
|FN219|double|筹资活动现金流/营业收入(季度累计)|筹资活动现金流/营业收入(季度累计)|
|FN220|double|现金及现金等价物净增加额/营业收入(季度累计)|现金及现金等价物净增加额/营业收入(季度累计)|
|FN221|double|经营活动现金流/营业利润(季度累计)|经营活动现金流/营业利润(季度累计)|
|FN222|double|投资活动现金流/营业利润(季度累计)|投资活动现金流/营业利润(季度累计)|
|FN223|double|筹资活动现金流/营业利润(季度累计)|筹资活动现金流/营业利润(季度累计)|
|FN224|double|现金及现金等价物净增加额/营业利润(季度累计)|现金及现金等价物净增加额/营业利润(季度累计)|
|FN225|double|经营活动现金流/毛利润(季度累计)|经营活动现金流/毛利润(季度累计)|
|FN226|double|投资活动现金流/毛利润(季度累计)|投资活动现金流/毛利润(季度累计)|
|FN227|double|筹资活动现金流/毛利润(季度累计)|筹资活动现金流/毛利润(季度累计)|
|FN228|double|现金及现金等价物净增加额/毛利润(季度累计)|现金及现金等价物净增加额/毛利润(季度累计)|
|FN229|double|经营活动现金流/总资产(季度累计)|经营活动现金流/总资产(季度累计)|
|FN230|double|投资活动现金流/总资产(季度累计)|投资活动现金流/总资产(季度累计)|
|FN231|double|筹资活动现金流/总资产(季度累计)|筹资活动现金流/总资产(季度累计)|
|FN232|double|现金及现金等价物净增加额/总资产(季度累计)|现金及现金等价物净增加额/总资产(季度累计)|
|FN233|double|经营活动现金流/股东权益(季度累计)|经营活动现金流/股东权益(季度累计)|
|FN234|double|投资活动现金流/股东权益(季度累计)|投资活动现金流/股东权益(季度累计)|
|FN235|double|筹资活动现金流/股东权益(季度累计)|筹资活动现金流/股东权益(季度累计)|
|FN236|double|现金及现金等价物净增加额/股东权益(季度累计)|现金及现金等价物净增加额/股东权益(季度累计)|
|FN237|double|经营活动现金流/主营业务收入(季度累计)|经营活动现金流/主营业务收入(季度累计)|
|FN238|double|投资活动现金流/主营业务收入(季度累计)|投资活动现金流/主营业务收入(季度累计)|
|FN239|double|筹资活动现金流/主营业务收入(季度累计)|筹资活动现金流/主营业务收入(季度累计)|
|FN240|double|现金及现金等价物净增加额/主营业务收入(季度累计)|现金及现金等价物净增加额/主营业务收入(季度累计)|
|FN241|double|经营活动现金流/营业利润(季度累计)|经营活动现金流/营业利润(季度累计)|
|FN242|double|投资活动现金流/营业利润(季度累计)|投资活动现金流/营业利润(季度累计)|
|FN243|double|筹资活动现金流/营业利润(季度累计)|筹资活动现金流/营业利润(季度累计)|
|FN244|double|现金及现金等价物净增加额/营业利润(季度累计)|现金及现金等价物净增加额/营业利润(季度累计)|
|FN245|double|经营活动现金流/毛利润(季度累计)|经营活动现金流/毛利润(季度累计)|
|FN246|double|投资活动现金流/毛利润(季度累计)|投资活动现金流/毛利润(季度累计)|
|FN247|double|筹资活动现金流/毛利润(季度累计)|筹资活动现金流/毛利润(季度累计)|
|FN248|double|现金及现金等价物净增加额/毛利润(季度累计)|现金及现金等价物净增加额/毛利润(季度累计)|

返回值说明

 * 返回类型：dict，键为股票代码（如 '600519.SH'），值为 pandas.DataFrame。
 * DataFrame 列：
   * 用户请求的财务字段（如 FN193, FN194 … 大写）。
   * announce_time：公告日期，格式 YYYYMMDD。
   * tag_time：报告期截止日期，格式 YYYYMMDD。
 * 行：按时间顺序排列的财务数据记录。

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

fd = tq.get_financial_data(
        stock_list=['688318.SH'],
        field_list=['Fn193','Fn194','Fn195','Fn196','Fn197'],
        start_time='20250101',
        end_time='',
        report_type='announce_time')
print(fd)
```

数据样本

```json
{'600519.SH':     FN193  FN194  FN195 FN196  FN197 announce_time  tag_time
0  164.82  70.03  15.76  8.07  36.99      20250403  20241231
1  193.43  73.19  14.16  8.03  10.39      20250430  20250331
2  166.69  70.22  15.60  8.70  19.02      20250813  20250630
3  162.47  69.67  16.07  8.71  25.14      20251030  20250930}
```

### 获取指定日期专业财务数据get_financial_data_by_date

根据股票，获取指定日期的专业财务数据，与基础财务数据不同，需要先在客户端中下载专业财务数据

```python
get_financial_data_by_date(stock_list: List[str] = [],
							field_list: List[str] = [],
							year: int = 0,
							mmdd: int = 0) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|field_list|Y|List[str]|字段筛选，不能为空（如 FN193）|
|year|Y|int|指定年份|
|mmdd|Y|int|指定月日|

 * 如果year和mmdd都为0,表示最新的财报;
 * 如果year为0,mmdd为小于300的数字,表示最近一期向前推mmdd期的数据,如果是331,630,930,1231这些,表示最近一期的对应季报的数据;
 * 如果mmdd为0,year为一数字,表示最近一期向前推year年的同期数据;
 * 季报分界点为:0331,0630,0930,1231
 * 需要先在客户端中下载财务数据包

输出数据

同get_financial_data一样。

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

fd = tq.get_financial_data_by_date(
        stock_list=['688318.SH'],
        field_list=['Fn193','Fn194','Fn195','Fn196','Fn197'],
        year=0,
        mmdd=0)
print(fd)
```

数据样本

```json
{'600519.SH':
{'FN193': '162.47',
'FN194': '69.67',
'FN195': '16.07',
'FN196': '8.71',
'FN197': '25.14'}}
```

### 获取板块交易数据get_bkjy_value

根据板块代码，获取指定时间段内的板块交易数据，需要先在客户端中下载股票数据包

```python
get_bkjy_value(stock_list: List[str] = [],
				field_list: List[str] = [],
				start_time: str = '',
				end_time: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|field_list|Y|List[str]|字段筛选，不能为空|
|start_time|N|str|起始时间|
|end_time|N|str|结束时间|

输出数据

|名称|类型|数值|说明|
|---|---|---|---|
|BK5|double|市盈率TTM 整体法 算术平均|
|BK6|double|市净率MRQ 整体法 算术平均|
|BK7|double|市销率TTM 整体法 算术平均|
|BK8|double|市现率TTM 整体法 算术平均|
|BK9|double|涨跌数 上涨家数 下跌家数|
|BK10|double|板块总市值(亿元) 整体法 算术平均|
|BK11|double|板块流通市值(亿元) 整体法 算术平均|
|BK12|double|涨停数 涨停家数 曾涨停家数[注：该指标展示20160926日之后的数据]|
|BK13|double|跌停数 跌停家数 曾跌停家数[注：该指标展示20160926日之后的数据]|
|BK14|double|涨停数据 市场高度(不含ST股和未开板新股) 2板及以上涨停个数(不含ST股和未开板新股)[注：该指标展示20180319日之后的数据]|
|BK15|double|融资融券 沪深京融资余额(万元) 沪深京融券余额(万元)|
|BK16|double|陆股通资金流入 沪股通流入金额(亿元) 深股通流入金额(亿元) [注：该指标展示20170320日之后的数据]|
|BK17|double|开盘成交数 开盘成交额(万元) 开盘成交量(万股)|
|BK18|double|板块股息率(%) 算数平均 整体法|
|BK19|double|板块自由流通市值(亿元) 整体法 算术平均|

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

bk_data = tq.get_bkjy_value(stock_list=['880660.SH'],
        field_list=['BK5','BK6','BK7','BK8','BK9'],
        start_time='20250101',
        end_time='20250102')
print(bk_data)
```

数据样本

```json
{'880660.SH': {'BK5': [{'Date': '20250102', 'Value': ['55.28', '55.50']}],
'BK6': [{'Date': '20250102', 'Value': ['4.62', '3.79']}],
'BK7': [{'Date': '20250102', 'Value': ['5.25', '8.22']}],
'BK8': [{'Date': '20250102', 'Value': ['46.52', '312.41']}],
'BK9': [{'Date': '20250102', 'Value': ['0.00', '35.00']}, {'Date': '20260130', 'Value': ['10.00', '25.00']}]}}
```

### 获取指定日期板块交易数据get_bkjy_value_by_date

根据板块代码，获取指定日期的板块交易数据，需要先在客户端中下载股票数据包

```python
get_bkjy_value_by_date(stock_list: List[str] = [],
							field_list: List[str] = [],
							year: int = 0,
							mmdd: int = 0) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|field_list|Y|List[str]|字段筛选，不能为空|
|year|Y|int|指定年份|
|mmdd|Y|int|指定月日|

 * 如果year为0,mmdd为0,表示最新数据,mmdd为1,2,3...,表示倒数第2,3,4...个数据。
 * 需要先在客户端中下载股票数据包

输出数据

同get_bkjy_value一样。

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

bk_one = tq.get_bkjy_value_by_date(stock_list=['880660.SH'],
                                   field_list=['BK9','BK10','BK11','BK12','BK13'],
                                   year=0,mmdd=0)
print(bk_one)
```

数据样本

```json
{'880660.SH': {'BK10': ['6705.83', '191.60'], 'BK11': ['6183.65', '176.68'], 'BK12': ['0.00', '0.00'], 'BK13': ['0.00', '0.00'], 'BK9': ['3.00', '31.00']}}
```

### 获取股票交易数据get_gpjy_value

根据股票，获取指定时间段内的股票交易数据，需要先在客户端中下载股票数据包

```python
get_gpjy_value(stock_list: List[str] = [],
				field_list: List[str] = [],
				start_time: str = '',
				end_time: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|field_list|Y|List[str]|字段筛选，不能为空|
|start_time|N|str|起始时间|
|end_time|N|str|结束时间|

输出数据

|名称|类型|数值|说明|
|---|---|---|---|
|GP01|double|股东人数 股东户数(户)|
|GP02|double|龙虎榜 买入总计(万元) 卖出总计(万元)[注：该指标展示20230717日之后的数据]|
|GP03|double|融资融券1 融资余额(万元) 融券余量(股)|
|GP04|double|大宗交易 成交均价(元) 成交额(万元)|
|GP05|double|增减持1 成交均价(元) 变动股数(股)|
|GP06|double|陆股通持股量 持股数量(股)[注：该指标展示20170317日之后的数据]|
|GP07|double|陆股通市场成交净额 陆股通市场净买入(万元)[注：官方只公布了每日的前十名数据]|
|GP08|double|龙虎榜机构(卖方)数据 卖方机构个数 机构卖出金额(万元)|
|GP09|double|龙虎榜机构(买方)数据 买方机构个数 机构买入金额(万元)|
|GP10|double|近3月机构调研情况 近3月机构调研次数 近3月调研机构数量|
|GP11|double|融资融券2 融资买入额(万元) 融资偿还额(万元)|
|GP12|double|融资融券3 融券卖出量(股) 融券偿还量(股)|
|GP13|double|融资融券4 融资净买入(万元) 融券净卖出(股)|
|GP14|double|涨停数据 涨停金额(即板上成交,万元) 开板次数[注：该指标展示20180319日之后的数据]|
|GP15|double|涨跌停 涨跌停状态 封单金额(万元)[注：涨停取2,曾涨停取1,跌停取-2,曾跌停取-1;跌停和曾跌停时,封单金额取负值 该指标展示20160926日之后的数据]|
|GP16|double|总市值 总市值(万元)|
|GP17|double|龙虎榜营业部数据 买入金额(万元) 卖出金额(万元)|
|GP18|double|龙虎榜沪深股通数据 买入金额(万元) 卖出金额(万元)|
|GP19|double|每周股票质押数量 无限售股份质押数(万) 有限售股份质押数(万)[注：该指标展示20180316日之后的数据]|
|GP20|double|每周股票质押比例 质押比例(%)[注：该指标展示20180316日之后的数据]|
|GP21|double|股息率 股息率(%)|
|GP22|double|涨跌停 封成比 封流比[注：该指标展示20180319日之后的数据]|
|GP23|double|拟增减持 拟增持数量(万股) 拟减持数量(万股)|
|GP24|double|涨停 首次涨停时间 涨停最大封单额(万) [注：首次涨停时间展示20160301之后的数据，涨停最大封单额展示20200730之后的数据]|
|GP25|double|盘前盘后成交量 开盘成交量(手) 盘后固定成交量(手) [注：盘后固定成交量只包含科创板和创业板]|
|GP26|double|拟增减持金额 拟增持金额(万元) 拟减持金额(万元)|

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

gp_data = tq.get_gpjy_value(stock_list=['688318.SH'],
        field_list=['GP1','GP2','GP3','GP4','GP5'],
        start_time='20250101',
        end_time='20250102')
print(gp_data)
```

### 获取指定日期股票交易数据get_gpjy_value_by_date

根据股票，获取指定时间段内的股票交易数据，需要先在客户端中下载股票数据包

```python
def get_gpjy_value_by_date(stock_list: List[str] = [],
							field_list: List[str] = [],
							year: int = 0,
							mmdd: int = 0) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|field_list|Y|List[str]|字段筛选，不能为空|
|year|Y|int|指定年份|
|mmdd|Y|int|指定月日|

 * 如果year为0,mmdd为0,表示最新数据,mmdd为1,2,3...,表示倒数第2,3,4...个数据。
 * 需要先在客户端中下载股票数据包

输出数据

同get_gpjy_value一样。

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

gp_one = tq.get_gpjy_value_by_date(
        stock_list=['688318.SH'],
        field_list=['GP1','GP2','GP3','GP4','GP5'],
        year=0,mmdd=0)
print(gp_one)
```

数据样本

```json
{'688318.SH': {'GP1': ['24154.00', '0.00'], 'GP2': ['20574.12', '18728.85'], 'GP3': ['140464.83', '55043.00'], 'GP4': ['169.80', '5943.00'], 'GP5': ['103.00', '-7000.00']}}
```

### 获取股票的单个财务数据get_gp_one_data

根据证券代码，获取股票的单个数据

```python
get_gp_one_data(stock_list: List[str] = [],
				field_list: List[str] = []) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|field_list|Y|List[str]|字段筛选，不能为空（如 GO47表示是第47号个股数据最新业绩预告 本期扣非净利润预计同比增减幅上限%）这个值，GO为gp one的首字母大写|

输出数据

|名称|类型|数值|说明|
|---|---|---|---|
|GO1|double|发行价(元)|
|GO2|double|总发行数量(万股)|
|GO3|double|一致预期目标价(元)[注：一致预期值均为近半年内各家机构预测数值的平均值]|
|GO4|double|一致预期T年度|
|GO5|double|一致预期T年每股收益|
|GO6|double|一致预期T+1年每股收益|
|GO7|double|一致预期T+2年每股收益|
|GO8|double|一致预期T年净利润(万元)|
|GO9|double|一致预期T+1年净利润(万元)|
|GO10|double|一致预期T+2年净利润(万元)|
|GO11|double|一致预期T年营业收入(万元)|
|GO12|double|一致预期T+1年营业收入(万元)|
|GO13|double|一致预期T+2年营业收入(万元)|
|GO14|double|一致预期T年营业利润(万元)|
|GO15|double|一致预期T+1年营业利润(万元)|
|GO16|double|一致预期T+2年营业利润(万元)|
|GO17|double|一致预期T年每股净资产(元)|
|GO18|double|一致预期T+1年每股净资产(元)|
|GO19|double|一致预期T+2年每股净资产(元)|
|GO20|double|一致预期T年净资产收益率(%)|
|GO21|double|一致预期T+1年净资产收益率(%)|
|GO22|double|一致预期T+2年净资产收益率(%)|
|GO23|double|一致预期T年PE|
|GO24|double|一致预期T+1年PE|
|GO25|double|一致预期T+2年PE|
|GO26|double|最新解禁日(YYMMDD格式)|
|GO27|double|最新解禁数量（万股）|
|GO28|double|下一报告期的预约披露时间|
|GO29|double|最新持股机构家数|
|GO30|double|最新机构持股总量（万股）|
|GO31|double|最新持股基金家数|
|GO32|double|最新基金持股量（万股）|
|GO33|double|最新总股本（万股）|
|GO34|double|最新实际流通A股（万股）|
|GO35|double|最新业绩预告 报告期(YYMMDD格式)|
|GO36|double|最新业绩预告 本期归母净利润下限（万元）|
|GO37|double|最新业绩预告 本期归母净利润上限（万元）|
|GO38|double|最新业绩预告 本期归母净利润预计同比增减幅下限%|
|GO39|double|最新业绩预告 本期归母净利润预计同比增减幅上限%|
|GO40|double|最新业绩快报 报告期|
|GO41|double|最新业绩快报 归母净利润（万元）|
|GO42|double|分红募资 派现总额（万元）|

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

gp_one = tq.get_gp_one_data(
        stock_list=['688318.SH'],
        field_list=['GO1','GO2','GO3','GO4','GO5'])
print(gp_one)
```

### 获取市场交易数据get_scjy_value

获取指定时间段内的市场交易数据，需要先在客户端中下载股票数据包

```python
get_scjy_value(field_list: List[str] = [],
				start_time: str = '',
				end_time: str = '') -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|field_list|Y|List[str]|字段筛选，不能为空|
|start_time|N|str|起始时间|
|end_time|N|str|结束时间|

输出数据

|名称|类型|数值|说明|
|---|---|---|---|
|SC01|double|融资融券 沪深京融资余额(万元) 沪深京融券余额(万元)|
|SC02|double|陆股通资金流入 沪股通流入金额(亿元) 深股通流入金额(亿元)[注：沪股通限制展示2000条数据，深股通展示自20161205以后的数据]|
|SC03|double|沪深京涨停股个数 涨停股个数 曾涨停股个数 [注：该指标展示20160926日之后的数据]|
|SC04|double|沪深京跌停股个数 跌停股个数 曾跌停股个数 [注：该指标展示20160926日之后的数据]|
|SC05|double|上证50股指期货 净持仓(手)[注：该指标展示20171009日之后的数据]|
|SC06|double|沪深300股指期货 净持仓(手) [注：该指标展示20171009日之后的数据]|
|SC07|double|中证500股指期货 净持仓(手) [注：该指标展示20171009日之后的数据]|
|SC08|double|ETF基金规模份额数据 ETF基金规模(亿份) ETF净申赎(亿份)|
|SC09|double|沪月新开A股账户 沪月新开A股账户(万户)|
|SC10|double|增减持统计 增持额(万元) 减持额(万元)[注：部分公司公告滞后,造成每天查看的数据可能会不一样]|
|SC11|double|大宗交易 溢价的大宗交易额(万元) 折价的大宗交易额(万元)|
|SC12|double|限售解禁 限售解禁计划额(亿元) 限售解禁股份实际上市金额(亿元)[注：该指标展示201802月之后的数据;部分股票的解禁日期延后，造成不同日期提取的某天的计划额可能不同]|
|SC13|double|分红 市场总分红额(亿元)[注：除权派息日的A股市场总分红额]|
|SC14|double|募资 市场总募资额(亿元)[注：发行日期/除权日期的首发、配股和增发的总募资额]|
|SC15|double|打板资金 封板成功资金(亿元) 封板失败资金(亿元) [注：该指标展示20160926日之后的数据]|
|SC16|double|龙虎榜 买入总金额(亿元) 卖出总金额(亿元)|
|SC17|double|龙虎榜机构数据 买入金额(亿元) 卖出金额(亿元)|
|SC18|double|龙虎榜营业部数据 买入金额(亿元) 卖出金额(亿元)|
|SC19|double|龙虎榜沪深股通数据 买入金额(亿元) 卖出金额(亿元)|
|SC20|double|陆股通净买入 沪股通净买入额(亿元) 深股通净买入额(亿元)|
|SC21|double|每周无限售质押率 深市质押率(%) 沪市质押率(%)[注：该指标展示20180128日之后的数据]|
|SC22|double|每周有限售质押率 深市质押率(%) 沪市质押率(%)[注：该指标展示20180128日之后的数据]|
|SC23|double|连板家数 连板股个数(包含ST和未开板新股) 连板股个数(不含ST股和未开板新股）[注：该指标展示20180319日之后的数据]|
|SC24|double|沪深京涨跌停股个数 涨停股个数(不含ST股和未开板新股)|

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

sc_data = tq.get_scjy_value(
        field_list=['SC1','SC2','SC3','SC4','SC5'],
        start_time='20250101',
        end_time='20250102')
print(sc_data)
```

### 获取指定日期市场交易数据get_scjy_value_by_date

获取指定时间的市场交易数据，需要先在客户端中下载股票数据包

```python
get_scjy_value_by_date(field_list: List[str] = [],
						year: int = 0,
						mmdd: int = 0) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|field_list|Y|List[str]|字段筛选，不能为空|
|year|Y|int|指定年份|
|mmdd|Y|int|指定月日|

 * 如果year为0,mmdd为0,表示最新数据,mmdd为1,2,3...,表示倒数第2,3,4...个数据。
 * 需要先在客户端中下载股票数据包

输出数据

同get_scjy_value一样。

接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

sc_one = tq.get_scjy_value_by_date(field_list=['SC6','SC7','SC8','SC9','SC10'],year=0,mmdd=0)
print(sc_one)
```

数据样本

```json
{'SC10': ['0.00', '181415.13'], 'SC6': ['-30479.00', '0.00'], 'SC7': ['-26449.00', '0.00'], 'SC8': ['31752.86', '84.22'], 'SC9': ['993000.00', '2900.00']}
```

## 自定义板块相关

### 创建自定义板块 create_sector

在通达信客户端中创建自定义板块

```python
create_sector(block_code:str = '',
				block_name:str = ''):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|block_code|Y|str|自定义板块简称|
|block_name|Y|str|自定义板块名称|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
create_ptr = tq.create_sector(block_code='CSBK2', block_name='测试板块2')
print(create_ptr)
```

数据样本

```json
{
   "Error" : "创建CSBK2板块成功",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

### 删除自定义板块 delete_sector

删除通达信客户端中的自定义板块

```python
delete_sector(block_code:str = ''):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|block_code|Y|str|自定义板块简称|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
delete_ptr = tq.delete_sector(block_code='CSBK')
print(delete_ptr)
```

数据样本

```json
{
   "Error" : "删除CSBK板块成功",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

### 重命名自定义板块 rename_sector

重命名通达信客户端中的自定义板块

```python
rename_sector(block_code:str = '',
				block_name:str = ''):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|block_code|Y|str|自定义板块简称|
|block_name|Y|str|重命名后的自定义板块名称|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
rename_ptr = tq.rename_sector(block_code='CSBK', block_name='测试板块重命名')
print(rename_ptr)
```

数据样本

```json
{
   "Error" : "重命名CSBK板块成功",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

### 清空自定义板块成份股 clear_sector

清空指定通达信客户端自定义板块的成份股

```python
clear_sector(block_code:str = ''):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|block_code|Y|str|自定义板块简称|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
clear_ptr = tq.clear_sector(block_code='CSBK')
print(clear_ptr)
```

数据样本

```json
{
   "Error" : "清空CSBK板块成功",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

### 添加自定义板块成份股 send_user_block

往指定自定义板块中添加成份股

```python
send_user_block(block_code: str = '',
                stocks: List[str] = [],
                show: bool = False) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|block_code|Y|str|自定义板块简称|
|stocks|Y|List[str]|添加的自选股|
|show|N|str|客户端是否切换至对应板块界面|

 * block_code 为客户端已有的自定义板块简称，如果不存在则无效果，空则为添加到临时条件股
 * block_code存在，传入空列表则表示清空该板块所有股票，否则为添加新股票
 * 自选股的block_code为ZXG

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
zxg_result = tq.send_user_block(block_code='CSBK', stocks=["600000.SH","600004.SH","000001.SZ","000002.SZ"])
```

数据样本

```json
{'Error': 'Add User Block Completed', 'ErrorId': '0', 'run_id': '1'}
```

### 获取自定义板块列表 get_user_sector

获取自定义板块代码列表

```python
get_user_sector(cls) -> List:
```

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
user_list = tq.get_user_sector()
print(user_list)
print(len(user_list))
```

数据样本

```python
[{'Code': 'CSBK', 'Name': '测试板块'}, {'Code': 'CSBK2', 'Name': '测试板块2'}]
```

### 获取A股板块代码列表 get_sector_list

获取A股全部板块代码列表

```python
def get_sector_list(list_type: int = 0) -> List:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|list_type|Y|int|返回数据类型|

 * list_type = 0 只返回代码，list_type = 1 返回代码和名称

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
block_list = tq.get_sector_list()
print(block_list)
block_list2 = tq.get_sector_list(list_type = 1)
print(block_list2)
```

注：此接口相当于 get_stock_list('10')

数据样本

```python
['880081.SH', '880082.SH', '880201.SH', '880202.SH', '880203.SH', '880204.SH', '880205.SH', '880206.SH', '880207.SH', '880208.SH', ...]

[{'Code': '880081.SH', 'Name': '轮动趋势'}, {'Code': '880082.SH', 'Name': '板块趋势'}, {'Code': '880201.SH', 'Name': '黑龙江'}, {'Code': '880202.SH', 'Name': '新疆板块'}, {'Code': '880203.SH', 'Name': '吉林板块'}, {'Code': '880204.SH', 'Name': '甘肃板块'}, {'Code': '880205.SH', 'Name': '辽宁板块'}, {'Code': '880206.SH', 'Name': '青海板块'}, {'Code': '880207.SH', 'Name': '北京板块'},...]
```

### 获取板块成份股 get_stock_list_in_sector

根据板块代码获取其成份股列表

```python
def get_stock_list_in_sector(block_code: str,
                         block_type: int = 0,
                         list_type: int = 0) -> List:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|block_code|Y|str|板块代码|
|block_type|N|str|板块类型|
|list_type|Y|int|返回数据类型|

 * 获取A股成份股时支持板块名称或板块代码两种方式传入
 * block_type=0 表示传入板块指数代码或板块指数名称（默认）
 * block_type=1 表示传入自定义板块简称 需要是客户端中预先定义好自定义板块的简称 如果是ZXG表示是自选股；TJG表示是临时条件股
 * list_type = 0 只返回代码，list_type = 1 返回代码和名称

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
#通过板块代码获取成份股
block_stocks = tq.get_stock_list_in_sector('880081.SH')
print(block_stocks)
print(len(block_stocks))

#通过板块名获取成份股
block_stocks = tq.get_stock_list_in_sector('钛金属')
print(block_stocks)
print(len(block_stocks))

block_stocks2 = tq.get_stock_list_in_sector('钛金属',list_type=1)
print(block_stocks2)

#获取自定义板块成份股
block_stocks = tq.get_stock_list_in_sector('CSBK', block_type = 1)
print(block_stocks)
print(len(block_stocks))
```

数据样本

```python
['159922.SZ', '510500.SH', '512500.SH']
3
['000545.SZ', '000629.SZ', '000635.SZ', '000688.SZ', '000709.SZ', '000962.SZ', '002136.SZ', '002140.SZ', '002145.SZ', '002149.SZ', '002167.SZ', '002386.SZ', '002601.SZ', '002978.SZ', '300402.SZ', '300891.SZ', '600456.SH', '600727.SH', '603067.SH', '603826.SH', '688122.SH', '688750.SH', '920068.BJ']
23
[{'Code': '000545.SZ', 'Name': '金浦钛业'}, {'Code': '000629.SZ', 'Name': '钒钛股份'}, {'Code': '000635.SZ', 'Name': '英 力 特'}, {'Code': '000688.SZ', 'Name': '国城矿业'}, {'Code': '000709.SZ', 'Name': '河钢股份'}, {'Code': '000962.SZ', 'Name': '东方钽业'}, {'Code': '002136.SZ', 'Name': '安 纳 达'}, {'Code': '002140.SZ', 'Name': '东华科技'}, {'Code': '002145.SZ', 'Name': '钛能化学'}, {'Code': '002149.SZ', 'Name': '西部材料'}, {'Code': '002167.SZ', 'Name': '东方锆业'}, {'Code': '002386.SZ', 'Name': '天原股份'}, {'Code': '002601.SZ', 'Name': '龙佰集团'}, {'Code': '002978.SZ', 'Name': '安宁股份'}, {'Code': '300402.SZ', 'Name': '宝色股份'}, {'Code': '300891.SZ', 'Name': '惠云钛业'}, {'Code': '600456.SH', 'Name': '宝钛股份'}, {'Code': '600727.SH', 'Name': '鲁北化工'}, {'Code': '603067.SH', 'Name': '振华股份'}, {'Code': '603826.SH', 'Name': '坤彩科技'}, {'Code': '688122.SH', 'Name': '西部超导'}, {'Code': '688750.SH', 'Name': '宝武碳业'}, {'Code': '920068.BJ', 'Name': '路斯股份'}]
```

## ETF/可转债/期货数据

### 获取可转债信息 get_kzz_info

根据可转债代码获取可转债信息

```python
def get_kzz_info(stock_code:str = '',
				field_list: List[str] = []):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|可转债代码|
|field_list|N|List[str]|字段筛选，传空则返回全部|

输出数据

|名称|类型|说明|
|---|---|---|
|SetCode|str|证券市场|
|KZZCode|str|可转债代码|
|HSCode|str|正股代码|
|ZGPrice|str|转股价格|
|CurRate|str|当期利率|
|RestScope|str|剩余规模(万)|
|PutBack|str|回售触发价|
|ForceRedeem|str|强赎触发价|
|ZGDate|str|转股日|
|EndPrice|str|到期价|
|EndDate|str|到期日期|
|ZGRate|str|转股比率%|
|RealValue|str|纯债价值|
|ExpireYield|str|到期收益率%|
|KZZScore|str|可转债评级|
|HSScore|str|主体评级|
|RedeemDate|str|赎回登记日期|
|RedeemPrice|str|赎回价格|
|PutDate|str|回售申报起始日期|
|PutPrice|str|回售价格|
|ZGCode|str|转股代码|
|AGPrice|str|正股当前价格|
|KZZPrice|str|可转债当前价格|
|KZZYj|str|溢价率|
|ZGValue|str|转股价值|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
kzz_info = tq.get_kzz_info(stock_code = '123039.SZ')
print(kzz_info)
```

数据样本

```json
{'CurRate': '2.80',
'EndDate': '20251226',
'EndPrice': '115.00',
'ExpireYield': '0.00',
'ForceRedeem': '37.90',
'HSCode': '300577',
'HSScore': 'A+',
'KZZCode': '123039',
'KZZScore': 'A+',
'PutBack': '20.41',
'PutDate': '0',
'PutPrice': '0.00',
'RealValue': '0.00',
'RedeemDate': '0',
'RedeemPrice': '0.00',
'RestScope': '22044.02',
'ZGCode': '123039',
'ZGDate': '20200702',
'ZGPrice': '29.15',
'ZGRate': '1.15',
'setcode': '0'}
```

### 获取新股申购信息get_ipo_info

获取今天及未来的新股或新发债申购信息

```python
get_ipo_info(ipo_type:int = 0,
             ipo_date:int = 0):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|ipo_type|Y|int|ipo_type=0 表示获取新股申购信息，ipo_type=1 表示获取新发债信息，ipo_type=2 表示获取新股和新发债信息|
|ipo_date|Y|int|ipo_date=0 表示只获取今天信息，ipo_date=1 表示获取今天及以后信息|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
ipo_info = tq.get_ipo_info(ipo_type=2, ipo_date=1)
print(ipo_info)
```

数据样本

```json
[{'MaxSG': '0.00', 'PE_Issue': '0.00', 'SGCode': '371036', 'SGDate': '20251226', 'SGPrice': '100.00', 'code': '301036', 'name': '双乐转债', 'setcode': '0'},
{'MaxSG': '0.00', 'PE_Issue': '0.00', 'SGCode': '718676', 'SGDate': '20251225', 'SGPrice': '100.00', 'code': '688676', 'name': '金05转债', 'setcode': '1'}]
```

### 获取跟踪指数的ETF信息 get_trackzs_etf_info

根据指数代码获取跟踪它的ETF的信息

```python
def get_trackzs_etf_info(zs_code: str = ''):
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|zs_code|Y|str|指数代码|

输出数据

|名称|类型|说明|
|---|---|---|
|Code|str|证券代码|
|Name|str|证券名称|
|NowPrice|str|现价|
|PreClose|str|昨收|
|IOPV|str|净值|
|Zgb|str|净额（万份）|
|Sz|str|规模（亿元）|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)

trackzs_etf_info = tq.get_trackzs_etf_info(zs_code='950162.CSI')
print(trackzs_etf_info)
```

数据样本

```python
[{'Code': '589210.SH', 'Name': '科创芯片设计ETF', 'NowPrice': '1.208', 'PreClose': '1.192', 'IOPV': '1.2071', 'Zgb': '7646.90', 'Sz': '0.92'},
{'Code': '589070.SH', 'Name': '科创芯片设计ETF', 'NowPrice': '0.954', 'PreClose': '0.942', 'IOPV': '0.9547', 'Zgb': '65129.30', 'Sz': '6.21'},
{'Code': '588780.SH', 'Name': ' 科创芯片设计ETF', 'NowPrice': '0.875', 'PreClose': '0.866', 'IOPV': '0.8756', 'Zgb': '106790.20', 'Sz': '9.34'},
{'Code': '589170.SH', 'Name': '科创芯片设计ETF', 'NowPrice': '0.969', 'PreClose': '0.956', 'IOPV': '0.9685', 'Zgb': '37890.90', 'Sz': '3.67'},
{'Code': '589250.SH', 'Name': '芯设计PY', 'NowPrice': '0.000', 'PreClose': '0.000', 'IOPV': '0.0000', 'Zgb': '0.00', 'Sz': '0.00'},
{'Code': '589030.SH', 'Name': '科创芯片设计ETF', 'NowPrice': '1.013', 'PreClose': '1.000', 'IOPV': '1.0130', 'Zgb': '48407.70', 'Sz': '4.90'}]
```

## 调用通达信公式

### 格式化K线数据formula_format_data

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
{'Date': '2026-01-26 00:00:00', 'Amount': 54141.73, 'Volume': 3761141.0, 'Close': 141.84, 'Open': 143.7, 'High': 146.77, 'Low': 141.8}]
}
```

### 向通达信公式系统设置数据formula_set_data

向通达信公式系统设置数据

```python
formula_set_data(data: Dict) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|data|Y|Dict|数据|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
set_result = tq.formula_set_data(data={'Close': [10, 20, 30, 40, 50]})
print(set_result)
```

### 向通达信公式系统设置数据信息formula_set_data_info

向通达信公式系统设置数据信息

```python
formula_set_data_info(info: Dict) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|info|Y|Dict|数据信息|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
set_info_result = tq.formula_set_data_info(info={'Name': 'Test', 'Period': '1d'})
print(set_info_result)
```

### 获取公式中的设置数据formula_get_data

获取公式中的设置数据

```python
formula_get_data() -> Dict:
```

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
get_data = tq.formula_get_data()
print(get_data)
```

### 调用通达信技术指标公式formula_zb

调用通达信技术指标公式

```python
formula_zb(stock_code: str = '',
			formula_name: str = '',
			params: List[float] = [],
			xsflag: int = 2) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|
|formula_name|Y|str|公式名称|
|params|N|List[float]|公式参数|
|xsflag|N|int|小数位数|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
zb_result = tq.formula_zb(
    stock_code='688318.SH',
    formula_name='MA',
    params=[5, 10, 20],
    xsflag=2
)
print(zb_result)
```

### 调用通达信专家系统公式formula_exp

调用通达信专家系统公式

```python
formula_exp(stock_code: str = '',
			formula_name: str = '',
			params: List[float] = []) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|
|formula_name|Y|str|公式名称|
|params|N|List[float]|公式参数|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
exp_result = tq.formula_exp(
    stock_code='688318.SH',
    formula_name='CCI',
    params=[12]
)
print(exp_result)
```

### 调用通达信条件选股公式formula_xg

调用通达信条件选股公式

```python
formula_xg(stock_code: str = '',
			formula_name: str = '',
			params: List[float] = []) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_code|Y|str|证券代码|
|formula_name|Y|str|公式名称|
|params|N|List[float]|公式参数|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
xg_result = tq.formula_xg(
    stock_code='688318.SH',
    formula_name='MACD',
    params=[12, 26, 9]
)
print(xg_result)
```

### 批量调用通达信公式formula_process

批量调用通达信公式

```python
formula_process(stock_list: List[str] = [],
				formula_name: str = '',
				params: List[float] = [],
				return_count: int = 1) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|formula_name|Y|str|公式名称|
|params|N|List[float]|公式参数|
|return_count|N|int|返回数据个数|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
process_result = tq.formula_process(
    stock_list=['688318.SH', '600519.SH'],
    formula_name='MA',
    params=[5, 10, 20],
    return_count=1
)
print(process_result)
```

### 批量调用选股公式formula_process_mul_xg

批量调用选股公式

```python
formula_process_mul_xg(stock_list: List[str] = [],
							formula_name: str = '',
							params: List[float] = [],
							return_count: int = 1) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|formula_name|Y|str|公式名称|
|params|N|List[float]|公式参数|
|return_count|N|int|返回数据个数|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
mul_xg_result = tq.formula_process_mul_xg(
    stock_list=['688318.SH', '600519.SH'],
    formula_name='MACD',
    params=[12, 26, 9],
    return_count=1
)
print(mul_xg_result)
```

### 批量调用指标公式formula_process_mul_zb

批量调用指标公式

```python
formula_process_mul_zb(stock_list: List[str] = [],
							formula_name: str = '',
							params: List[float] = [],
							return_count: int = 1) -> Dict:
```

输入参数

|参数|是否必选|参数类型|参数说明|
|---|---|---|---|
|stock_list|Y|List[str]|证券代码列表|
|formula_name|Y|str|公式名称|
|params|N|List[float]|公式参数|
|return_count|N|int|返回数据个数|

接口使用

```python
from tqcenter import tq
tq.initialize(__file__)
mul_zb_result = tq.formula_process_mul_zb(
    stock_list=['688318.SH', '600519.SH'],
    formula_name='MA',
    params=[5, 10, 20],
    return_count=1
)
print(mul_zb_result)
```

## 常量枚举

### 市场类型

|名称|类型|数值|说明|
|---|---|---|---|
|.SZ|int|0|深圳交易所|
|.SH|int|1|上海交易所|
|.BJ|int|2|北京交易所|
|.NQ|int|44|新三板|
|.SHO|int|8|上海个股期权|
|.SZO|int|9|深圳个股期权|
|.HK|int|31|香港交易所|
|.US|int|74|美国股票|
|.CSI|int|62|中证指数|
|.CNI|int|102|国证指数|
|.HG|int|38|国内宏观指标|
|.CFF|int|47|中金期货|
|.CZC|int|28|郑州期货|
|.DCE|int|29|大连期货|
|.SHF|int|30|上海期货|
|.GFE|int|66|广州期货|
|.INE|int|30|上海能源|
|.HI|int|27|港股指数|
|.OF|int|33|开放式基金净值|
|.CFFO|int|7|中金所期权|
|.CZCO|int|4|郑州期货期权|
|.DCEO|int|5|大连期货期权|
|.SHFO|int|6|上海期货期权|
|.GFEO|int|67|广州期货期权|

### dividend_type复权类型

|名称|类型|数值|说明|
|---|---|---|---|
|type|str|none|不复权|
|type|str|front|前复权|
|type|str|back|后复权|

### period周期入参类型

|名称|类型|数值|说明|
|---|---|---|---|
|period|str|1m|1分钟|
|period|str|5m|5分钟|
|period|str|15m|15分钟|
|period|str|30m|30分钟|
|period|str|1h|60分钟（1小时）|
|period|str|1d|1天|
|period|str|1w|1周|
|period|str|1mon|1月|
|period|str|1q|1季|
|period|str|1y|1年|
|period|str|tick|分笔|

### order_type类型

|名称|类型|数值|说明|
|---|---|---|---|
|STOCK_BUY|int|0|买|
|STOCK_SELL|int|1|卖|
|CREDIT_BUY|int|0|担保品买入|
|CREDIT_SELL|int|1|担保品卖出|
|CREDIT_FIN_BUY|int|69|融资买入|
|CREDIT_SLO_SELL|int|70|融券卖出|

### price_type类型

|名称|类型|数值|说明|
|---|---|---|---|
|PRICE_MY|int|0|自填价|
|PRICE_SJ|int|1|市价|
|PRICE_ZTJ|int|2|涨停价/笼子上限|
|PRICE_DTJ|int|3|跌停价/笼子下限|

### Status类型

|名称|类型|数值|说明|
|---|---|---|---|
|WTSTATUS_NULL|int|0|无效单|
|WTSTATUS_NOCJ|int|1|未成交|
|WTSTATUS_PARTCJ|int|2|部分成交|
|WTSTATUS_ALLCJ|int|3|全部成交|
|WTSTATUS_BCBC|int|4|部分成交部分撤单|
|WTSTATUS_ALLCD|int|5|全部撤单|

## TdxQuant 简介

TdxQuant是由深圳市财富趋势科技股份有限公司研发的专业量化投研平台，专注于为国内量化投资者提供从策略研究到投资决策的全流程解决方案。平台以高效、简洁为核心设计理念，致力于降低量化交易门槛，提升策略开发与执行的效率。

依托通达信近三十余年在金融科技领域的深厚积累，TdxQuant集成了完备的实时和历史行情数据、金融数据库及稳定的交易系统基础设施，为策略的研发、回测、验证和执行提供了坚实可靠的技术支持。

平台采用分层化、模块化的服务体系，可灵活适配从高校学生、独立研究者、个人投资者到专业机构等不同用户的需求，实现从策略构思到交易落地的无缝衔接。

### TdxQuant 服务介绍

TdxQuant 是一套基于通达信金融终端构建的 Python 量化策略运行框架。该框架通过 API 接口形式，为策略交易提供所需的行情数据获取与交易指令执行功能。

### 运行环境要求

TdxQuant 支持 64 位 Python 3.7、3.8、3.9、3.10、3.11、3.12、3.13、3.14等版本，系统会自动适配当前 Python 版本，建议使用3.13版本。
请注意：运行 TdxQuant 程序前，需预先启动支持TQ策略功能的 通达信金融终端、量化模拟版或专业研究版等版本。

### 核心运行逻辑

TdxQuant 以 tqcenter 行情模块为核心，专注于为量化交易者提供高效、直接的数据服务，主要包含以下内容：

 * 行情数据：实时与历史的快照、K 线、分笔（Tick）数据
 * 基本面数据：除权除息、基本财务、专业财务、股票交易数据、市场数据等
 * 新股和合约等信息：标的基础信息、可转债、新股申购等
 * 分类数据：市场类型、行业分类、自定义板块等

### 核心应用场景

TdxQuant提供覆盖量化投研全流程的核心功能模块，主要应用场景包括：

#### 1. 策略研发与历史回测

平台提供“即用型”标准化数据。所有历史与实时数据均在服务端完成清洗、对齐，并预加载至客户端。支持用户快速获取指定时间维度的历史数据，并进行策略信号计算与回测分析。既提供复权因子，也提供各种类型的复权后的数据。

#### 2. 实时监控与信号预警

支持实时行情数据订阅，用户可基于自定义的指标与因子模型进行在线计算。当预设条件触发时，系统通过信号接口实时推送预警信息至客户端，助力研究者及时捕捉市场动态与交易机会。

#### 3. 交易模拟与实盘执行

平台构建了完整的策略交易闭环，提供模拟交易、券商实盘等两种执行环境：

 * 模拟交易：在仿真市场环境中，使用实时行情数据对策略进行持续跟踪与验证，评估其实际表现，全程无资金风险。
 * 实盘交易：通过稳定的交易总线，安全对接券商报盘系统，实现策略信号的自动化、高可靠性下单与交易管理。

### 量化交易的核心价值

#### 1. 利用历史数据高效验证策略，提升研究效率数百倍

在验证交易策略时，历史回测是评估其有效性的关键环节，但传统人工方式难以处理海量数据与复杂计算。量化交易可在几分钟内完成一次全面回测，快速获得统计验证结果，极大提升了策略研发的迭代效率。

#### 2. 实时捕捉基于概率的获胜机会

量化交易借助计算机强大的数据处理能力，能够从海量市场信息中发掘人工难以察觉的规律与机会。面对全市场数千只股票的实时波动，量化系统可同时监控多重条件，避免机会错失。它能够综合考量选股、择时、资产配置与风险管理，构建并执行具有较大概率的投资组合，追求收益最大化。

#### 3. 实现科学、客观的投资决策

与传统主观投资不同，量化交易将投资理念、经验甚至市场直觉转化为严谨的数学模型。通过系统化的信号生成与执行机制，有效克服人性中的情绪偏差，使投资决策过程更具纪律性、可重复性与可优化性。

### 量化交易的工具挑战

工欲善其事，必先利其器。 对于个人投资者而言，独立搭建一套完整的量化交易体系，复杂繁琐，涉及数据、系统、策略等多层面的巨大投入。

#### 一、需要准确、全面的金融数据基础

量化交易依赖于高质量的历史与实时数据，包括行情、财务、宏观及基本面数据等。构建和维护这样一个数据仓库，不仅需要持续的数据采购、清洗、更新与运维成本，还需在数据存储、访问速度与系统稳定性方面进行深入的技术投入。

#### 二、需要易用、可靠的量化交易系统

一个成熟的量化平台需要支持多样的策略开发语言、具备高速的回测与模拟引擎、提供科学的策略评估体系，并为实盘交易提供全方位的保障。过往，研究者往往需要兼具复杂的金融数据处理能力和专业的编程技能，这对非专业背景的投资者形成了较高的技术门槛。

### TdxQuant的核心优势

#### 1. 全方位保障策略安全与自主

TdxQuant 采用本地运行模式，策略代码与数据均存储在用户本地设备，确保策略逻辑与交易数据的隐私与安全。用户完全掌控策略的开发、测试与执行全过程，无需担心云端平台的安全隐患或策略泄露风险。

#### 2. 大幅降低量化交易门槛

平台提供简洁直观的 Python API 接口，封装了复杂的底层数据处理与交易执行逻辑，使开发者可专注于策略本身的构思与实现。同时，平台内置丰富的技术指标与数据处理函数，加速策略研发进程。

#### 3. 助力构建专业量化成长路径

从入门级的策略回测到高级的实盘交易，TdxQuant 提供全流程的工具支持与文档资源。用户可通过循序渐进的学习与实践，逐步掌握量化交易的核心技能，构建属于自己的专业量化交易体系。

## 更新日志

### 📅 2026-03-27 更新说明 --仅上线内测版和金融终端(量化模拟)版
 * 新增函数：获取股票所属板块get_relation
 * 新增函数：调用客户端功能接口exec_to_tdx
 * 新增函数：撤单cancel_order_stock
 * 新增函数：账户资产查询query_stock_asset
 * 更新函数：交易类账户函数逻辑更新
 * 更新函数：调用通达信公式返回值字段名由"Data"改为"Value"
 * 更新函数：order_stock对于模拟账户自动下单
 * 更新函数：order_stock新增信用交易：担保品买入、担保品卖出，融资买入，融券卖出
 * 更新函数：get_stock_list_in_sector访问空的自定义板块会返回空集而不是报错
 * 问题修复：修复了get_market_data、refresh_kline等函数无法处理期权的问题
 * 其他更新：期货期权类型支持，新增相关宏定义（常量枚举）

### 📅 2026-03-20 更新说明 --仅上线内测版和金融终端(量化模拟)版
 * 新增函数：获取资金账户句柄stock_account
 * 新增函数：查询账户委托信息query_stock_orders
 * 新增函数：查询账户持仓信息query_stock_positions
 * 新增函数：交易执行函数order_stock
 * 更新函数：get_stock_list_in_sector新增block_type=2，可取对应期货代码
 * 更新函数：get_more_info新增字段QHMainYYMM
 * 更新函数：get_stock_list新增参数92: 国内期货主力合约
 * 更新函数：get_cb_info改名为get_kzz_info

### 📅 2026-03-06 更新说明
 * 新增函数：获取跟踪指数的ETF信息get_trackzs_etf_info
 * 更新函数：refresh_cache新增参数 'ZS' 表示沪深京指数
 * 更新函数：get_stock_list新增参数91 跟踪指数的ETF信息
 * 其他修正：未识别的市场后缀由默认的SZ改为OT
 * 其他修正：修复get_market_data某些情况下会报NoneType的bug

### 📅 2026-02-28 更新说明
 * 问题修复：修复了formula_process_mul_zb等入参retrun_count拼写错误问题
 * 更新函数：get_more_info，get_cb_info，get_market_snapshot加上了字段筛选功能
 * 更新函数：get_more_info等支持更多行情数据项，输出顺序进行归整
 * 其他修正：tqcenter几处细节修改

### 📅 2026-02-12 更新说明
 * 更新函数：send_user_block可以添加股票进自选股，自选股简称为ZXG
 * 其他更新：批量调用公式内部优化提速
 * 其他更新：新增港股指数（.HI）
 * 其他更新：解决多个客户端同时运行时的TQ冲突的问题

### 📅 2026-02-07 更新说明
 * 新增函数：批量调用选股公式formula_process_mul_xg
 * 新增函数：批量调用指标公式formula_process_mul_zb
 * 更新函数：get_stock_list、 get_sector_list、 get_stock_list_in_sector新增参数list_type，可以选择返回股票名称
 * 更新函数：tdx_formula返回做出修改，条件选股和专家选股只返回'1'和'0'
 * 更新函数：formula_zb新增参数xsflag，可以设置返回数据的小数位数
 * 更新函数：download_file新增下载：最近舆情、综合信息文件
 * 更新函数：get_stock_info新增部分数据字段输出

### 📅 2026-01-31 更新说明
 * 新增功能：支持调用通达信公式进行计算
 * 新增函数：格式化K线数据formula_format_data
 * 新增函数：向通达信公式系统设置数据formula_set_data
 * 新增函数：向通达信公式系统设置数据信息formula_set_data_info
 * 新增函数：获取公式中的设置数据formula_get_data
 * 新增函数：调用通达信技术指标公式formula_zb
 * 新增函数：调用通达信条件选股公式formula_xg
 * 新增函数：批量调用通达信公式formula_process
