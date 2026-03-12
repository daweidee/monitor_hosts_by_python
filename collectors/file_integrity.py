# -*- coding: utf-8 -*-
"""
系统文件完整性监控：基线比对与异常修改检测（Python 2.7）
资源优化：先 mtime+size 比对，仅在变更时做哈希；支持文件数/大小上限，降低 IO/CPU。
"""
from __future__ import print_function
import os
import json
import hashlib
import fnmatch

def _file_hash(path, block_size=65536, max_bytes=0):
    """
    max_bytes: 若 >0 只读前 max_bytes 做哈希（大文件限流）；0 表示全量。
    """
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            read = 0
            while True:
                to_read = block_size
                if max_bytes > 0 and read + block_size > max_bytes:
                    to_read = max_bytes - read
                if to_read <= 0:
                    break
                block = f.read(to_read)
                if not block:
                    break
                h.update(block)
                read += len(block)
                if max_bytes > 0 and read >= max_bytes:
                    break
        return h.hexdigest()
    except (IOError, OSError):
        return None

def _walk_files(dirs, exclude_patterns=None, max_files=0, max_depth=0):
    """
    max_files: 0=不限制；>0 时最多 yield 该数量后停止。
    max_depth: 0=不限制；>0 时相对 watch_dir 的目录深度超过则跳过该子树。
    """
    exclude_patterns = exclude_patterns or []
    seen = set()
    count = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        d = os.path.normpath(d)
        base_depth = len(d.rstrip(os.sep).split(os.sep))
        for root, dirs_names, filenames in os.walk(d):
            if max_depth > 0:
                cur_depth = len(os.path.normpath(root).split(os.sep)) - base_depth
                if cur_depth > max_depth:
                    dirs_names[:] = []
                    continue
            for name in filenames:
                if max_files > 0 and count >= max_files:
                    return
                full = os.path.join(root, name)
                try:
                    if os.path.islink(full):
                        continue
                    if not os.path.isfile(full):
                        continue
                except OSError:
                    continue
                skip = False
                for pat in exclude_patterns:
                    if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(full, pat):
                        skip = True
                        break
                if not skip and full not in seen:
                    seen.add(full)
                    count += 1
                    yield full

def build_baseline(watch_dirs, exclude_patterns=None, baseline_path=None,
                  max_file_size_to_hash=0, max_files=0, max_depth=0):
    """
    建立文件基线：路径 -> {mtime, size, sha256?}。
    若文件大于 max_file_size_to_hash 则不计算哈希（省 IO），仅记 mtime/size。
    """
    baseline = {}
    for path in _walk_files(watch_dirs, exclude_patterns, max_files, max_depth):
        try:
            st = os.stat(path)
            do_hash = max_file_size_to_hash <= 0 or st.st_size <= max_file_size_to_hash
            h = _file_hash(path) if do_hash else None
            baseline[path] = {
                "mtime": st.st_mtime,
                "size": st.st_size,
                "sha256": h,
            }
        except (OSError, IOError):
            continue
    if baseline_path:
        base_dir = os.path.dirname(baseline_path)
        if base_dir and not os.path.isdir(base_dir):
            try:
                os.makedirs(base_dir, 0o755)
            except OSError:
                pass
        if os.path.isdir(base_dir) or not base_dir:
            with open(baseline_path, "w") as f:
                json.dump(baseline, f, indent=2)
    return baseline

def load_baseline(baseline_path):
    if not baseline_path or not os.path.isfile(baseline_path):
        return {}
    try:
        with open(baseline_path, "r") as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}

def check_integrity(watch_dirs, baseline_path, exclude_patterns=None,
                   use_mtime_only=False, hash_only_if_changed=True,
                   max_file_size_to_hash=0, max_files=0, max_depth=0):
    """
    与基线比对。资源优化：
    - use_mtime_only: True 时只比较 mtime+size，不做任何哈希。
    - hash_only_if_changed: True 时仅当 mtime 或 size 与基线不同才计算哈希以确认修改。
    - max_file_size_to_hash: 超过该字节数的文件不哈希（仅用 mtime+size 判断）。
    """
    baseline = load_baseline(baseline_path)
    current = {}
    alerts = []
    for path in _walk_files(watch_dirs, exclude_patterns, max_files, max_depth):
        try:
            st = os.stat(path)
            mtime, size = st.st_mtime, st.st_size
            old = baseline.get(path)
            if old is None:
                alerts.append({"type": "new", "path": path})
                current[path] = {"mtime": mtime, "size": size, "sha256": None}
                continue
            if mtime == old.get("mtime") and size == old.get("size"):
                current[path] = {"mtime": mtime, "size": size, "sha256": old.get("sha256")}
                continue
            if use_mtime_only:
                alerts.append({"type": "modified", "path": path})
                current[path] = {"mtime": mtime, "size": size, "sha256": None}
                continue
            if not hash_only_if_changed:
                do_hash = max_file_size_to_hash <= 0 or size <= max_file_size_to_hash
                max_bytes = max_file_size_to_hash if (max_file_size_to_hash > 0 and size > max_file_size_to_hash) else 0
                h = _file_hash(path, max_bytes=max_bytes) if do_hash else None
                if h != old.get("sha256"):
                    alerts.append({"type": "modified", "path": path})
                current[path] = {"mtime": mtime, "size": size, "sha256": h}
                continue
            do_hash = max_file_size_to_hash <= 0 or size <= max_file_size_to_hash
            max_bytes = max_file_size_to_hash if (max_file_size_to_hash > 0 and size > max_file_size_to_hash) else 0
            h = _file_hash(path, max_bytes=max_bytes) if do_hash else None
            old_hash = old.get("sha256")
            if old_hash is not None and h is not None and h == old_hash:
                pass
            else:
                alerts.append({"type": "modified", "path": path})
            current[path] = {"mtime": mtime, "size": size, "sha256": h}
        except (OSError, IOError):
            continue
    for path in baseline:
        if path not in current:
            alerts.append({"type": "deleted", "path": path})
    return alerts, current
