# -*- coding: utf-8 -*-
"""磁盘使用率采集（os.statvfs，Python 2.7）"""
from __future__ import print_function
import os

def get_disk_usage(mounts=None):
    """
    mounts: 挂载点列表，如 ["/", "/data"]。None 时仅 "/"。
    返回 [(mount, used_percent, {"total_bytes", "free_bytes", "used_bytes"}), ...]
    """
    if mounts is None:
        mounts = ["/"]
    result = []
    for m in mounts:
        m = m.strip()
        if not m:
            continue
        try:
            st = os.statvfs(m)
        except OSError:
            result.append((m, None, {}))
            continue
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        if total <= 0:
            result.append((m, None, {"total_bytes": total, "free_bytes": free, "used_bytes": used}))
            continue
        used_pct = round(100.0 * used / total, 2)
        result.append((m, used_pct, {
            "total_bytes": total,
            "free_bytes": free,
            "used_bytes": used,
        }))
    return result
