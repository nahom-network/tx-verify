"""Centralized HTTP client factory with explicit proxy support.

Provides sync and async httpx clients that accept proxy configuration
**directly** via the ``proxies`` argument. No environment variables are read.

SOCKS4, SOCKS5, and SOCKS5h are supported via ``httpx[socks]``.
"""

from __future__ import annotations

import asyncio
import re
import ssl
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from tx_verify.utils.logger import logger

# ---------------------------------------------------------------------------
# Proxy helpers
# ---------------------------------------------------------------------------

_VALID_PROXY_SCHEMES: set[str] = {"http", "https", "socks4", "socks5", "socks5h"}


def _mask_credentials(url: str) -> str:
    """Return a proxy URL with the password (if any) masked."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            # Build netloc with user but no password
            user_info = f"{parsed.username}:****"
            netloc = f"{user_info}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            # Reassemble
            return f"{parsed.scheme}://{netloc}{parsed.path or ''}"
    except Exception:
        pass
    return url


def _validate_proxy_url(url: str) -> str:
    """Validate and normalize a single proxy URL.

    Raises:
        ValueError: if the scheme is unsupported or the URL is malformed.
    """
    url = url.strip()
    if not url:
        raise ValueError("Proxy URL is empty")

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _VALID_PROXY_SCHEMES:
        raise ValueError(
            f"Unsupported proxy scheme '{scheme}'. "
            f"Supported: {', '.join(sorted(_VALID_PROXY_SCHEMES))}"
        )
    if not parsed.hostname:
        raise ValueError(f"Proxy URL missing host: {url}")

    return url


def _build_proxies(
    proxies: str | dict[str, str] | None = None,
) -> str | dict[str, str] | None:
    """Validate and normalize an explicit proxy configuration.

    Args:
        proxies: A single proxy URL (``str``) or a per-scheme mapping
            (``dict``). ``None`` means "no proxy".

    Returns:
        ``None`` when no proxy is configured, otherwise a ``str`` (single URL)
        or ``dict`` mapping scheme → URL for httpx's ``proxies=`` kwarg.

    Raises:
        TypeError: if ``proxies`` is neither ``str`` nor ``dict``.
        ValueError: if a proxy URL has an unsupported scheme or is malformed.
    """
    if proxies is None:
        return None

    if isinstance(proxies, str):
        return _validate_proxy_url(proxies)
    if isinstance(proxies, dict):
        validated: dict[str, str] = {}
        for key, val in proxies.items():
            validated[key] = _validate_proxy_url(val)
        return validated
    raise TypeError(f"proxies must be str, dict, or None, got {type(proxies)}")


def _log_proxy_config(proxies: str | dict[str, str] | None) -> None:
    """Log proxy configuration with credentials masked."""
    if proxies is None:
        logger.debug("HTTP client: no proxy configured")
        return

    if isinstance(proxies, str):
        logger.info("HTTP client: using proxy %s", _mask_credentials(proxies))
    elif isinstance(proxies, dict):
        for scheme, url in proxies.items():
            logger.info("HTTP client: %s proxy = %s", scheme, _mask_credentials(url))


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------

_PROXY_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ProxyError", re.IGNORECASE),
    re.compile(r"ConnectError", re.IGNORECASE),
    re.compile(r"Timeout", re.IGNORECASE),
    re.compile(r"SOCKS", re.IGNORECASE),
]


def _is_proxy_related_error(exc: Exception) -> bool:
    """Heuristic to decide whether an exception is proxy-related."""
    exc_str = f"{type(exc).__name__}: {exc}"
    return any(pattern.search(exc_str) for pattern in _PROXY_ERROR_PATTERNS)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def get_async_client(
    *,
    timeout: float = 30.0,
    verify: ssl.SSLContext | str | bool = True,
    proxies: Any = None,
    headers: dict[str, str] | None = None,
    **httpx_kwargs: Any,
) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with optional explicit proxy support.

    Proxy configuration is **not** read from environment variables.
    Pass ``proxies`` explicitly when calling this function.

    Args:
        timeout: Request timeout in seconds (default 30).
        verify: SSL verification mode / context (default True).
        proxies: Proxy URL (``str``) or per-scheme mapping (``dict``).
        headers: Default headers for every request.
        **httpx_kwargs: Extra arguments forwarded to ``httpx.AsyncClient``.

    Returns:
        Configured ``httpx.AsyncClient`` instance.
    """
    resolved = _build_proxies(proxies)
    _log_proxy_config(resolved)

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        verify=verify,
        proxies=cast(Any, resolved),
        headers=headers,
        **httpx_kwargs,
    )
    return client


