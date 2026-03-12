#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Linux 主机监控入口（Python 2.7）
用法:
  单次运行: python main.py [--config monitor_config.json] [--json]
  建立文件基线: python main.py --build-baseline
"""
from __future__ import print_function
import os
import sys

# 以 monitor_hosts 为根，便于 import
_monitor_root = os.path.dirname(os.path.abspath(__file__))
if _monitor_root not in sys.path:
    sys.path.insert(0, _monitor_root)

from runner import main

if __name__ == "__main__":
    sys.exit(main())
