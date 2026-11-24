from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from client import SonarClient

_client: "SonarClient | None" = None


def get_client() -> "SonarClient":
    global _client
    if _client is None:
        from credential_manager import build_client

        _client = build_client()
    return _client


def set_client(client: "SonarClient | None") -> None:
    global _client
    _client = client
