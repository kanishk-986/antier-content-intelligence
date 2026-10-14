"""Retry a request that failed for a transport reason.

A run on an unstable connection recorded 82 of 98 sources as `error` with the same
SSL verification failure, and every one of them answered 200 to the same client
minutes later. Office wifi, a VPN coming up and a captive portal all produce the
same shape: the connection fails for a few seconds and then works.

Without a retry, a few seconds of instability is written into `source_fetch_log` as
a fact about 82 publishers, the brief is built from almost nothing, and the health
report sends someone chasing listing rules for sources that were never broken.

**Only transport failures are retried.** An HTTP 403 is the publisher's decision and
means the same thing however many times it is asked; retrying it would be the
blind retry SOURCE_POLICY forbids. A connection that never opened said nothing at
all.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

# Three attempts over ~4 seconds. Long enough to cross a brief network change,
# short enough that 105 sources do not turn a 30-minute run into an hour.
DEFAULT_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)

# Transport-level: the request never reached the server, or the connection died
# mid-flight. httpx.HTTPStatusError is deliberately absent -- a status is an answer.
TRANSIENT = (
    httpx.ConnectError,       # DNS, TLS verification, refused connection
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


def with_retry(call: Callable[[], Any], attempts: int = DEFAULT_ATTEMPTS,
               sleep: Callable[[float], None] = time.sleep) -> Any:
    """Run `call`, retrying only transport failures. The last error is re-raised."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return call()
        except TRANSIENT as exc:
            last = exc
            if attempt < attempts - 1:
                sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
    raise last if last else RuntimeError("retry called with no attempts")


def get(client: httpx.Client, url: str, attempts: int = DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep, **kwargs: Any) -> httpx.Response:
    return with_retry(lambda: client.get(url, **kwargs), attempts, sleep)
