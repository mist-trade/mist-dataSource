import inspect

from src.datasource.qmt.bridge import QmtCommandGateway
from src.datasource.qmt.realtime.runtime import QmtRealtimeCollector


def test_qmt_runtime_store_exposes_schema_v2_latest_state_without_polling() -> None:
    gateway = QmtCommandGateway()
    runtime = QmtRealtimeCollector(gateway=gateway, publisher=lambda _value: None)

    assert runtime.ready_contract() == {
        "mode": "builtin",
        "schemaVersion": 2,
        "source": "qmt",
        "quality": "latest-state",
    }
    assert "collect_once" not in dir(runtime)
    assert "gateway.enqueue" not in inspect.getsource(QmtRealtimeCollector)
    assert gateway.health()["pendingCount"] == 0


def test_qmt_runtime_store_tracks_leader_connection_and_latest_observation() -> None:
    gateway = QmtCommandGateway()
    runtime = QmtRealtimeCollector(gateway=gateway, publisher=lambda _value: None)

    assert runtime.claim_leader("backend-a") is True
    assert runtime.claim_leader("backend-b") is False
    runtime.record_snapshot("2026-07-26T10:00:00+08:00")

    health = runtime.health()
    assert health["schemaVersion"] == 2
    assert health["quality"] == "latest-state"
    assert health["leaderClientId"] == "backend-a"
    assert health["connectionCount"] == 2
    assert health["lastQuoteAt"] == "2026-07-26T10:00:00+08:00"

    runtime.disconnect("backend-a")
    assert runtime.health()["leaderClientId"] is None
