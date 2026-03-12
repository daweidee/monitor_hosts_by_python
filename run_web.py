#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动监控配置 Web 界面（Python 2.7）
用法: python monitor_hosts/run_web.py [--host 0.0.0.0] [--port 5000]
"""
from __future__ import print_function
import os
import sys

_monitor_root = os.path.dirname(os.path.abspath(__file__))
if _monitor_root not in sys.path:
    sys.path.insert(0, _monitor_root)

# 在 web 目录下启动，以便 Flask 找到 templates/static
web_dir = os.path.join(_monitor_root, "web")
os.chdir(web_dir)
sys.path.insert(0, web_dir)

from app import app
import argparse

parser = argparse.ArgumentParser(description="Monitor Hosts Web UI")
parser.add_argument("--host", default="0.0.0.0", help="Bind host")
parser.add_argument("--port", type=int, default=5000, help="Bind port")
parser.add_argument("--debug", action="store_true", help="Debug mode")
args = parser.parse_args()

if __name__ == "__main__":
    print("Monitor Hosts Web: http://{0}:{1}/".format(args.host if args.host != "0.0.0.0" else "127.0.0.1", args.port))
    app.run(host=args.host, port=args.port, debug=args.debug)
