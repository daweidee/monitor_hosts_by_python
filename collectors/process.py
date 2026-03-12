# -*- coding: utf-8 -*-
"""
进程存在性检查：按进程名判断是否在运行（Python 2.7）
资源优化：use_light_check 时仅用 pgrep/ps -C 查询期望名，不遍历 /proc 全量列表。
"""
from __future__ import print_function
import os
import subprocess

def _check_by_light(expected_names):
    """
    轻量检查：只查期望的进程名是否存在，不构建全量进程集。
    返回 (found_list, missing_list)。
    """
    missing = []
    found = []
    for name in expected_names:
        name = name.strip()
        if not name:
            continue
        try:
            out = subprocess.check_output(["pgrep", "-x", name], stderr=subprocess.PIPE)
            if out.strip():
                found.append(name)
            else:
                missing.append(name)
        except (subprocess.CalledProcessError, OSError):
            try:
                out = subprocess.check_output(["ps", "-C", name, "-o", "pid="], stderr=subprocess.PIPE)
                if out.strip():
                    found.append(name)
                else:
                    missing.append(name)
            except (subprocess.CalledProcessError, OSError):
                missing.append(name)
    return found, missing


def get_running_process_names():
    """返回当前运行中的进程名集合（去重，小写）。较重：ps + /proc 遍历。"""
    names = set()
    try:
        out = subprocess.check_output(["ps", "-eo", "comm="], stderr=subprocess.PIPE)
        for line in out.splitlines():
            name = line.strip().split()[0] if line.strip() else ""
            if name:
                names.add(name)
        proc = "/proc"
        if os.path.isdir(proc):
            for pid in os.listdir(proc):
                if not pid.isdigit():
                    continue
                try:
                    with open(os.path.join(proc, pid, "cmdline"), "r") as f:
                        raw = f.read()
                    if raw:
                        cmd = raw.replace("\x00", " ").strip().split()
                        if cmd:
                            base = os.path.basename(cmd[0])
                            if base:
                                names.add(base)
                except (IOError, OSError):
                    continue
    except (subprocess.CalledProcessError, OSError):
        pass
    return names


def check_processes(expected_names, must_running=True, use_light_check=True):
    """
    expected_names: 期望存在的进程名列表。
    must_running: True 表示这些进程中至少有一个在运行即视为正常。
    use_light_check: True 时仅用 pgrep/ps -C 查期望名，不遍历 /proc，降低 IO/CPU。
    """
    if use_light_check and expected_names:
        found, missing = _check_by_light(expected_names)
        ok = len(found) > 0 if must_running else (len(missing) == 0)
        return ok, missing, found
    running = get_running_process_names()
    running_lower = set(s.lower() for s in running)
    missing = []
    found = []
    for name in expected_names:
        name = name.strip()
        if not name:
            continue
        n_lower = name.lower()
        if n_lower in running_lower:
            found.append(name)
            continue
        matched = False
        for r in running_lower:
            if n_lower in r or r in n_lower:
                matched = True
                found.append(name)
                break
        if not matched:
            missing.append(name)
    if must_running and expected_names:
        ok = len(found) > 0
    else:
        ok = len(missing) == 0
    return ok, missing, found
