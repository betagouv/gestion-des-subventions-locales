from unittest.mock import MagicMock, patch

import redis
from django.test import override_settings

from gsl_ds_proxy.locks import acquire_token_lock, release_token_lock


@override_settings(DS_PROXY_TOKEN_LOCK_TIMEOUT=90)
@patch("gsl_ds_proxy.locks.redis.Redis.from_url")
def test_acquire_returns_lock_when_free(mock_from_url):
    lock = MagicMock()
    lock.acquire.return_value = True
    client = MagicMock()
    client.lock.return_value = lock
    mock_from_url.return_value = client

    result = acquire_token_lock(7)

    assert result is lock
    client.lock.assert_called_once_with("ds-proxy:token:7", timeout=90)
    lock.acquire.assert_called_once_with(blocking=False)


@patch("gsl_ds_proxy.locks.redis.Redis.from_url")
def test_acquire_returns_none_when_held(mock_from_url):
    lock = MagicMock()
    lock.acquire.return_value = False
    client = MagicMock()
    client.lock.return_value = lock
    mock_from_url.return_value = client

    assert acquire_token_lock(7) is None


@patch("gsl_ds_proxy.locks.redis.Redis.from_url")
def test_distinct_tokens_use_distinct_keys(mock_from_url):
    client = MagicMock()
    client.lock.return_value.acquire.return_value = True
    mock_from_url.return_value = client

    acquire_token_lock(1)
    acquire_token_lock(2)

    keys = [call.args[0] for call in client.lock.call_args_list]
    assert keys == ["ds-proxy:token:1", "ds-proxy:token:2"]


def test_release_calls_lock_release():
    lock = MagicMock()
    release_token_lock(lock, 7)
    lock.release.assert_called_once_with()


def test_release_swallows_lock_error_when_ttl_expired():
    lock = MagicMock()
    lock.release.side_effect = redis.exceptions.LockError("not owned")

    # Must not raise: the TTL expired and the lock is no longer ours.
    release_token_lock(lock, 7)

    lock.release.assert_called_once_with()
