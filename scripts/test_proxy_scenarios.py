#!/usr/bin/env python3
"""End-to-end proxy scenario tests for the receipt HTTP client.

Scenarios covered:
  1. No proxy         – direct fetch to local target
  2. HTTP proxy       – fetch through a tiny local HTTP forward proxy
  3. HTTPS proxy      – verify proxy URL is passed to httpx (mocked TLS layer)
  4. SOCKS4 proxy     – verify proxy config reaches httpx / socksio
  5. SOCKS5 proxy     – verify proxy config reaches httpx / socksio
  6. SOCKS5h proxy    – verify DNS-handoff variant is accepted
  7. Invalid proxy    – verify graceful ValueError

Run:
    python scripts/test_proxy_scenarios.py
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from unittest.mock import MagicMock, patch

# Ensure project root on path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import httpx  # noqa: E402

from tx_verify.utils.http_client import (  # noqa: E402
    _build_proxies,
    _is_proxy_related_error,
    _mask_credentials,
    _validate_proxy_url,
    fetch_with_retry,
    get_async_client,
    get_sync_client,
)

# ---------------------------------------------------------------------------
# Local target server (simple HTTP echo)
# ---------------------------------------------------------------------------

TARGET_PORT = 0  # let OS pick
PROXY_PORT = 0   # let OS pick


class _TargetHandler(BaseHTTPRequestHandler):
    """Minimal echo server that always returns 200 + a JSON body."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok","via":"target"}')

    def log_message(self, format: str, *args: Any) -> None:
        # suppress default logging noise
        pass


