"""Pooled, keep-alive async HTTP transport shared by every outbound Runtime
leg (NVS / CLE / HEKB) — EXP-Ubuntu011.

EXP-Ubuntu010B measured ~155ms WAN RTT (Ubuntu -> GCP) with p99 connection
close (fresh TCP+TLS handshake per call) of ~330ms, roughly double the
p99 keep-alive figure (~161ms). This module is the fix: one
`httpx.AsyncClient` per base_url, cached for the process lifetime, so a
handshake happens once and every subsequent request reuses the pooled
connection. Retry/backoff and timeout policy live here too, sourced from
`NetworkProfile` — never in the NVS/CLE/HEKB services themselves.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from runtime.core.network_profile import NetworkProfile, get_network_profile

logger = logging.getLogger(__name__)

_clients: dict[str, httpx.AsyncClient] = {}
_clients_lock = asyncio.Lock()


def _build_client(base_url: str, profile: NetworkProfile) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(
            connect=profile.connect_timeout_ms / 1000,
            read=profile.request_timeout_ms / 1000,
            write=profile.request_timeout_ms / 1000,
            pool=profile.request_timeout_ms / 1000,
        ),
        limits=httpx.Limits(
            max_keepalive_connections=profile.max_keepalive_connections,
            max_connections=profile.max_connections,
            keepalive_expiry=30.0 if profile.keep_alive else 0.0,
        ),
    )


async def get_pooled_client(
    base_url: str, profile: NetworkProfile | None = None
) -> httpx.AsyncClient:
    """Return the cached AsyncClient for `base_url`, creating it on first use.

    One client per base_url for the whole process — this is the "persistent
    connection / connection pool / reuse" requirement: no caller opens a new
    TCP connection per request.
    """
    profile = profile or get_network_profile()
    client = _clients.get(base_url)
    if client is not None and not client.is_closed:
        return client

    async with _clients_lock:
        client = _clients.get(base_url)
        if client is not None and not client.is_closed:
            return client
        client = _build_client(base_url, profile)
        _clients[base_url] = client
        return client


async def close_all_pooled_clients() -> None:
    """Close every pooled client — call once, on app shutdown."""
    clients = list(_clients.values())
    _clients.clear()
    for client in clients:
        await client.aclose()


class RetryExhaustedError(RuntimeError):
    """Raised when a pooled request fails after every retry attempt."""


async def request_with_retry(
    method: str,
    base_url: str,
    path: str,
    *,
    json: dict | None = None,
    profile: NetworkProfile | None = None,
) -> httpx.Response:
    """Issue one HTTP request through the pooled client for `base_url`,
    retrying transient failures (connect/read errors, timeouts, 5xx) with
    exponential backoff: `retry_backoff_ms * 2**attempt`.

    Retries `profile.retry_count` times beyond the first attempt. 4xx
    responses are not retried (they are not transient — retrying a bad
    request just repeats the same error).
    """
    profile = profile or get_network_profile()
    client = await get_pooled_client(base_url, profile)
    backoff_s = profile.retry_backoff_ms / 1000
    last_exc: Exception | None = None

    for attempt in range(profile.retry_count + 1):
        try:
            response = await client.request(method, path, json=json)
            if response.status_code >= 500:
                response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt >= profile.retry_count:
                break
            wait_s = backoff_s * (2**attempt)
            logger.warning(
                "%s %s%s failed (attempt %d/%d): %s — retrying in %.2fs",
                method, base_url, path, attempt + 1, profile.retry_count + 1, exc, wait_s,
            )
            await asyncio.sleep(wait_s)

    raise RetryExhaustedError(
        f"{method} {base_url}{path} failed after {profile.retry_count + 1} attempts"
    ) from last_exc
