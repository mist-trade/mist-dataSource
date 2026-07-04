# BigQMT Windows Spike Evidence Template

Use this template before enabling the live QMT provider. Attach the raw output
from `qmt/builtin_bridge/mist_qmt_spike.py` and keep the final conclusion
explicit.

## Run Metadata

- Date/time:
- Windows host:
- QMT version/build:
- QMT account profile used:
- QMT model: simulation/trading/backtest:
- Strategy/script mode:
- Run mechanism tested: run_time/handlebar/subscribe/websocket:
- Trading session state while testing: in-session/outside-session/weekend:
- Editor separate-process option: off/on (must be off for valid bridge evidence)
- Datasource commit:
- Operator:

## Spike A: Library And Network Capability

| Check | Result | Evidence |
| --- | --- | --- |
| Python version | pending | |
| Encoding and JSON output | pending | |
| `json` import | pending | |
| `urllib` / `http.client` import | pending | |
| `socket` import | pending | |
| `sqlite3` import | pending | |
| `requests` import attempt | pending | |
| `websocket` import attempt | pending | |
| Outbound `127.0.0.1` HTTP | pending | |
| WebSocket package duplex probe | pending | |
| Standard-library raw WebSocket duplex probe | pending | |
| Local port listen attempt | pending | |
| Long request blocks strategy loop | pending | |

## Spike B: Process And Execution Model

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
- Bridge can use WebSocket internally: yes/no
- Bridge can listen on localhost: yes/no
- Bridge can use threads/processes/subprocesses: yes/no
- Bridge ran as one built-in script with editor separate-process option off: yes/no
- Preferred bridge transport after spike: HTTP polling/WebSocket duplex/blocked
- Bridge can rely on `run_time` outside trading hours if a pump is needed: yes/no
- Bridge must remain single-owner serial polling: yes/no
- Live QMT provider enablement approved: yes/no
- Follow-up implementation notes:
