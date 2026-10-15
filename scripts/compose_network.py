"""Generate an optional project-only IPAM override after inspecting actual routes/networks."""

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
from pathlib import Path


def command(args):
    return subprocess.check_output(args, text=True, timeout=20)


def routes():
    if os.name == "nt":
        shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
        if not shell:
            raise ValueError("PowerShell route inventory unavailable.")
        rows = json.loads(
            command(
                [
                    shell,
                    "-NoProfile",
                    "-Command",
                    (
                        "Get-NetRoute -AddressFamily IPv4 | "
                        "Select-Object DestinationPrefix | ConvertTo-Json -Compress"
                    ),
                ]
            )
        )
        rows = rows if isinstance(rows, list) else [rows]
        return [row["DestinationPrefix"] for row in rows]
    rows = json.loads(command(["ip", "-j", "-4", "route", "show", "table", "all"]))
    return [row["dst"] for row in rows if row.get("dst") != "default" and row.get("dst")]


def choose(existing, host_routes, requested=None):
    if not host_routes:
        raise ValueError("Host route inventory unavailable; refusing automatic subnet selection.")
    occupied = [
        ipaddress.ip_network(value, strict=False)
        for value in existing + host_routes
        if value != "0.0.0.0/0"
    ]
    candidates = (
        [ipaddress.ip_network(requested, strict=True)]
        if requested
        else ipaddress.ip_network("10.200.0.0/16").subnets(new_prefix=24)
    )
    private = [ipaddress.ip_network(v) for v in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    for candidate in candidates:
        if (
            candidate.version != 4
            or candidate.prefixlen != 24
            or not any(candidate.subnet_of(p) for p in private)
        ):
            raise ValueError("Only an RFC1918 IPv4 /24 project network is supported.")
        if not any(candidate.overlaps(network) for network in occupied if network.version == 4):
            return str(candidate)
    raise ValueError(
        "No non-overlapping candidate found. Review Docker/VPN/LAN routes; nothing changed."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subnet")
    args = parser.parse_args()
    try:
        ids = command(["docker", "network", "ls", "-q"]).split()
        networks = json.loads(command(["docker", "network", "inspect", *ids]))
        subnets = [
            config["Subnet"]
            for network in networks
            for config in network["IPAM"].get("Config") or []
            if config.get("Subnet")
        ]
        subnet = choose(subnets, routes(), args.subnet)
        payload = {"networks": {"default": {"ipam": {"config": [{"subnet": subnet}]}}}}
        # Exclusive creation: never replace a user's existing network override.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
        print(
            f"Validated {subnet} against {len(subnets)} Docker ranges and host routes. "
            f"Wrote {args.output}."
        )
    except (ValueError, OSError, subprocess.SubprocessError):
        parser.exit(
            1,
            "Network inspection/selection failed or output exists. "
            "No Docker configuration was changed.\n",
        )


if __name__ == "__main__":
    main()
