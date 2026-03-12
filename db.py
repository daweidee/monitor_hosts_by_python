# -*- coding: utf-8 -*-
"""
监控配置与运行数据持久化到 monitor_hosts 目录下 data/ 内的 SQLite（Python 2.7）。
若数据库文件不存在，会在首次加载时自动创建 data 目录及表结构。
"""
from __future__ import print_function
import os
import json
import sqlite3

# monitor_hosts 项目目录（db.py 所在目录）
_MONITOR_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_MONITOR_ROOT, "data")
DB_FILENAME = "monitor_hosts.db"
_CONFIG_KEY = "current"

# 表结构
_SCHEMA_CONFIG = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT
);
"""

_SCHEMA_RUNS = """
CREATE TABLE IF NOT EXISTS monitor_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    alerts TEXT,
    results TEXT
);
"""


def get_db_path():
    """返回 SQLite 数据库文件路径（monitor_hosts/data/monitor_hosts.db）。"""
    return os.path.join(DATA_DIR, DB_FILENAME)


def _ensure_data_dir():
    if not os.path.isdir(DATA_DIR):
        try:
            os.makedirs(DATA_DIR, 0o755)
        except OSError:
            pass


def init_db():
    """
    若数据库文件不存在则创建 data 目录、数据库文件及所需表结构。
    可重复调用，表已存在则跳过。
    """
    _ensure_data_dir()
    path = get_db_path()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA_CONFIG + _SCHEMA_RUNS)
        conn.commit()
    finally:
        conn.close()


def get_config():
    """
    从 SQLite 读取当前配置（key='current'）。
    返回 JSON 解析后的字典，若不存在或出错返回 None。
    """
    init_db()
    path = get_db_path()
    if not os.path.isfile(path):
        return None
    try:
        conn = sqlite3.connect(path)
        try:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", (_CONFIG_KEY,)
            ).fetchone()
            if row:
                return json.loads(row[0])
            return None
        finally:
            conn.close()
    except (sqlite3.Error, ValueError, IOError):
        return None


def set_config(config_dict):
    """
    将完整配置字典写入 SQLite（key='current'），并更新 updated_at。
    """
    import time
    init_db()
    path = get_db_path()
    value = json.dumps(config_dict)
    updated_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, ?)",
            (_CONFIG_KEY, value, updated_at),
        )
        conn.commit()
    finally:
        conn.close()


def save_run_result(alerts, results):
    """
    将一次监控运行的告警与结果写入 monitor_runs 表，供首页展示最近一次监控数据。
    """
    import time
    init_db()
    path = get_db_path()
    if not os.path.isfile(path):
        return
    run_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    alerts_json = json.dumps(alerts) if alerts else ""
    results_json = json.dumps(results) if results else "{}"
    try:
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "INSERT INTO monitor_runs (run_at, alerts, results) VALUES (?, ?, ?)",
                (run_at, alerts_json, results_json),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def get_last_run():
    """
    返回最近一次监控运行记录。
    返回 (run_at, alerts, results) 或 (None, [], {})。
    """
    init_db()
    path = get_db_path()
    if not os.path.isfile(path):
        return None, [], {}
    try:
        conn = sqlite3.connect(path)
        try:
            row = conn.execute(
                "SELECT run_at, alerts, results FROM monitor_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None, [], {}
            run_at, alerts_json, results_json = row
            alerts = json.loads(alerts_json) if alerts_json else []
            results = json.loads(results_json) if results_json else {}
            return run_at, alerts, results
        finally:
            conn.close()
    except (sqlite3.Error, ValueError, IOError):
        return None, [], {}
