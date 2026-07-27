from __future__ import annotations

from src.core.local_bridge import is_trusted_local_bridge_peer, parse_linux_default_gateway


def test_native_loopback_is_always_trusted(monkeypatch) -> None:
    monkeypatch.delenv("MIST_BRIDGE_TRUST_DOCKER_HOST_GATEWAY", raising=False)
    assert is_trusted_local_bridge_peer("127.0.0.1")
    assert is_trusted_local_bridge_peer("::1")
    assert not is_trusted_local_bridge_peer("172.18.0.1")


def test_docker_gateway_requires_explicit_mode_and_exact_default_route(monkeypatch) -> None:
    route = (
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        "eth0 00000000 010012AC 0003 0 0 0 00000000 0 0 0\n"
    )
    assert parse_linux_default_gateway(route) == "172.18.0.1"

    monkeypatch.setenv("MIST_BRIDGE_TRUST_DOCKER_HOST_GATEWAY", "true")
    monkeypatch.setattr("src.core.local_bridge.docker_default_gateway_ipv4", lambda: "172.18.0.1")
    assert is_trusted_local_bridge_peer("172.18.0.1")
    assert not is_trusted_local_bridge_peer("172.18.0.2")


def test_invalid_or_missing_peer_is_rejected() -> None:
    assert not is_trusted_local_bridge_peer(None)
    assert not is_trusted_local_bridge_peer("not-an-ip")