class _ForwardProxyHandler(BaseHTTPRequestHandler):
    """Minimal HTTP CONNECT / forward proxy."""

    def do_GET(self):
        # Simple forward: fetch the requested URL and return it
        target = self.path
        try:
            # Use a *sync* httpx client without proxy to avoid recursion
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(target)
            self.send_response(resp.status_code)
            for key, val in resp.headers.items():
                if key.lower() not in {"transfer-encoding", "content-encoding"}:
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as exc:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Proxy Error: {exc}".encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _start_server(handler: type[BaseHTTPRequestHandler], port: int = 0) -> HTTPServer:
    srv = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestProxyScenarios(unittest.IsolatedAsyncioTestCase):
    """Run the seven required proxy scenarios."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.target_srv = _start_server(_TargetHandler)
        cls.target_port = cls.target_srv.server_address[1]
        cls.target_url = f"http://127.0.0.1:{cls.target_port}/"

        cls.proxy_srv = _start_server(_ForwardProxyHandler)
        cls.proxy_port = cls.proxy_srv.server_address[1]
        cls.proxy_url = f"http://127.0.0.1:{cls.proxy_port}"

        # give servers a moment to bind
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.target_srv.shutdown()
        cls.proxy_srv.shutdown()

    # ------------------------------------------------------------------
    # 1. No proxy
    # ------------------------------------------------------------------
    async def test_no_proxy(self) -> None:
        """Baseline: direct fetch without any proxy configuration."""
        response = await fetch_with_retry(
            self.target_url,
            max_retries=1,
            timeout=10.0,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        print("✅  No proxy  – PASSED")

    # ------------------------------------------------------------------
    # 2. HTTP proxy
    # ------------------------------------------------------------------
    async def test_http_proxy(self) -> None:
        """Fetch through a real local HTTP forward proxy."""
        response = await fetch_with_retry(
            self.target_url,
            proxies=self.proxy_url,
            max_retries=1,
            timeout=10.0,
        )
        self.assertEqual(response.status_code, 200)
        print("✅  HTTP proxy  – PASSED")

    # ------------------------------------------------------------------
    # 3. HTTPS proxy (config verification)
    # ------------------------------------------------------------------
    async def test_https_proxy(self) -> None:
        """HTTPS proxy URL is correctly passed to httpx."""
        https_proxy = f"https://127.0.0.1:{self.proxy_port}"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            # make the async context manager return our mock
            mock_instance.__aenter__ = unittest.mock.AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = unittest.mock.AsyncMock(return_value=False)
            mock_instance.request = unittest.mock.AsyncMock(
                return_value=MagicMock(status_code=200, json=lambda: {"via": "mock"})
            )
            mock_client_cls.return_value = mock_instance

            async with get_async_client(timeout=5.0, proxies=https_proxy) as _client:
                _ = await _client.request("GET", "https://example.com")

            # verify httpx.AsyncClient was constructed with the proxy URL
            _, kwargs = mock_client_cls.call_args
            self.assertEqual(kwargs["proxies"], https_proxy)
            print("✅  HTTPS proxy config  – PASSED")

    # ------------------------------------------------------------------
    # 4. SOCKS4 proxy
    # ------------------------------------------------------------------
    async def test_socks4_proxy(self) -> None:
        """SOCKS4 proxy URL is accepted by httpx client construction."""
        socks4_url = "socks4://127.0.0.1:1080"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = unittest.mock.AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = unittest.mock.AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            async with get_async_client(timeout=5.0, proxies=socks4_url) as _client:
                pass

            _, kwargs = mock_client_cls.call_args
            self.assertEqual(kwargs["proxies"], socks4_url)
            print("✅  SOCKS4 proxy config  – PASSED")

    # ------------------------------------------------------------------
    # 5. SOCKS5 proxy
    # ------------------------------------------------------------------
    async def test_socks5_proxy(self) -> None:
        """SOCKS5 proxy URL is accepted by httpx client construction."""
        socks5_url = "socks5://user:secret@127.0.0.1:1080"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = unittest.mock.AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = unittest.mock.AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            async with get_async_client(timeout=5.0, proxies=socks5_url) as _client:
                pass

            _, kwargs = mock_client_cls.call_args
            self.assertEqual(kwargs["proxies"], socks5_url)
            print("✅  SOCKS5 proxy config  – PASSED")

    # ------------------------------------------------------------------
    # 6. SOCKS5h proxy (DNS resolution handoff)
    # ------------------------------------------------------------------
    async def test_socks5h_proxy(self) -> None:
        """SOCKS5h proxy URL is accepted – verifies DNS-handoff variant."""
        socks5h_url = "socks5h://127.0.0.1:1080"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = unittest.mock.AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = unittest.mock.AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            async with get_async_client(timeout=5.0, proxies=socks5h_url) as _client:
                pass

            _, kwargs = mock_client_cls.call_args
            self.assertEqual(kwargs["proxies"], socks5h_url)
            print("✅  SOCKS5h proxy config  – PASSED")

    # ------------------------------------------------------------------
    # 7. Invalid proxy (graceful failure)
    # ------------------------------------------------------------------
    def test_invalid_proxy(self) -> None:
        """Malformed / unsupported proxy URLs raise ValueError cleanly."""
        with self.assertRaises(ValueError):
            _validate_proxy_url("ftp://bad-proxy:21")
        with self.assertRaises(ValueError):
            _validate_proxy_url("")
        with self.assertRaises(ValueError):
            _build_proxies("unsupported://host")
        print("✅  Invalid proxy graceful failure  – PASSED")

    # ------------------------------------------------------------------
    # Bonus: credential masking
    # ------------------------------------------------------------------
    def test_credential_masking(self) -> None:
        """Proxy URLs with credentials are masked in logs."""
        raw = "http://user:secret@proxy.example.com:8080"
        masked = _mask_credentials(raw)
        self.assertNotIn("secret", masked)
        self.assertIn("****", masked)
        self.assertIn("user", masked)
        print("✅  Credential masking  – PASSED")

    # ------------------------------------------------------------------
    # Bonus: explicit proxy-only (no env fallback)
    # ------------------------------------------------------------------
    def test_no_implicit_env_fallback(self) -> None:
        """_build_proxies returns None when called without arguments."""
        proxies = _build_proxies()
        self.assertIsNone(proxies)
        print("✅  No implicit env fallback  – PASSED")

    # ------------------------------------------------------------------
    # Bonus: proxy-related error detection
    # ------------------------------------------------------------------
    def test_proxy_error_detection(self) -> None:
        """Heuristic correctly flags proxy-related exceptions."""
        self.assertTrue(_is_proxy_related_error(httpx.ConnectError("Proxy connection failed")))
        self.assertTrue(_is_proxy_related_error(httpx.TimeoutException("SOCKS5 handshake timeout")))
        self.assertTrue(_is_proxy_related_error(httpx.NetworkError("ProxyError")))
        print("✅  Proxy error detection  – PASSED")

    # ------------------------------------------------------------------
    # Bonus: sync client path
    # ------------------------------------------------------------------
    def test_sync_client(self) -> None:
        """Sync client factory also passes proxies correctly."""
        with patch("httpx.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            with get_sync_client(timeout=5.0, proxies=self.proxy_url) as _client:
                pass

            _, kwargs = mock_client_cls.call_args
            self.assertEqual(kwargs["proxies"], self.proxy_url)
            print("✅  Sync client proxy config  – PASSED")


if __name__ == "__main__":
    # Use unittest runner but force verbose output
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestProxyScenarios)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        print("\n🎉  All proxy scenarios passed!")
        sys.exit(0)
    else:
        print("\n❌  Some proxy scenarios failed.")
        sys.exit(1)
