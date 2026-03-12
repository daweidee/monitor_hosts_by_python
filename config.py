# -*- coding: utf-8 -*-
"""
监控配置：优先从项目 data 目录下 SQLite 读写；
若 SQLite 不存在则自动创建库与表，未写入过配置时使用下方默认配置。
"""
from __future__ import print_function
import os
import json
from db import init_db, get_config as _db_get_config, set_config as _db_set_config, get_db_path as _db_path

# 默认配置（Python 2.7 兼容）
# 设计原则：降低被监控端 CPU/内存/IO 损耗，重任务可关闭或限流
DEFAULT_CONFIG = {
    "monitoring_enabled": False,
    "cpu": {
        "enabled": True,
        "warn_percent": 85,
        "interval_sec": 2
    },
    "memory": {
        "enabled": True,
        "warn_percent": 85
    },
    "disk": {
        "enabled": True,
        "warn_percent": 85,
        "mounts": ["/", "/data", "/home"]
    },
    "file_integrity": {
        "enabled": True,
        "watch_dirs": ["/etc", "/usr/bin", "/usr/sbin"],
        "baseline_path": "/var/lib/monitor_hosts/baseline.json",
        "exclude_patterns": ["*.log", "*.cache", ".git"],
        "use_mtime_only": False,
        "hash_only_if_changed": True,
        "max_file_size_to_hash": 1048576,
        "max_files": 0,
        "max_depth": 0
    },
    "process": {
        "enabled": True,
        "expected_names": ["sshd", "nginx", "redis-server"],
        "must_running": True,
        "use_light_check": True
    },
    "port": {
        "enabled": True,
        "expected_ports": [22, 80, 443, 6379]
    },
    "target_hosts": {
        "mode": "local",
        "hosts": [],
        "remote_project_path": "/opt/monitor_hosts",
        "remote_command": "python monitor_hosts/main.py --json",
        "ssh_timeout": 30
    },
    "log": {
        "path": "/var/log/monitor_hosts.log",
        "level": "INFO"
    },
    "alerts_notify": {
        "enabled": False,
        "telegram": {
            "enabled": False,
            "bot_token": "",
            "chat_id": ""
        },
        "lark": {
            "enabled": False,
            "webhook_url": ""
        }
    }
}

def load_config(path=None):
    """从 SQLite 加载配置；若尚无记录则返回默认配置。path 保留兼容，忽略时使用 DB。"""
    if path is not None:
        # 显式指定路径时仍支持从 JSON 文件读（兼容旧用法）
        if os.path.isfile(path):
            with open(path, "r") as f:
                cfg = json.load(f)
            return _deep_merge(dict(DEFAULT_CONFIG), cfg)
        return dict(DEFAULT_CONFIG)
    init_db()
    cfg = _db_get_config()
    if cfg is None:
        return dict(DEFAULT_CONFIG)
    return _deep_merge(dict(DEFAULT_CONFIG), cfg)

def _deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_config_path(path=None):
    """返回当前配置存储路径（SQLite 文件路径，供 Web 展示）。"""
    if path is not None:
        return path
    return _db_path()


def save_config(config_dict, path=None):
    """将配置写入 SQLite；若传入 path 则同时写入该 JSON 文件（兼容）。"""
    _db_set_config(config_dict)
    if path is not None:
        with open(path, "w") as f:
            json.dump(config_dict, f, indent=2)
