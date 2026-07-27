# QMT runtime probe

`mist_qmt_runtime_probe.py` 仅用于确认大 QMT 内置 Python 运行时、`get_full_tick`
字段和文件输出能力。它不是生产 bridge，不应覆盖到生产策略脚本位置。

如需指定输出文件，设置 `MIST_QMT_RUNTIME_PROBE_OUTPUT_PATH`。生产 realtime 使用
`qmt/builtin_bridge/mist_qmt_realtime_bridge.py`。

默认输出仍落在 `F:\quant\MistAPI\datasource\logs\qmt`，该目录只是 cutover 后保留的
宿主 evidence/log 根，不包含 datasource Python runtime，也不表示 gateway 仍由
WinSW 部署。
