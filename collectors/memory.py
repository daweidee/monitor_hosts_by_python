# -*- coding: utf-8 -*-
"""内存使用率采集（读 /proc/meminfo，Python 2.7）"""
from __future__ import print_function

def _parse_meminfo():
    data = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                name, rest = line.split(":", 1)
                val = rest.strip().split()[0]
                data[name] = long(val)
    except (IOError, ValueError):
        pass
    return data

def get_memory_usage():
    """
    返回 (used_percent, {"total_kb": ..., "used_kb": ..., "free_kb": ..., "available_kb": ...})
    使用 MemTotal - MemAvailable 近似 used（兼容旧内核无 MemAvailable 时用 MemFree）。
    """
    data = _parse_meminfo()
    total = data.get("MemTotal", 0)
    available = data.get("MemAvailable")
    if available is not None:
        used = total - available
    else:
        used = total - data.get("MemFree", 0)
    if total <= 0:
        return None, {}
    used_pct = round(100.0 * used / total, 2)
    detail = {
        "total_kb": total,
        "used_kb": used,
        "free_kb": data.get("MemFree", 0),
        "available_kb": available if available is not None else data.get("MemFree", 0),
    }
    return used_pct, detail
