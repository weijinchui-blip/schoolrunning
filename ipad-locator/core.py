# -*- coding: utf-8 -*-
"""
iPad / iPhone 系统定位模拟 —— 核心后端

原理：通过 usbmuxd 走 USB 连接设备，iOS 17.4+ 用 pymobiledevice3 的
「免 root 用户态隧道」拿到 RemoteServiceDiscovery（RSD），再连上
com.apple.instruments.dtservicehub 这个 DVT 通道，调用
`simulateLocationWithLatitude:longitude:` 直接把系统 GPS 输出改成我们给的坐标。

这和 Xcode 里 Debug -> Simulate Location 用的是同一条官方通道，
所以在 App 看来它就是"真实定位"，不走 VPN、不装描述文件、不越狱。

注意：模拟定位是"会话级"的。本进程退出 / 线被拔 / 会话断开，
设备会自动恢复真实 GPS —— 这正是我们要的安全兜底。
"""

from __future__ import annotations

import asyncio
import math
import threading
from contextlib import AsyncExitStack
from typing import Any, Callable, Dict, List, Optional

from pymobiledevice3 import usbmux
from pymobiledevice3.lockdown import create_using_usbmux


def _noop(_msg: str) -> None:
    pass


class DeviceSession:
    """一个设备会话：维持隧道 + DVT 通道 + 定位会话。"""

    def __init__(self, log: Optional[Callable[[str], None]] = None) -> None:
        self._log = log or _noop
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop_main, name="loc-engine", daemon=True)
        self._thread.start()
        self._tunnel = None          # UserspaceRsdTunnel
        self._stack: Optional[AsyncExitStack] = None
        self._loc = None             # LocationSimulation
        self._udid: Optional[str] = None
        self._info: Dict[str, Any] = {}
        self._last: Optional[tuple] = None
        self._guard = threading.RLock()

    # ------------------------------------------------------------------ 基建
    def _loop_main(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro, timeout: float = 240):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout)

    @property
    def connected(self) -> bool:
        return self._loc is not None

    @property
    def info(self) -> Dict[str, Any]:
        return dict(self._info)

    @property
    def last_location(self) -> Optional[tuple]:
        return self._last

    # -------------------------------------------------------------- 设备列表
    async def _list_devices(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for dev in await usbmux.list_devices():
            item: Dict[str, Any] = {
                "udid": dev.serial,
                "connection": dev.connection_type,
                "devid": dev.devid,
                "name": "iOS 设备",
                "model": "",
                "ios": "",
                "build": "",
                "paired": True,
            }
            try:
                lk = await create_using_usbmux(
                    serial=dev.serial,
                    autopair=False,
                    connection_type=dev.connection_type,
                )
                try:
                    vals = await lk.get_value() or {}
                    item.update(
                        {
                            "name": vals.get("DeviceName") or item["name"],
                            "model": vals.get("ProductType", ""),
                            "ios": vals.get("ProductVersion", ""),
                            "build": vals.get("BuildVersion", ""),
                            "udid": vals.get("UniqueDeviceID", dev.serial),
                        }
                    )
                finally:
                    try:
                        await lk.close()
                    except Exception:
                        pass
            except Exception as exc:  # 未配对 / 锁屏时可能拿不到信息
                item["paired"] = False
                item["note"] = str(exc)
            out.append(item)
        return out

    def list_devices(self) -> List[Dict[str, Any]]:
        return self._run(self._list_devices(), timeout=90)

    # ------------------------------------------------------------ 连接 / 断开
    async def _open(self, udid: str) -> None:
        await self._close()

        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        stack = AsyncExitStack()
        provider = None
        tunnel = None
        try:
            # 首选：iOS 17.4+ 免 root 用户态隧道（PyTCP 用户态网络栈，不要管理员权限、不要虚拟网卡）
            try:
                from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel

                self._log("正在建立免 root 隧道（首次约 3~10 秒）…")
                tunnel = UserspaceRsdTunnel(serial=udid)
                provider = await tunnel.aopen()
                self._log("隧道就绪（RSD 已连通）")
            except Exception as exc:
                self._log(f"用户态隧道不可用（{type(exc).__name__}: {exc}），改用传统 lockdown 通道…")
                provider = await stack.enter_async_context(
                    await create_using_usbmux(serial=udid, autopair=True)
                )

            self._log("正在打开 DVT 开发者通道…")
            dvt = await stack.enter_async_context(DvtProvider(provider))
            loc = await stack.enter_async_context(LocationSimulation(dvt))
            self._log("定位模拟通道已就绪")

            self._tunnel = tunnel
            self._stack = stack
            self._loc = loc
            self._udid = udid
        except BaseException:
            try:
                await stack.aclose()
            except Exception:
                pass
            if tunnel is not None:
                try:
                    await tunnel.aclose()
                except Exception:
                    pass
            raise

    def connect(self, udid: Optional[str] = None) -> None:
        """连接设备（udid 为空时取第一台）。"""
        with self._guard:
            if udid is None:
                devices = self.list_devices()
                if not devices:
                    raise RuntimeError("没有检测到 iOS 设备，请检查数据线 / 是否点了「信任」")
                udid = devices[0]["udid"]
            self._log(f"连接设备 {udid[:12]}…")
            self._run(self._open(udid), timeout=300)

            # 顺便把设备信息缓存下来给界面显示
            try:
                for d in self.list_devices():
                    if d["udid"].replace("-", "") == udid.replace("-", ""):
                        self._info = d
                        break
            except Exception:
                pass
            self._info.setdefault("udid", udid)

    async def _close(self) -> None:
        if self._stack is not None:
            try:
                # 先清掉模拟定位，再拆通道，避免残留
                if self._loc is not None:
                    try:
                        await asyncio.wait_for(self._loc.clear(), timeout=8)
                    except Exception:
                        pass
            finally:
                try:
                    await self._stack.aclose()
                except Exception:
                    pass
                self._stack = None
        if self._tunnel is not None:
            try:
                await self._tunnel.aclose()
            except Exception:
                pass
            self._tunnel = None
        self._loc = None
        self._last = None

    def disconnect(self) -> None:
        with self._guard:
            self._run(self._close(), timeout=120)
            self._log("已断开，设备恢复真实定位")

    # ------------------------------------------------------------------ 定位
    async def _set(self, lat: float, lon: float) -> None:
        if self._loc is None:
            raise RuntimeError("尚未连接设备")
        await self._loc.set(float(lat), float(lon))

    def set_location(self, lat: float, lon: float, retry: bool = True) -> None:
        """把设备系统定位设到 (lat, lon)。"""
        lat, lon = float(lat), float(lon)
        if not (-90 <= lat <= 90):
            raise ValueError("纬度必须在 -90 ~ 90 之间")
        if not (-180 <= lon <= 180):
            raise ValueError("经度必须在 -180 ~ 180 之间")
        with self._guard:
            if self._loc is None:
                raise RuntimeError("尚未连接设备")
            try:
                self._run(self._set(lat, lon), timeout=60)
            except Exception as exc:
                if not retry:
                    raise
                self._log(f"发送失败（{type(exc).__name__}），重连一次…")
                udid = self._udid
                self._run(self._open(udid), timeout=300)
                self._run(self._set(lat, lon), timeout=60)
            self._last = (lat, lon)

    async def _clear(self) -> None:
        if self._loc is not None:
            await self._loc.clear()

    def clear_location(self) -> None:
        """撤销模拟，回到真实 GPS。"""
        with self._guard:
            if self._loc is None:
                return
            try:
                self._run(self._clear(), timeout=60)
            except Exception as exc:
                self._log(f"撤销模拟定位失败：{exc}")
            self._last = None

    def shutdown(self) -> None:
        try:
            self.disconnect()
        except Exception:
            pass
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass


# ------------------------------------------------------------------ 工具函数
EARTH_R = 6371008.8


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点球面距离（米）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def interpolate(lat1: float, lon1: float, lat2: float, lon2: float, t: float) -> tuple:
    """在两点之间按比例 t(0~1) 取坐标（够用的小范围线性插值）。"""
    return lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t


def offset_meters(lat: float, lon: float, dx_m: float, dy_m: float) -> tuple:
    """相对某点偏移若干米（dx 东，dy 北）。"""
    dlat = dy_m / 111320.0
    dlon = dx_m / (111320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return lat + dlat, lon + dlon


class Walker:
    """在后台线程里按速度沿直线/轨迹推送坐标，用于"走动"效果。"""

    def __init__(self, session: DeviceSession, log: Optional[Callable[[str], None]] = None):
        self.session = session
        self._log = log or _noop
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.progress: float = 0.0
        self.samples: List[tuple] = []      # (t, lat, lon) 上报点，供自检用
        self.stats: Dict[str, Any] = {}

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _spawn(self, fn, *args) -> None:
        if self.running:
            raise RuntimeError("已经在移动中")
        self._stop.clear()
        self._thread = threading.Thread(target=fn, args=args, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=6)
        self._thread = None

    # ---- 直线行走：起点 -> 终点，speed_kmh 速度，interval 推送间隔
    def walk_line(
        self,
        start: tuple,
        end: tuple,
        speed_kmh: float = 5.0,
        interval: float = 1.0,
        loop: bool = False,
    ) -> None:
        import time

        def job() -> None:
            a = (float(start[0]), float(start[1]))
            b = (float(end[0]), float(end[1]))
            total = haversine(a[0], a[1], b[0], b[1])
            if total < 1:
                self._log("起终点太近（不足 1 米），直接设点")
                self.session.set_location(b[0], b[1])
                return
            v = max(speed_kmh * 1000.0 / 3600.0, 0.3)
            self._log(f"开始移动：全程 {total:.0f} 米，速度 {speed_kmh:g} km/h，约 {total / v / 60:.1f} 分钟")
            t0 = time.monotonic()
            last_log = -10.0
            while not self._stop.is_set():
                elapsed = time.monotonic() - t0
                travelled = v * elapsed
                if travelled >= total:
                    try:
                        self.session.set_location(b[0], b[1])
                    except Exception as exc:
                        self._log(f"推送失败：{exc}")
                    self.progress = 1.0
                    if loop:
                        a, b = b, a
                        total = haversine(a[0], a[1], b[0], b[1])
                        t0 = time.monotonic()
                        self._log("折返，往回走")
                        continue
                    self._log("已到达终点")
                    break
                t = travelled / total
                lat, lon = interpolate(a[0], a[1], b[0], b[1], t)
                try:
                    self.session.set_location(lat, lon)
                except Exception as exc:
                    self._log(f"推送失败：{exc}")
                    break
                self.progress = t
                if elapsed - last_log >= 5.0:
                    last_log = elapsed
                    self._log(f"进度 {t * 100:5.1f}%  ({lat:.6f}, {lon:.6f})")
                if self._stop.wait(interval):
                    break
            self._log("移动已停止")
            self.progress = 0.0

        self._spawn(job)

    # ---- 轨迹回放：points = [(lat, lon), ...]，按 interval 逐点推送
    def walk_points(self, points, interval: float = 1.0, loop: bool = False) -> None:
        pts = [(float(a), float(b)) for a, b in points]
        if len(pts) < 2:
            raise ValueError("轨迹点不足 2 个")

        def job() -> None:
            self._log(f"开始回放轨迹：{len(pts)} 个点，间隔 {interval:g} 秒")
            idx = 0
            while not self._stop.is_set():
                for i, (lat, lon) in enumerate(pts):
                    if self._stop.is_set():
                        break
                    try:
                        self.session.set_location(lat, lon)
                    except Exception as exc:
                        self._log(f"推送失败：{exc}")
                        self._stop.set()
                        break
                    self.progress = (i + 1) / len(pts)
                    idx += 1
                    if idx % 10 == 0:
                        self._log(f"已推送 {idx} 点（{lat:.6f}, {lon:.6f}）")
                    if self._stop.wait(interval):
                        break
                if not loop:
                    break
            self._log("轨迹回放结束")

        self._spawn(job)

    # ---- 沿画好的折线走：按总长度和速度匀速推进（手绘轨迹用这个）
    def walk_path(self, points, speed_kmh: float = 5.0, interval: float = 1.0, loop: bool = False) -> None:
        import time

        pts = [(float(a), float(b)) for a, b in points]
        if len(pts) < 2:
            raise ValueError("轨迹至少要 2 个点")

        def job() -> None:
            v = max(speed_kmh * 1000.0 / 3600.0, 0.3)
            segs = [haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]
            total = sum(segs)
            if total < 1:
                self.session.set_location(pts[-1][0], pts[-1][1])
                self._log("轨迹总长不足 1 米，直接设到最后一个点")
                return
            self._log(
                f"开始沿轨迹移动：{len(pts)} 个点 / 全长 {total:.0f} 米 / 速度 {speed_kmh:g} km/h "
                f"→ 约 {total / v / 60:.1f} 分钟"
            )
            cur = list(pts)
            cur_segs = list(segs)
            cur_total = total
            t0 = time.monotonic()
            last_log = -10.0
            while not self._stop.is_set():
                s = v * (time.monotonic() - t0)
                if s >= cur_total:
                    if loop:
                        cur.reverse()
                        cur_segs = [
                            haversine(cur[i][0], cur[i][1], cur[i + 1][0], cur[i + 1][1])
                            for i in range(len(cur) - 1)
                        ]
                        cur_total = sum(cur_segs)
                        t0 = time.monotonic()
                        self._log("折返，往回走")
                        continue
                    try:
                        self.session.set_location(cur[-1][0], cur[-1][1])
                    except Exception as exc:
                        self._log(f"推送失败：{exc}")
                    self.progress = 1.0
                    self._log("轨迹已走完")
                    break
                acc = 0.0
                lat = lon = None
                for i, d in enumerate(cur_segs):
                    if acc + d >= s or i == len(cur_segs) - 1:
                        t = 0.0 if d <= 0 else max(0.0, min(1.0, (s - acc) / d))
                        lat, lon = interpolate(cur[i][0], cur[i][1], cur[i + 1][0], cur[i + 1][1], t)
                        break
                    acc += d
                if lat is None:
                    break
                try:
                    self.session.set_location(lat, lon)
                except Exception as exc:
                    self._log(f"推送失败：{exc}")
                    break
                self.progress = s / cur_total
                if time.monotonic() - t0 - last_log >= 5.0:
                    last_log = time.monotonic() - t0
                    self._log(f"进度 {self.progress * 100:5.1f}%  ({lat:.6f}, {lon:.6f})")
                if self._stop.wait(interval):
                    break
            self._log("移动已停止")
            self.progress = 0.0

        self._spawn(job)

    # ---- 拟真跑步：按「步幅 × 步频」推导速度，逐步推进 + GPS 噪声 + 随机停顿
    def walk_gait(self, points, gait: "Gait", interval: float = 1.0, loop: bool = False) -> None:
        """
        和 walk_path 的区别：速度不是一个人为填的常数，而是由步幅和步频算出来的，
        并且每两步一个微小波动、长距离有掉速、偶尔停下来等红灯、坐标带相关的 GPS 漂移。
        实际推送序列和「自检」用的是同一个生成器，所以自检结果就是真跑出来的结果。
        """
        import time

        pts = [(float(a), float(b)) for a, b in points]
        if len(pts) < 2:
            raise ValueError("轨迹至少要 2 个点")
        total = sum(
            haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)
        )
        if total < 1:
            self.session.set_location(pts[-1][0], pts[-1][1])
            self._log("轨迹总长不足 1 米，直接设到最后一个点")
            return

        def job() -> None:
            self.samples = []
            self._log("拟真跑步：" + gait.describe())
            if not gait.in_window():
                self._log(
                    f"⚠ 当前速度 {gait.speed:.2f} m/s 不在校园跑统计窗口 1.5~6.5 m/s 内，"
                    "这段里程可能不计数"
                )
            self._log(f"全程 {total:.0f} 米，预计 {total / gait.speed / 60:.1f} 分钟，约 {int(total / gait.stride_m)} 步")

            last_log = -10.0
            for t, rlat, rlon, v, s in gait_samples(pts, gait, interval):
                if self._stop.is_set():
                    break
                try:
                    self.session.set_location(rlat, rlon)
                except Exception as exc:
                    self._log(f"推送失败：{exc}")
                    break
                self.samples.append((t, rlat, rlon))
                self.progress = s / total
                if t - last_log >= 8.0:
                    last_log = t
                    pace = (1000 / v / 60) if v > 0.1 else 0
                    self._log(
                        f"{s:6.0f}/{total:.0f} 米  已跑 {t / 60:.1f} 分  {v * 3.6:4.1f} km/h"
                        + (f"  配速 {pace:.2f}" if pace else "  停顿中")
                    )
                if s >= total:
                    break
                if self._stop.wait(interval):
                    break

            self.stats = analyze_track(self.samples, total, gait)
            st = self.stats
            if st:
                self._log(
                    f"结束：上报 {st['n']} 个点 / {st['reported_m']:.0f} 米，平均 {st['avg_kmh']:.1f} km/h"
                    f"（配速 {st['avg_pace']:.2f}），步数约 {st['steps']}，"
                    f"有效速度区间占比 {st['in_range'] * 100:.0f}%"
                )
            self.progress = 0.0

        self._spawn(job)

    # ---- 原地微抖：防止"长时间坐标一动不动"看起来假
    def jitter(self, center: tuple, radius_m: float = 3.0, interval: float = 5.0) -> None:
        import random

        def job() -> None:
            lat0, lon0 = center
            self._log(f"开始原地微抖：半径 {radius_m:g} 米，每 {interval:g} 秒一次")
            while not self._stop.is_set():
                ang = random.random() * math.tau
                r = radius_m * math.sqrt(random.random())
                lat, lon = offset_meters(lat0, lon0, r * math.cos(ang), r * math.sin(ang))
                try:
                    self.session.set_location(lat, lon)
                except Exception as exc:
                    self._log(f"推送失败：{exc}")
                    break
                if self._stop.wait(interval):
                    break
            self._log("微抖已停止")

        self._spawn(job)


# ------------------------------------------------------------ 拟真步态参数
def gait_samples(pts, gait: "Gait", interval: float = 1.0):
    """
    按步态生成上报点序列，逐条 yield (t, lat, lon, v, s)：
    t=已用时, v=当前瞬时速度(m/s), s=已推进的路径距离(m)。

    这是「真跑」和「自检」共用的唯一实现，保证自检结果就是实际会发出去的数据。
    """
    import bisect
    import random

    segs = [haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]
    total = sum(segs)
    if total <= 0:
        return
    cum = [0.0]
    for d in segs:
        cum.append(cum[-1] + d)

    def point_at(s: float) -> tuple:
        i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(segs) - 1)
        d = segs[i]
        t = 0.0 if d <= 0 else max(0.0, min(1.0, (s - cum[i]) / d))
        return interpolate(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], t)

    rng = random.Random(gait.seed)
    v_base = gait.speed
    s = 0.0
    t = 0.0
    steps = 0
    noise = (0.0, 0.0)
    pause_left = 0.0
    sigma = gait.jitter_m / 2.6

    while True:
        frac = min(s / total, 1.0)
        # 后程掉速 3%，最后 5% 冲一下
        fatigue = 1.0 - 0.03 * max(0.0, (frac - 0.65) / 0.35)
        if frac > 0.95:
            fatigue *= 1.04
        # 每两步一个周期的左右脚不对称波动
        wobble = 1.0 + 0.05 * math.sin((steps % 2) * math.pi + t * 1.7)
        v = v_base * fatigue * wobble

        if pause_left > 0:
            v = 0.0
            pause_left -= interval
        elif gait.pause_prob > 0 and rng.random() < gait.pause_prob * v_base * interval / 1000.0:
            pause_left = rng.uniform(*gait.pause_sec)
            v = 0.0

        s = min(s + v * interval, total)
        steps += int(round(v * interval / max(gait.stride_m, 0.1)))
        t += interval

        la, lo = point_at(s)
        # AR(1)：上一刻的定位误差有 85% 延续到下一刻，像真实 GPS 缓慢漂移
        noise = (
            0.85 * noise[0] + 0.15 * rng.gauss(0, sigma),
            0.85 * noise[1] + 0.15 * rng.gauss(0, sigma),
        )
        rlat, rlon = offset_meters(la, lo, noise[1], noise[0])
        yield (round(t, 2), rlat, rlon, v, s)
        if s >= total:
            break