def get_sync_client(
    *,
    timeout: float = 30.0,
    verify: ssl.SSLContext | str | bool = True,
    proxies: Any = None,
    headers: dict[str, str] | None = None,
    **httpx_kwargs: Any,
) -> httpx.Client:
    """Create an ``httpx.Client`` with optional explicit proxy support.

    Proxy configuration is **not** read from environment variables.
    Pass ``proxies`` explicitly when calling this function.

    Args:
        timeout: Request timeout in seconds (default 30).
        verify: SSL verification mode / context (default True).
        proxies: Proxy URL (``str``) or per-scheme mapping (``dict``).
        headers: Default headers for every request.
        **httpx_kwargs: Extra arguments forwarded to ``httpx.Client``.

    Returns:
        Configured ``httpx.Client`` instance.
    """
    resolved = _build_proxies(proxies)
    _log_proxy_config(resolved)

    client = httpx.Client(
        timeout=httpx.Timeout(timeout),
        verify=verify,
        proxies=cast(Any, resolved),
        headers=headers,
        **httpx_kwargs,
    )
    return client


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


async def fetch_with_retry(
    url: str,
    *,
    method: str = "GET",
    max_retries: int = 3,
    retry_delay: float = 2.0,
    timeout: float = 30.0,
    verify: ssl.SSLContext | str | bool = True,
    proxies: Any = None,
    headers: dict[str, str] | None = None,
    raise_for_status: bool = True,
    **request_kwargs: Any,
) -> httpx.Response:
    """Fetch a URL with an async httpx client, retrying on transient failures.

    Proxy configuration is **not** read from environment variables.
    Pass ``proxies`` explicitly when calling this function.

    Proxy-related errors are explicitly logged with credentials masked.
    """
    resolved_proxies = _build_proxies(proxies)
    _log_proxy_config(resolved_proxies)

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            async with get_async_client(
                timeout=timeout,
                verify=verify,
                proxies=resolved_proxies,
                headers=headers,
            ) as client:
                response = await client.request(method, url, **request_kwargs)
                if raise_for_status:
                    response.raise_for_status()
                return response

        except httpx.HTTPStatusError:
            # Non-transient HTTP error — don't waste retries on 4xx/5xx
            # unless it's a proxy auth failure (407) or gateway issue (502/503/504)
            raise
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exception = exc
            is_proxy_err = _is_proxy_related_error(exc)
            safe_url = _mask_credentials(str(url))
            safe_proxy = _mask_credentials(str(resolved_proxies)) if resolved_proxies else "none"

            if is_proxy_err:
                logger.warning(
                    "Proxy-related failure on attempt %d/%d for %s (proxy=%s): %s",
                    attempt,
                    max_retries,
                    safe_url,
                    safe_proxy,
                    exc,
                )
            else:
                logger.warning(
                    "Network failure on attempt %d/%d for %s: %s",
                    attempt,
                    max_retries,
                    safe_url,
                    exc,
                )

            if attempt < max_retries:
                wait = retry_delay * attempt  # linear back-off
                logger.info("Waiting %.1fs before retry...", wait)
                await asyncio.sleep(wait)

    # All retries exhausted
    raise last_exception  # type: ignore[misc]


def fetch_sync_with_retry(
    url: str,
    *,
    method: str = "GET",
    max_retries: int = 3,
    retry_delay: float = 2.0,
    timeout: float = 30.0,
    verify: ssl.SSLContext | str | bool = True,
    proxies: Any = None,
    headers: dict[str, str] | None = None,
    raise_for_status: bool = True,
    **request_kwargs: Any,
) -> httpx.Response:
    """Synchronous equivalent of ``fetch_with_retry``.

    Proxy configuration is **not** read from environment variables.
    Pass ``proxies`` explicitly when calling this function.
    """
    resolved_proxies = _build_proxies(proxies)
    _log_proxy_config(resolved_proxies)

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            with get_sync_client(
                timeout=timeout,
                verify=verify,
                proxies=resolved_proxies,
                headers=headers,
            ) as client:
                response = client.request(method, url, **request_kwargs)
                if raise_for_status:
                    response.raise_for_status()
                return response

        except httpx.HTTPStatusError:
            raise
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exception = exc
            is_proxy_err = _is_proxy_related_error(exc)
            safe_url = _mask_credentials(str(url))
            safe_proxy = _mask_credentials(str(resolved_proxies)) if resolved_proxies else "none"

            if is_proxy_err:
                logger.warning(
                    "Proxy-related failure on attempt %d/%d for %s (proxy=%s): %s",
                    attempt,
                    max_retries,
                    safe_url,
                    safe_proxy,
                    exc,
                )
            else:
                logger.warning(
                    "Network failure on attempt %d/%d for %s: %s",
                    attempt,
                    max_retries,
                    safe_url,
                    exc,
                )

            if attempt < max_retries:
                wait = retry_delay * attempt
                logger.info("Waiting %.1fs before retry...", wait)
                import time

                time.sleep(wait)

    raise last_exception  # type: ignore[misc]
