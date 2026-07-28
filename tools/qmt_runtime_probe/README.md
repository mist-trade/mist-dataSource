# QMT runtime probe

本目录包含两种用途不同的 QMT operator probe，均不是生产 bridge，禁止覆盖
`正式采集.py` 或
`qmt/builtin_bridge/mist_qmt_realtime_bridge.py`。

## 晚间订阅 API 只读取证

使用 `mist_qmt_subscription_introspection_probe.py`。它只执行：

- `dir(ContextInfo)`；
- 对四个 required method 和所有 `subscribe*all*|subscribe*whole*` 候选执行
  `getattr`、读取 `__doc__`、`help` 和 `inspect.signature`；
- 写一份已做路径/token 基础脱敏的 JSON。

它不会调用任何 `subscribe*`、`unsubscribe*`、`get_market_data_ex`，也不会发
HTTP、打开监听端口、创建线程或子进程。非交易时段可以执行。

操作步骤：

1. 在 QMT 中新建一个临时 Python 策略/项目，不要修改或停止当前
   `正式采集.py`。
2. 将 `mist_qmt_subscription_introspection_probe.py` 全文复制进去。
3. 如果界面能够查到版本或权限，可先填写脚本顶部五个
   `OPERATOR_*` 常量；拿不到就保持 `unknown`，不要猜。
4. 启动临时项目一次，看到
   `MIST_QMT_SUBSCRIPTION_INTROSPECTION_END` 后停止临时项目。
5. 将
   `F:\quant\qmt\mist-qmt-subscription-introspection.json`
   发给 Codex。若文件未写出，则复制 BEGIN/END 之间的完整日志。
6. 删除或停用临时项目即可；不需要重载 datasource、backend 或生产 bridge。

输出中的 `signature.status=unknown` 是允许结果，不代表方法不存在。
`operatorMetadata` 保持 `unknown` 也会原样记录为平台/操作员无法确认，不会猜测
QMT alias 或权限。

## 完整运行环境复验

`mist_qmt_runtime_probe.py` 用于更广泛的运行环境、文件、网络和进程模型复验，
会尝试只读历史查询、localhost HTTP、socket、线程和子进程，不适合仅补订阅
introspection 证据时运行。

如需指定其输出文件，设置 `MIST_QMT_RUNTIME_PROBE_OUTPUT_PATH`。默认输出位于
`F:\quant\MistAPI\datasource\logs\qmt`；该目录只是 cutover 后保留的宿主
evidence/log 根，不包含 datasource Python runtime，也不表示 gateway 仍由
WinSW 部署。
