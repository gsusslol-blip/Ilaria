"""WAN tunnel frees a domain left online by a dead Ilaria process."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.tunnel_manager import _open_tunnel, _release_stuck_endpoint, _release_tunnel_sessions


class _Boom(Exception):
    pass


class TunnelRebindTests(unittest.TestCase):
    def test_stops_leftover_tunnel_sessions(self) -> None:
        client = MagicMock()
        client.get.return_value.raise_for_status = MagicMock()
        client.get.return_value.json.return_value = {
            "tunnel_sessions": [{"id": "ts_old"}]
        }
        client.post.return_value.status_code = 204
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        with patch("httpx.Client", return_value=client):
            stopped = _release_tunnel_sessions("token")
        self.assertEqual(stopped, 1)
        client.post.assert_called_once()
    def test_releases_the_endpoint_named_in_the_error(self) -> None:
        client = MagicMock()
        client.get.return_value.status_code = 200
        client.get.return_value.json.return_value = {
            "endpoints": [{"id": "ep_1", "url": "https://stuck.ngrok-free.dev"}]
        }
        client.get.return_value.raise_for_status = MagicMock()
        client.delete.return_value.status_code = 204
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        with patch("httpx.Client", return_value=client):
            ok = _release_stuck_endpoint(
                "token",
                "The endpoint 'https://stuck.ngrok-free.dev' is already online. ERR_NGROK_334",
            )
        self.assertTrue(ok)
        client.delete.assert_called_once()

    def test_session_limit_without_api_key_does_not_retry(self) -> None:
        ngrok = MagicMock()
        ngrok.connect.side_effect = _Boom(
            "limited to 3 simultaneous ngrok agent sessions ERR_NGROK_108"
        )
        with patch.dict("os.environ", {"NGROK_API_KEY": ""}, clear=False):
            with self.assertRaises(_Boom):
                _open_tunnel(ngrok, 8787, "token")
        self.assertEqual(ngrok.connect.call_count, 1)

    def test_retries_connect_after_334(self) -> None:
        tunnel = MagicMock()
        ngrok = MagicMock()
        ngrok.connect.side_effect = [
            _Boom("endpoint 'https://stuck.ngrok-free.dev' already online ERR_NGROK_334"),
            tunnel,
        ]
        with patch("jarvis.tunnel_manager._release_stuck_endpoint", return_value=True), patch(
            "jarvis.tunnel_manager._release_tunnel_sessions", return_value=1
        ), patch("jarvis.tunnel_manager.time.sleep"):
            got = _open_tunnel(ngrok, 8787, "token")
        self.assertIs(got, tunnel)
        self.assertEqual(ngrok.connect.call_count, 2)


if __name__ == "__main__":
    unittest.main()
