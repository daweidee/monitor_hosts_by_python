# -*- coding: utf-8 -*-
"""CPU 使用率采集（读 /proc/stat，Python 2.7）"""
from __future__ import print_function
import time

def _read_proc_stat():
    with open("/proc/stat", "r") as f:
        for line in f:
            if line.startswith("cpu "):
                parts = line.split()
                return [long(x) for x in parts[1:5]]
    return None

def get_cpu_usage(interval_sec=2):
    """
    两次采样 /proc/stat 计算 CPU 使用率百分比。
    返回 (usage_percent, {"user": ..., "system": ..., "idle": ...}) 或 (None, {})
    """
    v1 = _read_proc_stat()
    if not v1:
        return None, {}
    time.sleep(max(0.1, interval_sec))
    v2 = _read_proc_stat()
    if not v2 or len(v1) != 4 or len(v2) != 4:
        return None, {}
    user, nice, system, idle = [v2[i] - v1[i] for i in range(4)]
    total = user + nice + system + idle
    if total == 0:
        return 0.0, {}
    usage = 100.0 * (user + nice + system) / total
    detail = {
        "user": 100.0 * user / total,
        "system": 100.0 * system / total,
        "idle": 100.0 * idle / total,
    }
    return round(usage, 2), detail
