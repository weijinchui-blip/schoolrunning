# -*- coding: utf-8 -*-
"""移动功能自测：直线移动 + 原地微抖"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

LOG = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
s = core.DeviceSession(log=LOG)
w = core.Walker(s, log=LOG)
try:
    s.connect()
    print("已连接:", s.info.get("name"), s.info.get("ios"), flush=True)

    print("\n--- 直线移动 80 米 / 10km/h / 间隔 0.5s ---", flush=True)
    w.walk_line((39.9087, 116.3975), (39.90942, 116.3975), speed_kmh=10, interval=0.5)
    t0 = time.time()
    while w.running and time.time() - t0 < 60:
        time.sleep(0.5)
    print(f"直线移动结束，用时 {time.time() - t0:.1f}s，进度 {w.progress:.2f}", flush=True)

    print("\n--- 原地微抖 6 秒 ---", flush=True)
    w.jitter((39.9087, 116.3975), radius_m=5, interval=1.5)
    time.sleep(6)
    w.stop()
    print("微抖已停", flush=True)

    s.clear_location()
    print("\n全部通过", flush=True)
finally:
    s.shutdown()
