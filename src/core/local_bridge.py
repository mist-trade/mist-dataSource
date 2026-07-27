"""Trusted local-peer checks for terminal bridges behind Docker loopback publishing."""

from __future__ import annotations

import ipaddress
import os
import socket
from functools import lru_cache
from pathlib import Path

_DOCKER_HOST_GATEWAY_ENV = "MIST_BRIDGE_TRUST_DOCKER_HOST_GATEWAY"


def is_trusted_local_bridge_peer(client_host: str | None) -> bool:
    """Accept native loopback, or the exact Docker default gateway when enabled."""
    if not client_host:
        return False
    try:
        if ipaddress.ip_address(client_host).is_loopback:
            return True
    except ValueError:
        return client_host == "localhost"

    if os.getenv(_DOCKER_HOST_GATEWAY_ENV, "").lower() not in {"1", "true", "yes"}:
        return False
    gateway = docker_default_gateway_ipv4()
    return gateway is not None and client_host == gateway


@lru_cache(maxsize=1)
def docker_default_gateway_ipv4() -> str | None:
    """Read the Linux container default route without shelling out."""
    try:
        route_text = Path("/proc/net/route").read_text(encoding="ascii")
    except OSError:
        return None
    return parse_linux_default_gateway(route_text)


def parse_linux_default_gateway(route_text: str) -> str | None:
    for line in route_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
            gateway_bytes = bytes.fromhex(fields[2])
        except ValueError:
            continue
        if not flags & 0x2 or len(gateway_bytes) != 4:
            continue
        return socket.inet_ntoa(gateway_bytes[::-1])
    return None
