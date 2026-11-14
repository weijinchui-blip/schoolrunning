# -*- coding: utf-8 -*-
"""
传感器数据流生成器：从「轨迹 + 步态」推出一条物理自洽的 IMU 流。

设计原则：**同一套运动学**——GPS 速度、步频、加速度峰值、陀螺仪转向必须是同一个物理过程算出来的，
否则比对步频就会露馅（GPS 显示 2.8 Hz 步频，加速度却是 1.2 Hz，一眼假）。

输出（设备坐标系，屏幕朝上平放）：
    ax/ay/az  加速度，单位 g（含重力，1 g ≈ 9.81 m/s²）
    gx/gy/gz  角速度，单位 rad/s
    默认 50 Hz 采样

注意：本模块只负责「算出应该是什么数据」。真正把它塞进 App 的读数里需要越狱 + 注入
（见 sensor_spoof/ 目录），电脑通过 USB 没有任何写入传感器读数的接口。
"""

import json
import math
import random

import core

G = 9.80665


class Mount:
    """设备固定方式，决定重力落在哪个轴、振荡怎么分配"""

    HAND = "hand"      # 手持看屏幕：屏幕朝上，z 轴承重
    POCKET = "pocket"  # 揣兜里：屏幕朝内，y 轴承重（前后晃动更明显）
    ARM = "arm"        # 臂包：屏幕朝外，姿态更稳