class Gait:
    """
    真人跑步的步态参数。速度 = 步幅 × 步频，这也正是校园跑服务端用来判断
    "这段轨迹是不是人跑出来的"的核心关系：步数、距离、时间要自洽。
    """

    def __init__(
        self,
        stride_m: float = 1.05,
        cadence: float = 170.0,
        jitter_m: float = 2.5,
        pause_prob: float = 0.12,
        pause_sec=(6.0, 20.0),
        seed=None,
    ) -> None:
        self.stride_m = min(max(float(stride_m), 0.30), 1.80)
        self.cadence = min(max(float(cadence), 60.0), 240.0)
        self.jitter_m = min(max(float(jitter_m), 0.0), 20.0)
        self.pause_prob = min(max(float(pause_prob), 0.0), 3.0)
        self.pause_sec = pause_sec
        self.seed = seed

    @property
    def speed(self) -> float:
        """m/s"""
        return self.stride_m * self.cadence / 60.0

    @property
    def pace(self) -> float:
        """分/公里"""
        return 1000.0 / self.speed / 60.0 if self.speed else 99.0

    def in_window(self, lo: float = 1.5, hi: float = 6.5, margin: float = 0.05) -> bool:
        """
        是否稳妥地落在统计窗口内。留 5% 余量：因为速度本身有 ±5% 的步态波动，
        刚好卡在 1.53 m/s 这种边界值时，一波动就掉出窗口，那些区间不计里程。
        """
        return lo * (1 + margin) <= self.speed <= hi * (1 - margin)

    def describe(self) -> str:
        return (
            f"步幅 {self.stride_m:g} m × 步频 {self.cadence:g} 步/分 "
            f"= {self.speed:.2f} m/s（{self.speed * 3.6:.1f} km/h，配速 {self.pace:.2f} 分/公里）"
        )


