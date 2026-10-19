#!/usr/bin/env python3
"""Attach/detach a Neutron router gateway, retrying transient API failures."""

import ast
import json
import os
import subprocess
import sys
import time


ROUTER_ID = os.environ["ROUTER_ID"]
NETWORK_ID = os.environ["NETWORK_ID"]


def openstack(*args):
    return subprocess.run(
        ["openstack", *args], check=True, capture_output=True, text=True
    ).stdout


def gateway_network():
    result = openstack("router", "show", ROUTER_ID, "-f", "json", "-c", "external_gateway_info")
    gateway = json.loads(result)["external_gateway_info"]
    if isinstance(gateway, str):
        try:
            gateway = json.loads(gateway)
        except json.JSONDecodeError:
            gateway = ast.literal_eval(gateway)
    return gateway.get("network_id") if gateway else None


def main(action):
    desired = NETWORK_ID if action == "attach" else None

    for attempt in range(1, 7):
        try:
            current = gateway_network()
            if current == desired:
                print(f"Router {ROUTER_ID}: gateway {action} verified")
                return
            if current is not None and current != NETWORK_ID:
                raise RuntimeError(f"Router {ROUTER_ID} uses unexpected gateway {current}")

            if action == "attach":
                openstack("router", "set", "--external-gateway", NETWORK_ID, ROUTER_ID)
            else:
                openstack("router", "unset", "--external-gateway", ROUTER_ID)
        except subprocess.CalledProcessError as exc:
            print(
                f"Gateway {action} attempt {attempt}: {exc.stderr.strip() or exc}",
                file=sys.stderr,
            )

        if attempt < 6:
            time.sleep(5 * attempt)

    if gateway_network() != desired:
        raise RuntimeError(
            f"Router {ROUTER_ID}: gateway {action} not confirmed after 6 attempts"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("attach", "detach"):
        sys.exit("Usage: router_gateway.py attach|detach")
    main(sys.argv[1])
