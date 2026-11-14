# -*- coding: utf-8 -*-
"""链路自测：连设备 -> 设坐标 -> 保持 20 秒 -> 撤销 -> 断开"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import DeviceSession

LOG = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

s = DeviceSession(log=LOG)
try:
    devs = s.list_devices()
    print("设备:", devs, flush=True)
    if not devs:
        raise SystemExit("无设备")

    t0 = time.time()
    s.connect(devs[0]["udid"])
    print(f"连接耗时 {time.time() - t0:.1f}s", flush=True)
    print("连接状态:", s.connected, flush=True)

    t0 = time.time()
    s.set_location(39.9087, 116.3975)
    print(f"设置定位成功，耗时 {time.time() - t0:.2f}s  ->  天安门 39.9087,116.3975", flush=True)

    print("保持 20 秒，期间连续推送 4 次不同坐标（模拟走动）…", flush=True)
    for i, (la, lo) in enumerate([(39.9090, 116.3980), (39.9095, 116.3985), (39.9100, 116.3990)]):
        time.sleep(5)
        t0 = time.time()
        s.set_location(la, lo)
        print(f"  第{i + 2}次推送 OK ({la},{lo}) {time.time() - t0:.2f}s", flush=True)

    time.sleep(3)
    s.clear_location()
    print("已撤销模拟定位（设备回到真实 GPS）", flush=True)
finally:
    s.shutdown()
print("自测结束", flush=True)
