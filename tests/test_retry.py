"""Retrying a transport failure, and never retrying an answer."""

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion import retry


class _Calls:
    """Fails with `exc` the first `fail_times` times, then succeeds."""

    def __init__(self, exc, fail_times):
        self.exc, self.fail_times, self.n = exc, fail_times, 0

    def __call__(self):
        self.n += 1
        if self.n <= self.fail_times:
            raise self.exc
        return "ok"


def _no_sleep(_seconds):
    return None


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] verify failed"),
    httpx.ConnectError("[Errno 8] nodename nor servname provided"),
    httpx.ReadError("Connection reset by peer"),
    httpx.ConnectTimeout("timed out"),
    httpx.ReadTimeout("timed out"),
    httpx.RemoteProtocolError("server disconnected"),
])
def test_a_transport_failure_is_retried(exc):
    """A run on an unstable connection recorded 82 of 98 sources as `error` with
    one SSL failure, and every one answered 200 to the same client minutes later."""
    call = _Calls(exc, fail_times=1)
    assert retry.with_retry(call, sleep=_no_sleep) == "ok"
    assert call.n == 2


def test_it_gives_up_after_the_last_attempt_and_reraises():
    call = _Calls(httpx.ConnectError("down"), fail_times=99)
    with pytest.raises(httpx.ConnectError):
        retry.with_retry(call, attempts=3, sleep=_no_sleep)
    assert call.n == 3, "it must not retry forever"


def test_a_success_is_not_retried():
    call = _Calls(httpx.ConnectError("x"), fail_times=0)
    assert retry.with_retry(call, sleep=_no_sleep) == "ok"
    assert call.n == 1


def test_an_http_status_is_an_answer_and_is_never_retried():
    """A 403 is the publisher's decision and means the same thing however many
    times it is asked. Retrying it is the blind retry SOURCE_POLICY forbids."""
    def answered():
        raise httpx.HTTPStatusError("403", request=None, response=None)
    call_count = {"n": 0}

    def wrapped():
        call_count["n"] += 1
        answered()

    with pytest.raises(httpx.HTTPStatusError):
        retry.with_retry(wrapped, sleep=_no_sleep)
    assert call_count["n"] == 1


def test_a_403_response_is_returned_not_retried():
    """The common case: the server answers, and the answer is a refusal."""
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        return httpx.Response(403)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    resp = retry.get(client, "https://x.test", sleep=_no_sleep)
    assert resp.status_code == 403 and seen["n"] == 1


def test_backoff_grows_between_attempts():
    waits = []
    call = _Calls(httpx.ConnectError("down"), fail_times=99)
    with pytest.raises(httpx.ConnectError):
        retry.with_retry(call, attempts=3, sleep=waits.append)
    assert waits == [1.0, 3.0], "a flat retry crowds a recovering network"
