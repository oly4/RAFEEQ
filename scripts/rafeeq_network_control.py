#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys


def run(command: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def split_nmcli_line(line: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.rstrip("\n"):
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == ":":
            values.append("".join(current))
            current = []
            continue
        current.append(char)
    values.append("".join(current))
    return values


def wifi_devices() -> list[dict[str, str]]:
    result = run(["/usr/bin/nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    devices: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = split_nmcli_line(line)
        if len(parts) >= 4 and parts[1] == "wifi":
            devices.append(
                {
                    "interface": parts[0],
                    "state": parts[2],
                    "connection": parts[3] or None,
                }
            )
    return devices


def current_ssid(interface: str | None) -> str | None:
    iwgetid = shutil.which("iwgetid") or "/usr/sbin/iwgetid"
    if interface:
        result = run([iwgetid, interface, "--raw"], timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    result = run([iwgetid, "--raw"], timeout=5)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    result = run_nmcli_wifi_list(["ACTIVE,SSID"], interface=interface, rescan="no", timeout=8)
    for line in result.stdout.splitlines():
        parts = split_nmcli_line(line)
        if len(parts) >= 2 and parts[0] == "yes" and parts[1]:
            return parts[1]
    return None


def ip_addresses() -> list[str]:
    result = run(["/usr/bin/hostname", "-I"], timeout=5)
    if result.returncode != 0:
        return []
    return [value for value in result.stdout.split() if value]


def run_nmcli_wifi_list(
    fields: list[str],
    *,
    interface: str | None = None,
    rescan: str = "auto",
    timeout: int = 20,
) -> subprocess.CompletedProcess[str]:
    command = [
        "/usr/bin/nmcli",
        "-t",
        "-f",
        ",".join(fields),
        "device",
        "wifi",
        "list",
    ]
    if interface:
        command.extend(["ifname", interface])
    command.extend(["--rescan", rescan])
    return run(command, timeout=timeout)


def scan_networks() -> list[dict[str, object]]:
    interface = primary_wifi_interface()
    result = run_nmcli_wifi_list(
        ["ACTIVE", "SSID", "SIGNAL", "SECURITY"],
        interface=interface,
        rescan="yes",
        timeout=15,
    )
    if result.returncode != 0:
        result = run_nmcli_wifi_list(
            ["ACTIVE", "SSID", "SIGNAL", "SECURITY"],
            interface=interface,
            rescan="no",
            timeout=10,
        )
    networks_by_ssid: dict[str, dict[str, object]] = {}
    for line in result.stdout.splitlines():
        parts = split_nmcli_line(line)
        if len(parts) < 4:
            continue
        active, ssid, signal, security = parts[:4]
        if not ssid:
            continue
        parsed_signal: int | None
        try:
            parsed_signal = int(signal)
        except ValueError:
            parsed_signal = None
        existing = networks_by_ssid.get(ssid)
        if existing is None or (parsed_signal or 0) > int(existing.get("signal") or 0):
            networks_by_ssid[ssid] = {
                "ssid": ssid,
                "signal": parsed_signal,
                "security": security or None,
                "active": active == "yes",
            }
    ssid = current_ssid(interface)
    if ssid and ssid not in networks_by_ssid:
        networks_by_ssid[ssid] = {
            "ssid": ssid,
            "signal": None,
            "security": None,
            "active": True,
        }
    elif ssid:
        networks_by_ssid[ssid]["active"] = True
    return sorted(
        networks_by_ssid.values(),
        key=lambda item: int(item.get("signal") or 0),
        reverse=True,
    )


def primary_wifi_interface() -> str:
    devices = wifi_devices()
    primary = next((item for item in devices if item.get("state") == "connected"), None)
    if primary and primary.get("interface"):
        return str(primary["interface"])
    if devices and devices[0].get("interface"):
        return str(devices[0]["interface"])
    return "wlan0"


def security_for_ssid(ssid: str) -> str | None:
    for network in scan_networks():
        if network.get("ssid") == ssid:
            return str(network.get("security") or "")
    return None


def status(include_scan: bool = False) -> dict[str, object]:
    devices = wifi_devices()
    primary = next((item for item in devices if item["state"] == "connected"), devices[0] if devices else {})
    interface = primary.get("interface")
    ssid = current_ssid(interface)
    state = primary.get("state")
    connected = state == "connected" or bool(ssid)
    return {
        "connected": connected,
        "ssid": ssid,
        "connection": primary.get("connection"),
        "interface": interface,
        "state": state,
        "ip_addresses": ip_addresses(),
        "wifi_networks": scan_networks() if include_scan else [],
    }


def connect() -> dict[str, object]:
    payload = json.load(sys.stdin)
    ssid = str(payload.get("ssid") or "").strip()
    password = str(payload.get("password") or "")
    if not ssid:
        raise SystemExit("SSID is required")
    interface = primary_wifi_interface()
    security = security_for_ssid(ssid)
    if security is None and not password:
        raise SystemExit(f"Wi-Fi password is required for network '{ssid}' because security could not be verified.")
    if security and not password:
        raise SystemExit(f"Wi-Fi password is required for secured network '{ssid}'.")
    profile_name = f"rafeeq-wifi-{hashlib.sha256(ssid.encode()).hexdigest()[:10]}"
    run(["/usr/bin/nmcli", "connection", "delete", profile_name], timeout=10)
    add = run(
        [
            "/usr/bin/nmcli",
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            interface,
            "con-name",
            profile_name,
            "ssid",
            ssid,
        ],
        timeout=20,
    )
    if add.returncode != 0:
        raise SystemExit((add.stderr or add.stdout or "Failed to create Wi-Fi profile").strip())
    if password:
        detected_security = security or ""
        key_mgmt = "sae" if "WPA3" in detected_security and "WPA2" not in detected_security else "wpa-psk"
        modify = run(
            [
                "/usr/bin/nmcli",
                "connection",
                "modify",
                profile_name,
                "wifi-sec.key-mgmt",
                key_mgmt,
                "wifi-sec.psk",
                password,
            ],
            timeout=20,
        )
        if modify.returncode != 0:
            run(["/usr/bin/nmcli", "connection", "delete", profile_name], timeout=10)
            raise SystemExit(
                (modify.stderr or modify.stdout or "Failed to configure Wi-Fi security").strip()
            )
    run(["/usr/bin/nmcli", "connection", "modify", profile_name, "connection.autoconnect", "yes"])
    result = run(["/usr/bin/nmcli", "connection", "up", profile_name], timeout=45)
    if result.returncode != 0:
        run(["/usr/bin/nmcli", "connection", "delete", profile_name], timeout=10)
        raise SystemExit((result.stderr or result.stdout or "Failed to connect").strip())
    data = status(include_scan=False)
    data["message"] = result.stdout.strip() or "Wi-Fi connected"
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="RAFEEQ Raspberry Pi network helper")
    parser.add_argument("action", choices=["status", "scan", "connect"])
    args = parser.parse_args()

    if args.action == "status":
        data = status(include_scan=False)
    elif args.action == "scan":
        data = status(include_scan=True)
    else:
        data = connect()
    print(json.dumps(data))


if __name__ == "__main__":
    main()