def generate(
    points,
    gait,
    mount: str = Mount.HAND,
    fs: int = 50,
    interval: float = 1.0,
    seed=None,
):
    """
    返回 dict：
      meta  —— 采样率、步频、时长、距离、峰值等
      data  —— [[t, ax, ay, az, gx, gy, gz], ...]
    """
    rng = random.Random(seed)
    pts = [(float(a), float(b)) for a, b in points]
    if len(pts) < 2:
        raise ValueError("轨迹至少要 2 个点")

    # 1) 先按 GPS 侧同一套步态生成「每秒的位置与速度」，作为运动学基准
    track = list(core.gait_samples(pts, gait, interval))
    if not track:
        raise ValueError("轨迹长度不足")
    total_t = track[-1][0]

    # 2) 先把 1 秒分辨率的航向序列算好并展开，再插值到采样率——
    #    这样 90° 拐弯会分摊在约 1 秒里，角速度是人体能做到的 1~2 rad/s，而不是瞬间跳变
    headings = []
    for i in range(len(track)):
        j = min(i + 1, len(track) - 1)
        la1, lo1 = track[i][1], track[i][2]
        la2, lo2 = track[j][1], track[j][2]
        if abs(la2 - la1) < 1e-9 and abs(lo2 - lo1) < 1e-9:
            headings.append(headings[-1] if headings else 0.0)
        else:
            headings.append(math.atan2((lo2 - lo1) * math.cos(math.radians(la1)), la2 - la1))
    for i in range(1, len(headings)):
        while headings[i] - headings[i - 1] > math.pi:
            headings[i] -= 2 * math.pi
        while headings[i] - headings[i - 1] < -math.pi:
            headings[i] += 2 * math.pi

    def state_at(t):
        idx = min(max(t / interval, 0.0), len(track) - 1)
        i = int(idx)
        frac = idx - i
        v = track[i][3]
        if i + 1 < len(headings):
            heading = headings[i] + (headings[i + 1] - headings[i]) * frac
        else:
            heading = headings[i]
        return v, heading

    f_step = max(gait.cadence / 60.0, 0.5)   # 每秒步数
    w_step = 2 * math.pi * f_step

    # 3) 按 fs 采样
    data = []
    n = int(total_t * fs)
    prev_heading = None
    heading_rate = 0.0
    speeds = []

    for k in range(n):
        t = k / fs
        v, heading = state_at(t)
        speeds.append(v)

        # 起步 1.5 秒、收尾 1.5 秒的力度包络（真人不会瞬间达到满幅振荡）
        env = min(1.0, t / 1.5, max(0.0, (total_t - t) / 1.5) if total_t > 3 else 1.0)
        moving = v > 0.3

        # 速度越快，蹬地冲击越强（0.15 g 起步 → 3 m/s 时约 1.0 g 峰值）
        amp_v = min(0.18 + 0.27 * v, 1.15) * env
        amp_2 = 0.36 * amp_v          # 触地冲击的二次谐波
        amp_fwd = min(0.10 + 0.06 * v, 0.30) * env
        amp_lat = min(0.06 + 0.04 * v, 0.20) * env

        ph = w_step * t
        # 竖直：每步一次弹跳 + 触地冲击
        vert = amp_v * math.sin(ph) + amp_2 * math.sin(2 * ph + 0.9)
        # 前后：两次蹬地（每步一次推离 + 一次制动）
        fwd = amp_fwd * math.sin(2 * ph + math.pi / 3)
        # 左右：一个步幅周期一次（左右脚交替）
        lat = amp_lat * math.sin(ph / 2 + 0.5)

        # 陀螺仪：转向用轨迹真实曲率，姿态用步态振荡
        if prev_heading is not None:
            dh = heading - prev_heading
            while dh > math.pi:
                dh -= 2 * math.pi
            while dh < -math.pi:
                dh += 2 * math.pi
            target = dh * fs
            # 真人转身角速度上限约 230°/s（4 rad/s），手绘折线的直角必须先削掉
            target = max(-4.0, min(4.0, target))
            heading_rate = 0.88 * heading_rate + 0.12 * target
            heading_rate = max(-4.0, min(4.0, heading_rate))
        prev_heading = heading
        yaw = heading_rate
        roll = (0.9 * env * math.sin(ph)) if moving else 0.05 * math.sin(t)
        pitch = (0.6 * env * math.sin(2 * ph + 1.2)) if moving else 0.04 * math.sin(t * 0.7)

        # 传感器噪声
        na = lambda a=0.018: rng.gauss(0, a)
        ng = lambda a=0.05: rng.gauss(0, a)

        if mount == Mount.POCKET:
            # 屏幕朝内：重力落在 y 轴负方向，前后晃动最明显
            ax, ay, az = lat + na(), -1.0 + fwd + na(), vert * 0.55 + na()
            gx, gy, gz = (pitch + ng(), roll + ng(), yaw + ng())
        elif mount == Mount.ARM:
            # 臂包：屏幕朝外，z 轴承重的分量小一些，姿态更稳
            ax, ay, az = lat * 0.7 + na(), fwd * 0.7 + na(), 0.55 + vert * 0.85 + na()
            gx, gy, gz = (roll * 0.7 + ng(), pitch * 0.7 + ng(), yaw + ng())
        else:
            # 手持：屏幕朝上，重力在 z 轴
            ax, ay, az = lat + na(), fwd + na(), 1.0 + vert + na()
            gx, gy, gz = (roll + ng(), pitch + ng(), yaw + ng())

        data.append([round(t, 3), round(ax, 4), round(ay, 4), round(az, 4),
                     round(gx, 4), round(gy, 4), round(gz, 4)])

    moving_speeds = [s for s in speeds if s > 0.3]
    avg_v = sum(moving_speeds) / len(moving_speeds) if moving_speeds else 0.0
    dist = sum(core.haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
               for i in range(len(pts) - 1))
    meta = {
        "fs": fs,
        "mount": mount,
        "duration": round(total_t, 2),
        "distance_m": round(dist, 1),
        "stride_m": gait.stride_m,
        "cadence": gait.cadence,
        "step_hz": round(f_step, 3),
        "avg_mps": round(avg_v, 2),
        "avg_kmh": round(avg_v * 3.6, 1),
        "steps": int(round(dist / gait.stride_m)),
        "unit_accel": "g",
        "unit_gyro": "rad/s",
        "note": "由轨迹+步态推导，与 GPS 侧同一运动学；注入需越狱 tweak",
    }
    return {"meta": meta, "data": data}


def save_json(stream, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(stream, fh, ensure_ascii=False, separators=(",", ":"))
    return path


def save_csv(stream, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("t,ax,ay,az,gx,gy,gz\n")
        for row in stream["data"]:
            fh.write(",".join(str(x) for x in row) + "\n")
    return path


def summarize(stream):
    """自查：峰峰值、频谱主频是否等于步频"""
    data = stream["data"]
    if not data:
        return {}
    az = [r[3] for r in data]
    ax = [r[1] for r in data]
    gz = [r[6] for r in data]
    meta = stream["meta"]

    def peak_freq(series, fs):
        # 用零交叉估主频，避免引入 numpy 依赖
        s = series
        mean = sum(s) / len(s)
        s = [v - mean for v in s]
        cross = sum(1 for i in range(1, len(s)) if s[i - 1] < 0 <= s[i])
        dur = len(s) / fs
        return cross / dur if dur else 0.0

    return {
        "az_min": min(az),
        "az_max": max(az),
        "az_pp": max(az) - min(az),
        "ax_pp": max(ax) - min(ax),
        "gz_max": max(abs(x) for x in gz),
        "peak_hz": round(peak_freq(az, meta["fs"]), 3),
        "expect_hz": meta["step_hz"],
        "samples": len(data),
    }
