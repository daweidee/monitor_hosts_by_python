# -*- coding: utf-8 -*-
"""
监控配置 Web 后端（Python 2.7 + Flask 1.1）
提供配置的读取/保存与一次执行监控的 API，并托管前端页面。
"""
from __future__ import print_function
import os
import sys
import json
import logging

# 将 monitor_hosts 根目录加入 path，以便 import config / runner
_monitor_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _monitor_root not in sys.path:
    sys.path.insert(0, _monitor_root)

from flask import Flask, request, jsonify, render_template, send_from_directory

from config import load_config, save_config, get_config_path, DEFAULT_CONFIG
from db import save_run_result, get_last_run

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["JSON_AS_ASCII"] = False

# 静默 runner 的日志输出，避免刷屏
_logger = logging.getLogger("monitor_hosts")
_logger.setLevel(logging.WARNING)
_logger.addHandler(logging.NullHandler())


def _run_monitor(build_baseline=False):
    """执行一次监控，返回 (alerts, results)。支持 local/remote 模式。若监控已关闭则跳过采集。"""
    import runner
    config = load_config()
    if not config.get("monitoring_enabled", True):
        return [], {"monitoring_disabled": True, "message": "监控已关闭，未执行采集；仅可登录后台查看或修改配置。"}
    th = config.get("target_hosts", {})
    mode = (th.get("mode") or "local").strip().lower()
    hosts = th.get("hosts") or []
    if build_baseline:
        return runner.run_once(config, _logger, build_baseline=True)
    if mode == "remote" and hosts:
        return runner.run_once_remote(config, _logger)
    return runner.run_once(config, _logger, build_baseline=False)


@app.route("/")
def index():
    resp = app.make_response(render_template("index.html"))
    # 禁止缓存，修改项目后刷新页面即可看到最新内容
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """返回当前监控配置（与 monitor_config.json 合并默认后的结果）。"""
    try:
        cfg = load_config()
        return jsonify({"ok": True, "config": cfg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/config", methods=["POST"])
def api_save_config():
    """保存配置。请求体为 JSON，需包含完整 config 对象。"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"ok": False, "error": "Invalid JSON"}), 400
        # 若前端只传了部分 key，与默认配置合并后再保存
        merged = _deep_merge(dict(DEFAULT_CONFIG), data)
        save_config(merged)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@app.route("/api/run", methods=["POST"])
def api_run():
    """执行一次监控。若监控已关闭则返回提示不执行采集。可选 body: {"build_baseline": true} 表示仅建立文件基线。"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        build_baseline = data.get("build_baseline", False)
        alerts, results = _run_monitor(build_baseline=build_baseline)
        msg = None
        if results.get("monitoring_disabled"):
            msg = results.get("message", "监控已关闭")
        else:
            if not build_baseline:
                save_run_result(alerts, results)
            if alerts:
                try:
                    from notifiers import send_alert_notifications
                    send_alert_notifications(alerts, load_config(), _logger)
                except Exception as e:
                    _logger.exception("告警通知发送失败: %s", e)
        return jsonify({"ok": True, "alerts": alerts, "results": results, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/last_run", methods=["GET"])
def api_last_run():
    """返回最近一次监控运行记录，供首页监控概览展示。"""
    try:
        run_at, alerts, results = get_last_run()
        return jsonify({"ok": True, "run_at": run_at, "alerts": alerts, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/run_host", methods=["POST"])
def api_run_host():
    """对单台机器执行一次监控（用于「增加服务器」页的操作）。body: {"host_index": 0}。"""
    try:
        import runner
        data = request.get_json(force=True, silent=True) or {}
        idx = data.get("host_index", 0)
        config = load_config()
        th = config.get("target_hosts", {})
        hosts = th.get("hosts") or []
        if idx < 0 or idx >= len(hosts):
            return jsonify({"ok": False, "error": "无效的 host_index"}), 400
        host_spec = dict(hosts[idx])
        host_spec.setdefault("remote_project_path", th.get("remote_project_path"))
        host_spec.setdefault("remote_command", th.get("remote_command"))
        timeout = int(th.get("ssh_timeout") or 30)
        host_config = _deep_merge(config, host_spec.get("config_override", {}))
        import remote as remote_collector
        out = remote_collector.run_remote_collect(host_spec, timeout=timeout, config_for_host=host_config)
        host_id = out.get("host", "unknown")
        alerts = []
        if "error" in out:
            alerts.append({"metric": "remote", "host": host_id, "message": out["error"]})
        else:
            for a in out.get("alerts", []):
                alerts.append({"metric": a.get("metric", ""), "host": host_id, "message": a.get("message", "")})
        results = {"hosts": {host_id: out}}
        return jsonify({"ok": True, "alerts": alerts, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/alert_test", methods=["POST"])
def api_alert_test():
    """发送告警测试消息。body: {"channel": "telegram"|"lark"|"all", "telegram": {"bot_token","chat_id"}, "lark": {"webhook_url"}}，可选传表单值以测试未保存的配置。"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        channel = (data.get("channel") or "all").strip().lower()
        if channel not in ("telegram", "lark", "all"):
            channel = "all"
        form_overrides = {}
        if data.get("telegram"):
            form_overrides["telegram"] = {
                "bot_token": (data["telegram"].get("bot_token") or "").strip(),
                "chat_id": (data["telegram"].get("chat_id") or "").strip(),
            }
        if data.get("lark"):
            form_overrides["lark"] = {
                "webhook_url": (data["lark"].get("webhook_url") or "").strip(),
            }
        config = load_config()
        from notifiers import send_test_message
        result = send_test_message(channel, config, form_overrides=form_overrides if form_overrides else None, logger=_logger)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "telegram": None, "lark": None, "error": str(e)}), 500


@app.route("/api/config/path")
def api_config_path():
    """返回当前配置文件路径（只读，便于前端展示）。"""
    return jsonify({"path": get_config_path()})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Monitor Hosts Web UI (Python 2.7)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=5000, help="Bind port")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)