def analyze_track(samples, total_m: float = 0.0, gait: Optional[Gait] = None,
                  lo: float = 1.5, hi: float = 6.5) -> Dict[str, Any]:
    """
    按校园跑服务端的口径自检这条轨迹：
    相邻点算区间速度，统计有多少落在 [1.5, 6.5] m/s 的有效窗口里。
    """
    if not samples or len(samples) < 2:
        return {}
    speeds = []
    dist = 0.0
    for i in range(1, len(samples)):
        t0, la0, lo0 = samples[i - 1]
        t1, la1, lo1 = samples[i]
        d = haversine(la0, lo0, la1, lo1)
        dt = max(t1 - t0, 1e-6)
        dist += d
        speeds.append(d / dt)
    moving = [v for v in speeds if v > 0.2]
    in_range = [v for v in speeds if lo <= v <= hi]
    avg = sum(moving) / len(moving) if moving else 0.0
    steps = int(round(dist / gait.stride_m)) if gait else 0
    return {
        "n": len(samples),
        "duration": samples[-1][0] - samples[0][0],
        "reported_m": dist,
        "truth_m": total_m,
        "avg_mps": avg,
        "avg_kmh": avg * 3.6,
        "avg_pace": (1000 / avg / 60) if avg > 0.1 else 0.0,
        "max_mps": max(speeds) if speeds else 0.0,
        "min_mps": min(moving) if moving else 0.0,
        "in_range": (len(in_range) / len(speeds)) if speeds else 0.0,
        "jumps": sum(1 for v in speeds if v > 12),   # 瞬移点数
        "steps": steps,
        "stride": gait.stride_m if gait else 0.0,
        "cadence": gait.cadence if gait else 0.0,
    }


# -------------------------------------------------------------- GPX/CSV 解析
def parse_gpx(path: str) -> List[tuple]:
    """从 GPX 里按顺序取出 trkpt/rtept/wpt 的 (lat, lon)。"""
    import xml.etree.ElementTree as ET

    tree = ET.parse(path)
    root = tree.getroot()
    pts: List[tuple] = []
    for tag in ("trkpt", "rtept", "wpt"):
        for el in root.iter():
            if el.tag.split("}")[-1] == tag:
                try:
                    pts.append((float(el.get("lat")), float(el.get("lon"))))
                except (TypeError, ValueError):
                    continue
    return pts


def parse_csv_points(path: str) -> List[tuple]:
    """从 CSV 读取坐标：支持 lat,lon / 纬度,经度 两列，自动跳过表头。"""
    import csv

    pts: List[tuple] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            try:
                lat, lon = float(row[0]), float(row[1])
            except ValueError:
                continue
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                pts.append((lat, lon))
    return pts
