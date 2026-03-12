# -*- coding: utf-8 -*-
"""
监控运行器：按配置执行各采集器并汇总告警（Python 2.7）
"""
from __future__ import print_function
import os
import sys
import logging
import json

# 保证可导入同项目模块
_monitor_root = os.path.dirname(os.path.abspath(__file__))
if _monitor_root not in sys.path:
    sys.path.insert(0, _monitor_root)

from config import load_config, DEFAULT_CONFIG, _deep_merge
from collectors import cpu as cpu_collector
from collectors import memory as memory_collector
from collectors import disk as disk_collector
from collectors import file_integrity as file_integrity_collector
from collectors import process as process_collector
from collectors import port as port_collector
import remote as remote_collector


def setup_logging(log_path=None, level="INFO"):
    log_path = log_path or "/var/log/monitor_hosts.log"
    level = getattr(logging, level.upper(), logging.INFO)
    try:
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.isdir(log_dir):
            os.makedirs(log_dir, 0o755)
    except OSError:
        log_path = None
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_path:
        try:
            handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
        except (IOError, TypeError):
            pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    return logging.getLogger("monitor_hosts")


def run_once_remote(config, logger):
    """
    远程模式：对 target_hosts.hosts 中每台主机 SSH 执行采集，聚合告警与结果。
    返回 (alerts, results)，其中 results["hosts"] = { host: { alerts, results } 或 { error } }。
    """
    th = config.get("target_hosts", {})
    hosts = th.get("hosts") or []
    timeout = int(th.get("ssh_timeout") or 30)
    if not hosts:
        return [], {"hosts": {}}
    all_alerts = []
    by_host = {}
    for h in hosts:
        if not isinstance(h, dict):
            continue
        spec = dict(h)
        spec.setdefault("remote_project_path", th.get("remote_project_path"))
        spec.setdefault("remote_command", th.get("remote_command"))
        host_config = _deep_merge(config, h.get("config_override", {}))
        out = remote_collector.run_remote_collect(spec, timeout=timeout, config_for_host=host_config)
        host_id = out.get("host", "unknown")
        by_host[host_id] = out
        if "error" in out:
            all_alerts.append({"metric": "remote", "host": host_id, "message": out["error"]})
        else:
            for a in out.get("alerts", []):
                all_alerts.append({
                    "metric": a.get("metric", "remote"),
                    "host": host_id,
                    "message": a.get("message", ""),
                })
    return all_alerts, {"hosts": by_host}


def run_once(config, logger, build_baseline=False):
    alerts = []
    results = {}

    # CPU
    if config.get("cpu", {}).get("enabled", True):
        try:
            cfg = config.get("cpu", {})
            usage, detail = cpu_collector.get_cpu_usage(cfg.get("interval_sec", 2))
            results["cpu"] = {"usage_percent": usage, "detail": detail}
            if usage is not None and usage >= cfg.get("warn_percent", 85):
                alerts.append({"metric": "cpu", "message": "CPU usage {0}% >= {1}%".format(usage, cfg.get("warn_percent", 85))})
        except Exception as e:
            logger.exception("cpu collect failed")
            alerts.append({"metric": "cpu", "message": str(e)})
    else:
        results["cpu"] = {"skipped": True}

    # Memory
    if config.get("memory", {}).get("enabled", True):
        try:
            cfg = config.get("memory", {})
            used_pct, detail = memory_collector.get_memory_usage()
            results["memory"] = {"used_percent": used_pct, "detail": detail}
            if used_pct is not None and used_pct >= cfg.get("warn_percent", 85):
                alerts.append({"metric": "memory", "message": "Memory usage {0}% >= {1}%".format(used_pct, cfg.get("warn_percent", 85))})
        except Exception as e:
            logger.exception("memory collect failed")
            alerts.append({"metric": "memory", "message": str(e)})
    else:
        results["memory"] = {"skipped": True}

    # Disk
    if config.get("disk", {}).get("enabled", True):
        try:
            cfg = config.get("disk", {})
            mounts = cfg.get("mounts", ["/"])
            disk_list = disk_collector.get_disk_usage(mounts)
            results["disk"] = []
            for mount, used_pct, detail in disk_list:
                results["disk"].append({"mount": mount, "used_percent": used_pct, "detail": detail})
                if used_pct is not None and used_pct >= cfg.get("warn_percent", 85):
                    alerts.append({"metric": "disk", "message": "Disk {0} usage {1}% >= {2}%".format(mount, used_pct, cfg.get("warn_percent", 85))})
        except Exception as e:
            logger.exception("disk collect failed")
            alerts.append({"metric": "disk", "message": str(e)})
    else:
        results["disk"] = {"skipped": True}

    # File integrity
    if config.get("file_integrity", {}).get("enabled", True):
        try:
            cfg = config.get("file_integrity", {})
            watch_dirs = cfg.get("watch_dirs", [])
            baseline_path = cfg.get("baseline_path")
            exclude = cfg.get("exclude_patterns", [])
            if build_baseline:
                file_integrity_collector.build_baseline(
                    watch_dirs, exclude, baseline_path,
                    max_file_size_to_hash=cfg.get("max_file_size_to_hash", 0),
                    max_files=cfg.get("max_files", 0),
                    max_depth=cfg.get("max_depth", 0))
                logger.info("File baseline built: {0}".format(baseline_path))
                results["file_integrity"] = {"baseline_built": True}
            elif watch_dirs and baseline_path:
                integrity_alerts, _ = file_integrity_collector.check_integrity(
                    watch_dirs, baseline_path, exclude,
                    use_mtime_only=cfg.get("use_mtime_only", False),
                    hash_only_if_changed=cfg.get("hash_only_if_changed", True),
                    max_file_size_to_hash=cfg.get("max_file_size_to_hash", 0),
                    max_files=cfg.get("max_files", 0),
                    max_depth=cfg.get("max_depth", 0))
                results["file_integrity"] = {"alerts": integrity_alerts}
                for a in integrity_alerts:
                    alerts.append({"metric": "file_integrity", "message": "{0}: {1}".format(a.get("type"), a.get("path", ""))})
        except Exception as e:
            logger.exception("file_integrity failed")
            alerts.append({"metric": "file_integrity", "message": str(e)})
    else:
        results["file_integrity"] = {"skipped": True}

    # Process
    if config.get("process", {}).get("enabled", True):
        try:
            cfg = config.get("process", {})
            expected = cfg.get("expected_names", [])
            must_running = cfg.get("must_running", True)
            use_light = cfg.get("use_light_check", True)
            ok, missing, found = process_collector.check_processes(expected, must_running, use_light_check=use_light)
            results["process"] = {"ok": ok, "missing": missing, "found": found}
            if not ok:
                alerts.append({"metric": "process", "message": "Expected process(s) missing or not running: {0}".format(missing)})
        except Exception as e:
            logger.exception("process check failed")
            alerts.append({"metric": "process", "message": str(e)})
    else:
        results["process"] = {"skipped": True}

    # Port
    if config.get("port", {}).get("enabled", True):
        try:
            cfg = config.get("port", {})
            expected_ports = cfg.get("expected_ports", [])
            ok, missing, found = port_collector.check_ports(expected_ports)
            results["port"] = {"ok": ok, "missing": missing, "listening": found}
            if not ok:
                alerts.append({"metric": "port", "message": "Expected port(s) not listening: {0}".format(missing)})
        except Exception as e:
            logger.exception("port check failed")
            alerts.append({"metric": "port", "message": str(e)})
    else:
        results["port"] = {"skipped": True}

    return alerts, results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Linux host monitor (Python 2.7)")
    parser.add_argument("--config", "-c", default=None, help="Config JSON path")
    parser.add_argument("--config-stdin", action="store_true", help="Read config JSON from stdin (merge with default)")
    parser.add_argument("--build-baseline", action="store_true", help="Build file integrity baseline and exit")
    parser.add_argument("--json", action="store_true", help="Output results as JSON to stdout")
    parser.add_argument("--once", action="store_true", default=True, help="Run once (default)")
    args = parser.parse_args()

    if getattr(args, "config_stdin", False):
        config = _deep_merge(dict(DEFAULT_CONFIG), json.load(sys.stdin))
    else:
        config = load_config(args.config)
    log_cfg = config.get("log", {})
    logger = setup_logging(log_cfg.get("path"), log_cfg.get("level"))

    if not config.get("monitoring_enabled", True):
        if args.json:
            print(json.dumps({
                "alerts": [],
                "results": {"monitoring_disabled": True, "message": "监控已关闭，未执行采集；可登录后台查看或修改配置。"},
            }, indent=2))
        else:
            logger.info("监控已关闭，未执行采集；可登录后台查看或修改配置。")
        return 0

    th = config.get("target_hosts", {})
    mode = (th.get("mode") or "local").strip().lower()
    hosts = th.get("hosts") or []

    if args.build_baseline:
        alerts, results = run_once(config, logger, build_baseline=True)
    elif mode == "remote" and hosts:
        alerts, results = run_once_remote(config, logger)
    else:
        alerts, results = run_once(config, logger, build_baseline=False)
    if args.build_baseline:
        return 0

    if alerts:
        try:
            from notifiers import send_alert_notifications
            send_alert_notifications(alerts, config, logger)
        except Exception as e:
            if logger:
                logger.exception("告警通知发送失败: %s", e)

    if args.json:
        print(json.dumps({"alerts": alerts, "results": results}, indent=2))
    else:
        for a in alerts:
            host = a.get("host", "")
            part = ("[%s] " % host) if host else ""
            logger.warning("%s[%s] %s", part, a.get("metric", ""), a.get("message", ""))
        if not alerts:
            logger.info("All checks passed.")

    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
