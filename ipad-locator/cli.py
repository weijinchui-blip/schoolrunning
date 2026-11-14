# -*- coding: utf-8 -*-
"""
命令行版（适合脚本调用 / 定时任务）

  python cli.py list
  python cli.py set 39.908722 116.397499
  python cli.py set 39.908722 116.397499 --hold 600     # 保持 600 秒后自动撤销
  python cli.py walk 39.9087 116.3975 39.9170 116.3975 --speed 10
  python cli.py track route.gpx --interval 1
  python cli.py clear
"""

import argparse
import sys
import time

import core


def main() -> int:
    ap = argparse.ArgumentParser(description="iPad / iPhone 系统定位模拟（命令行）")
    ap.add_argument("--udid", help="指定设备 UDID（默认第一台）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出已连接的设备")

    p = sub.add_parser("set", help="设定固定坐标")
    p.add_argument("lat", type=float)
    p.add_argument("lon", type=float)
    p.add_argument("--hold", type=float, default=0, help="保持秒数，0 = 一直保持到 Ctrl+C")

    p = sub.add_parser("walk", help="从 A 走到 B")
    p.add_argument("a_lat", type=float)
    p.add_argument("a_lon", type=float)
    p.add_argument("b_lat", type=float)
    p.add_argument("b_lon", type=float)
    p.add_argument("--speed", type=float, default=5.0, help="km/h")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--loop", action="store_true", help="到终点后折返")

    p = sub.add_parser("gait", help="拟真跑：从 A 跑到 B，按步幅×步频生成速度曲线")
    p.add_argument("a_lat", type=float)
    p.add_argument("a_lon", type=float)
    p.add_argument("b_lat", type=float)
    p.add_argument("b_lon", type=float)
    p.add_argument("--stride", type=float, default=1.05, help="步幅（米）")
    p.add_argument("--cadence", type=float, default=170.0, help="步频（步/分）")
    p.add_argument("--noise", type=float, default=2.5, help="GPS 噪声（米）")
    p.add_argument("--pause", type=float, default=0.12, help="每公里停顿概率")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=None)

    p = sub.add_parser("track", help="回放 GPX / CSV 轨迹")
    p.add_argument("file")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--loop", action="store_true")

    p = sub.add_parser("clear", help="撤销模拟，恢复真实定位")

    args = ap.parse_args()
    log = lambda m: print(time.strftime("[%H:%M:%S] "), m, flush=True)

    if args.cmd == "list":
        devs = core.DeviceSession(log=log).list_devices()
        if not devs:
            print("没有检测到设备")
            return 1
        for d in devs:
            print(f"{d['name']}  {d.get('model')}  iPadOS {d.get('ios')}  {d['connection']}  {d['udid']}")
        return 0

    session = core.DeviceSession(log=log)
    walker = core.Walker(session, log=log)
    try:
        if args.cmd == "clear":
            session.connect(args.udid)
            session.clear_location()
            return 0

        session.connect(args.udid)
        print(f"已连接：{session.info.get('name')} / iPadOS {session.info.get('ios')}")

        if args.cmd == "set":
            session.set_location(args.lat, args.lon)
            print(f"定位已设为 {args.lat}, {args.lon}")
            if args.hold and args.hold > 0:
                print(f"保持 {args.hold:g} 秒…")
                time.sleep(args.hold)
                session.clear_location()
                print("已撤销")
            else:
                print("正在保持，Ctrl+C 结束（结束后设备自动恢复真实定位）")
                while True:
                    time.sleep(1)
        elif args.cmd == "walk":
            walker.walk_line(
                (args.a_lat, args.a_lon), (args.b_lat, args.b_lon),
                speed_kmh=args.speed, interval=args.interval, loop=args.loop,
            )
            while walker.running:
                time.sleep(0.5)
        elif args.cmd == "gait":
            gait = core.Gait(args.stride, args.cadence, args.noise, args.pause, seed=args.seed)
            print("步态：" + gait.describe())
            if not gait.in_window():
                print("⚠ 速度不在 1.5~6.5 m/s 统计窗口内，里程可能不计数")
            walker.walk_gait(
                [(args.a_lat, args.a_lon), (args.b_lat, args.b_lon)], gait, interval=args.interval
            )
            while walker.running:
                time.sleep(0.5)
            st = walker.stats
            if st:
                print(
                    f"上报 {st['n']} 个点 / {st['reported_m']:.0f} 米，平均 {st['avg_kmh']:.1f} km/h"
                    f"（配速 {st['avg_pace']:.2f}），步数约 {st['steps']}，"
                    f"区间命中 {st['in_range'] * 100:.0f}%，瞬移 {st['jumps']}"
                )
        elif args.cmd == "track":
            pts = core.parse_gpx(args.file) if args.file.lower().endswith(".gpx") else core.parse_csv_points(args.file)
            if len(pts) < 2:
                print("文件里没有有效坐标点")
                return 2
            walker.walk_points(pts, interval=args.interval, loop=args.loop)
            while walker.running:
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n已中断")
    finally:
        try:
            walker.stop()
        except Exception:
            pass
        try:
            session.clear_location()
        except Exception:
            pass
        session.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
