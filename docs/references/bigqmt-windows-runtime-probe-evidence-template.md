# BigQMT Windows runtime probe 复验模板

该模板用于 QMT 版本、机器或内置 Python 环境变化后的重新取证，不代表当前仍未
验证。2026-07-11 native history probe 与 2026-07-22 realtime HIL 已通过，正式证据
保存在 `mist` OpenSpec archive。复验时附加
`tools/qmt_runtime_probe/mist_qmt_runtime_probe.py` 原始输出，并明确区分“本次重新采集”和历史
结论。

## Run Metadata

- Date/time:
- Windows host:
- QMT version/build:
- QMT account profile used:
- QMT model: simulation/trading/backtest:
- Strategy/script mode:
- Run mechanism tested: run_time/handlebar/subscribe/http-polling:
- Trading session state while testing: in-session/outside-session/weekend:
- Editor separate-process option: off/on (must be off for valid bridge evidence)
- Datasource commit:
- Operator:

## Probe A: Library And Network Capability

| Check | Result | Evidence |
| --- | --- | --- |
| Python version | pending | |
| Encoding and JSON output | pending | |
| `json` import | pending | |
| `urllib` / `http.client` import | pending | |
| `socket` import | pending | |
| `sqlite3` import | pending | |
| `requests` import attempt | pending | |
| Outbound `127.0.0.1` HTTP | pending | |
| Local port listen attempt | pending | |
| Long request blocks strategy loop | pending | |

## Probe B: Process And Execution Model

| Check | Result | Evidence |
| --- | --- | --- |
| `os.getpid()` identity | pending | |
| Main thread identity | pending | |
| `threading` attempt | pending | |
| `multiprocessing` attempt | pending | |
| `subprocess` attempt | pending | |
| Two-strategy shared process check | pending | |
| Two-strategy global-state check | pending | |
| Editor separate-process option remains off | pending | |
| `run_time` callback fires on configured interval | pending | |
| `run_time` fires outside trading hours/weekend | pending | |
| Bridge does not require `handlebar` or `subscribe` events | pending | |
| `run_time` blocking impact | pending | |
| Long native API call impact | pending | |
| Exception recovery | pending | |
| Repeated startup behavior | pending | |

## Probe C: Native Historical Bars

| Check | Result | Evidence |
| --- | --- | --- |
| Built-in `get_market_data_ex` command completed | pending | |
| Native `:9002/v1/bars/query` field shape | pending | |
| QMT `marketData` returned with `source=native_bridge` | pending | |
| Datasource has no DAT reader or data-directory setting | pending | |

## Native API Shape Samples

Record sanitized samples for the methods planned for normalized provider work:

- `get_market_data_ex`:
- `get_full_tick`:
- `get_stock_list_in_sector`:
- Calendar method:
- Security info method:
- Finance/report method:
- Formula method:

## Conclusion

- Bridge can use third-party packages: yes/no
- Bridge can use HTTP polling internally: yes/no
- Bridge can listen on localhost: yes/no
- Bridge can use threads/processes/subprocesses: yes/no
- Bridge ran as one built-in script with editor separate-process option off: yes/no
- HTTP polling command loop can execute serial commands: yes/no
- Preferred bridge transport after runtime probe: HTTP polling/blocked
- Bridge can rely on `run_time` outside trading hours if a pump is needed: yes/no
- Bridge must remain single-owner serial polling: yes/no
- Native bridge historical-bars product path approved: yes/no
- Live QMT provider enablement approved: yes/no
- Follow-up implementation notes:
