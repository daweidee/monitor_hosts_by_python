# -*- coding: utf-8 -*-
"""
远程采集：中心机通过 SSH 连接目标主机执行监控脚本并取回 JSON 结果（Python 2.7）
支持传入 config_for_host，通过 stdin 传给目标机（目标机需支持 --config-stdin）。
"""
from __future__ import print_function
import subprocess
import json
import base64


def _escape_single_quote(s):
    """对远程 shell 单引号包裹内的字符串转义。"""
    if s is None:
        return ""
    return str(s).replace("'", "'\"'\"'")


def run_remote_collect(host_spec, timeout=30, config_for_host=None):
    """
    在单台目标主机上通过 SSH 执行监控命令，取回 JSON。
    host_spec: dict，需含 host, user；可选 port, key_file, remote_project_path, remote_command, config_override
    config_for_host: 该目标使用的完整配置（默认+覆盖合并后），若提供则通过 stdin 传给远程 --config-stdin
    返回: {"host": str, "alerts": list, "results": dict} 或 {"host": str, "error": str}
    """
    host = host_spec.get("host") or ""
    user = host_spec.get("user") or "root"
    port = int(host_spec.get("port") or 22)
    key_file = host_spec.get("key_file") or ""
    remote_project_path = host_spec.get("remote_project_path") or "/opt/monitor_hosts"
    remote_command = host_spec.get("remote_command") or "python monitor_hosts/main.py --json"
    if config_for_host is not None:
        remote_command = "base64 -d | python monitor_hosts/main.py --json --config-stdin"
    if not host:
        return {"host": "unknown", "error": "missing host"}
    # 远程命令：cd 到项目目录后执行
    remote_cmd = "cd '%s' && %s" % (_escape_single_quote(remote_project_path), remote_command)
    args = [
        "ssh",
        "-o", "ConnectTimeout=%d" % timeout,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-p", str(port),
    ]
    if key_file:
        args.extend(["-i", key_file])
    args.append("%s@%s" % (user, host))
    args.append(remote_cmd)

    try:
        if config_for_host is not None:
            stdin_data = base64.b64encode(json.dumps(config_for_host))
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out, _ = proc.communicate(input=stdin_data)
            if proc.returncode != 0:
                return {"host": host, "error": out or "remote exit %s" % proc.returncode}
        else:
            out = subprocess.check_output(args, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        err = getattr(e, "output", None) or str(e)
        return {"host": host, "error": "ssh or remote error: %s" % err}
    except OSError as e:
        return {"host": host, "error": "ssh not available or failed: %s" % str(e)}
    # 从 stdout 中截取 JSON（可能前面有日志行）
    text = out.strip()
    try:
        # 尝试整段解析
        data = json.loads(text)
        return {
            "host": host,
            "alerts": data.get("alerts", []),
            "results": data.get("results", {}),
        }
    except ValueError:
        pass
    # 尝试取最后一行为 JSON（常见：前面是 logging，最后一行是 print(json.dumps(...))）
    lines = text.split("\n")
    for line in reversed(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
            return {
                "host": host,
                "alerts": data.get("alerts", []),
                "results": data.get("results", {}),
            }
        except ValueError:
            continue
    return {"host": host, "error": "no valid JSON in output"}
