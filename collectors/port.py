# -*- coding: utf-8 -*-
"""端口监听检查：/proc/net/tcp 及可选的 netstat/ss（Python 2.7）"""
from __future__ import print_function
import os
import subprocess

def _parse_proc_net_tcp(path="/proc/net/tcp"):
    """解析 /proc/net/tcp，返回 set of (port_int)。"""
    listening = set()
    try:
        with open(path, "r") as f:
            lines = f.readlines()
    except IOError:
        return listening
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        # local_address 格式 0100007F:0016 -> host:port 十六进制
        local = parts[1]
        state = parts[3]
        if state != "0A":
            continue
        if ":" in local:
            try:
                port_hex = local.split(":")[1]
                listening.add(int(port_hex, 16))
            except ValueError:
                continue
    return listening

def get_listening_ports():
    """合并 IPv4/IPv6 监听端口，返回 set of port int。"""
    ports = set()
    ports.update(_parse_proc_net_tcp("/proc/net/tcp"))
    if os.path.isfile("/proc/net/tcp6"):
        ports.update(_parse_proc_net_tcp("/proc/net/tcp6"))
    return ports

def check_ports(expected_ports):
    """
    expected_ports: 期望监听的端口列表。
    返回 (ok, missing_list, listening_list)。
    """
    listening = get_listening_ports()
    expected_set = set(int(p) for p in expected_ports)
    missing = list(expected_set - listening)
    found = list(expected_set & listening)
    ok = len(missing) == 0
    return ok, sorted(missing), sorted(found)
