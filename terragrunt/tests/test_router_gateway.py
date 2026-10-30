"""Cleanup tolerates a deleted router, but not unrelated errors."""

import importlib.util
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock


path = Path(__file__).resolve().parents[1] / "bootstrap/module/scripts/router_gateway.py"
spec = importlib.util.spec_from_file_location("router_gateway", path)
router_gateway = importlib.util.module_from_spec(spec)
with mock.patch.dict(os.environ, {"ROUTER_ID": "router-123", "NETWORK_ID": "network-123"}):
    spec.loader.exec_module(router_gateway)


class RouterGatewayTests(unittest.TestCase):
    def test_detach_missing_router_succeeds(self):
        missing = subprocess.CalledProcessError(1, ["openstack"], stderr="No Router found for router-123")
        with mock.patch.object(router_gateway, "gateway_network", side_effect=missing) as query:
            router_gateway.main("detach")
        query.assert_called_once_with()

    def test_other_failure_still_fails(self):
        unauthorized = subprocess.CalledProcessError(1, ["openstack"], stderr="Unauthorized")
        with mock.patch.object(router_gateway, "gateway_network", side_effect=unauthorized), \
             mock.patch.object(router_gateway.time, "sleep"):
            with self.assertRaises(subprocess.CalledProcessError):
                router_gateway.main("detach")

    def test_attach_missing_router_still_fails(self):
        missing = subprocess.CalledProcessError(1, ["openstack"], stderr="No Router found for router-123")
        with mock.patch.object(router_gateway, "gateway_network", side_effect=missing), \
             mock.patch.object(router_gateway.time, "sleep"):
            with self.assertRaises(subprocess.CalledProcessError):
                router_gateway.main("attach")


if __name__ == "__main__":
    unittest.main()
