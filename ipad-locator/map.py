# -*- coding: utf-8 -*-
"""
可点击绘制轨迹的地图控件（纯 tkinter Canvas + 在线瓦片，无浏览器内核）

- 左键点击加点，左键拖拽平移，滚轮缩放，右键撤销上一点
- 支持三种底图：
    · 中文路网（高德）—— GCJ-02 坐标，内部自动换算成 WGS84
    · 卫星图（Esri）—— WGS84，和 iPad 的定位坐标系一致
    · 英文路网（Esri）—— WGS84
- 画出的轨迹点统一以 WGS84 存储，直接喂给设备
"""

import math
import os
import threading
import tkinter as tk
from tkinter import ttk

import core

TILE = 256
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiles")

CARD = "#FFFFFF"
BORDER = "#E2E6EC"
TEXT = "#1F2328"
SUB = "#6B7280"
ACCENT = "#2F6BFF"
START_C = "#16A34A"
END_C = "#DC2626"

LAYERS = {
    "高德 · 中文路网": {
        "key": "amap_road",
        "crs": "gcj",
        "url": "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        "sub": ["1", "2", "3", "4"],
        "attr": "© 高德地图",
    },
    "Esri · 卫星图": {
        "key": "esri_img",
        "crs": "wgs",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "© Esri, Maxar, Earthstar Geographics",
    },
    "Esri · 英文路网": {
        "key": "esri_street",
        "crs": "wgs",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        "attr": "© Esri, HERE, Garmin, OpenStreetMap",
    },
}


# 坐标换算统一放在 geo.py（WGS84 / GCJ-02 / BD-09 / BD09MC）
from geo import gcj02_to_wgs84, wgs84_to_gcj02  # noqa: E402


# ------------------------------------------------------------------- 瓦片数学
def deg2tile(lat, lon, z):
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(max(min(lat, 85.05112878), -85.05112878))
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y


def tile2deg(x, y, z):
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


class MapCanvas(tk.Frame):
    def __init__(self, master, ui_post, on_status=None):
        super().__init__(master, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.ui_post = ui_post
        self.on_status = on_status or (lambda *_: None)

        self.layer_name = "高德 · 中文路网"
        self.center = (39.908722, 116.397499)  # WGS84
        self.zoom = 16
        self.points = []          # WGS84 (lat, lon)
        self.closed = False
        self.target = None        # 定点页设的坐标，显示一个准星

        self._imgs = {}
        self._inflight = set()
        self._lock = threading.Lock()
        self._drag = None
        self._moved = False
        self._suppress_click = False

        self.canvas = tk.Canvas(self, bg="#EAEDF1", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", lambda e: self.undo())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

    # ------------------------------------------------------------ 对外接口
    @property
    def layer(self):
        return LAYERS[self.layer_name]

    def set_layer(self, name):
        if name in LAYERS:
            self.layer_name = name
            self.redraw()

    def set_target(self, lat, lon):
        self.target = (lat, lon)
        self.redraw()

    def set_center(self, lat, lon, zoom=None):
        self.center = (lat, lon)
        if zoom:
            self.zoom = zoom
        self.redraw()

    def fit_points(self):
        """把整条轨迹缩放到视野内：按投影后的像素包围盒逐个缩放级别试，取能装下的最大级别。"""
        if len(self.points) < 2:
            return
        lats = [p[0] for p in self.points]
        lons = [p[1] for p in self.points]
        self.center = ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
        cw = max(self.canvas.winfo_width(), 400)
        ch = max(self.canvas.winfo_height(), 300)
        best = 3
        for z in range(18, 2, -1):
            self.zoom = z
            pts = [self.screen(a, b) for a, b in self.points]
            w_span = max(p[0] for p in pts) - min(p[0] for p in pts)
            h_span = max(p[1] for p in pts) - min(p[1] for p in pts)
            if w_span <= cw * 0.80 and h_span <= ch * 0.72:
                best = z
                break
        self.zoom = best
        self.redraw()

    def add_point(self, lat, lon, redraw=True):
        self.points.append((lat, lon))
        if redraw:
            self.redraw()

    def undo(self):
        if self.points:
            self.points.pop()
            self.redraw()
            self.on_status(f"已撤销一个点，剩余 {len(self.points)} 个")

    def clear(self):
        self.points = []
        self.closed = False
        self.redraw()
        self.on_status("轨迹已清空")

    def total_meters(self):
        pts = list(self.points)
        if self.closed and len(pts) > 2:
            pts.append(pts[0])
        return sum(core.haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1))

    def path_for_play(self):
        pts = list(self.points)
        if self.closed and len(pts) > 2:
            pts.append(pts[0])
        return pts

    # ------------------------------------------------------------ 坐标变换
    def _to_layer(self, lat, lon):
        return wgs84_to_gcj02(lat, lon) if self.layer["crs"] == "gcj" else (lat, lon)

    def _from_layer(self, lat, lon):
        return gcj02_to_wgs84(lat, lon) if self.layer["crs"] == "gcj" else (lat, lon)

    def _world_px(self, lat, lon):
        la, lo = self._to_layer(lat, lon)
        tx, ty = deg2tile(la, lo, self.zoom)
        return tx * TILE, ty * TILE

    def _center_px(self):
        la, lo = self._to_layer(*self.center)
        tx, ty = deg2tile(la, lo, self.zoom)
        return tx * TILE, ty * TILE

    def screen(self, lat, lon):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        px, py = self._world_px(lat, lon)
        cx, cy = self._center_px()
        return px - cx + w / 2, py - cy + h / 2

    def unproject(self, sx, sy):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        cx, cy = self._center_px()
        gx, gy = cx + (sx - w / 2), cy + (sy - h / 2)
        lat, lon = tile2deg(gx / TILE, gy / TILE, self.zoom)
        return self._from_layer(lat, lon)

    # ---------------------------------------------------------------- 绘制
    def redraw(self):
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10 or h < 10:
            return
        c.delete("all")
        z = self.zoom
        cx, cy = self._center_px()
        left, top = cx - w / 2, cy - h / 2
        x0, x1 = int(math.floor(left / TILE)), int(math.floor((left + w) / TILE)) + 1
        y0, y1 = int(math.floor(top / TILE)), int(math.floor((top + h) / TILE)) + 1
        n = 2 ** z
        missing = 0
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                if not (0 <= tx < n and 0 <= ty < n):
                    continue
                sx, sy = tx * TILE - left, ty * TILE - top
                key = (self.layer["key"], z, tx, ty)
                img = self._imgs.get(key)
                if img is None:
                    img = self._load_cached(key)
                if img is not None:
                    c.create_image(sx, sy, image=img, anchor="nw")
                else:
                    missing += 1
                    c.create_rectangle(sx, sy, sx + TILE, sy + TILE, fill="#E6EAF0", outline="#DFE4EB")
                    self._request_tile(key, tx, ty)
        if missing:
            c.create_text(
                10, h - 26, text=f"正在加载地图瓦片… 剩 {missing}", anchor="w",
                fill=SUB, font=("Microsoft YaHei UI", 8),
            )

        self._draw_path()
        self._draw_target()
        self._draw_attr(w, h)

    def _draw_path(self):
        c = self.canvas
        pts = list(self.points)
        if self.closed and len(pts) > 2:
            pts.append(pts[0])
        if len(pts) >= 2:
            flat = []
            screen_pts = []
            for lat, lon in pts:
                x, y = self.screen(lat, lon)
                flat += [x, y]
                screen_pts.append((x, y))
            c.create_line(*flat, fill="#FFFFFF", width=7, joinstyle="round", capstyle="round")
            c.create_line(*flat, fill=ACCENT, width=3, joinstyle="round", capstyle="round")
            # 每段中点画个小箭头，一眼能看出跑的方向
            for (x1, y1), (x2, y2) in zip(screen_pts, screen_pts[1:]):
                dx, dy = x2 - x1, y2 - y1
                length = math.hypot(dx, dy)
                if length < 55:
                    continue
                ux, uy = dx / length, dy / length
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                s = 6.0
                c.create_polygon(
                    mx + ux * s, my + uy * s,
                    mx - uy * s * 0.62 - ux * s * 0.55, my + ux * s * 0.62 - uy * s * 0.55,
                    mx + uy * s * 0.62 - ux * s * 0.55, my - ux * s * 0.62 - uy * s * 0.55,
                    fill=ACCENT, outline="#FFFFFF", width=1,
                )
        if len(self.points) <= 400:
            for lat, lon in self.points:
                x, y = self.screen(lat, lon)
                c.create_oval(x - 3.5, y - 3.5, x + 3.5, y + 3.5, fill="#FFFFFF", outline=ACCENT, width=1.5)
        if self.points:
            for lat, lon, color, label, dy in (
                (self.points[0][0], self.points[0][1], START_C, "起", -20),
                (self.points[-1][0], self.points[-1][1], END_C, "终", -20),
            ):
                x, y = self.screen(lat, lon)
                c.create_oval(x - 9, y - 9, x + 9, y + 9, fill=color, outline="#FFFFFF", width=2.5)
                tid = c.create_text(x, y + dy, text=label, fill=color,
                                    font=("Microsoft YaHei UI", 9, "bold"))
                x1, y1, x2, y2 = c.bbox(tid)
                bg = c.create_polygon(x1 - 4, y1 - 1, x2 + 4, y1 - 1, x2 + 4, y2 + 1, x1 - 4, y2 + 1,
                                      fill="#FFFFFF", outline="", smooth=False)
                c.tag_lower(bg, tid)

    def _draw_target(self):
        if not self.target:
            return
        x, y = self.screen(*self.target)
        c = self.canvas
        c.create_line(x - 12, y, x + 12, y, fill="#1D4ED8", width=1)
        c.create_line(x, y - 12, x, y + 12, fill="#1D4ED8", width=1)
        c.create_oval(x - 5, y - 5, x + 5, y + 5, outline="#1D4ED8", width=2)

    def _draw_attr(self, w, h):
        c = self.canvas

        def chip(x, y, text, anchor="w", font_size=8, fg="#37414F"):
            """白底圆角小标签，压在地砖上也读得清"""
            f = ("Microsoft YaHei UI", font_size)
            tid = c.create_text(x, y, text=text, anchor=anchor, fill=fg, font=f)
            x1, y1, x2, y2 = c.bbox(tid)
            pad = 5
            rect = c.create_polygon(
                x1 - pad, y1 - 2, x2 + pad, y1 - 2, x2 + pad, y2 + 2, x1 - pad, y2 + 2,
                fill="#FFFFFF", outline="#DCE2EC", width=1, smooth=False,
            )
            c.tag_lower(rect, tid)
            return tid

        # 左上：底图/缩放/坐标
        chip(10, 12, f"{self.layer['attr'].split('©')[-1].strip()}  ·  缩放 {self.zoom}  ·  "
                     f"{self.center[0]:.5f}, {self.center[1]:.5f}", anchor="nw")

        # 左下：比例尺
        meters = 50
        px_per_meter = self._px_per_meter()
        while meters * px_per_meter > 200:
            meters //= 2
        while meters * px_per_meter < 40:
            meters *= 2
        length = max(meters * px_per_meter, 20)
        x0, y0 = 14, h - 20
        c.create_line(x0, y0, x0 + length, y0, fill="#2B3442", width=2)
        c.create_line(x0, y0 - 4, x0, y0 + 4, fill="#2B3442", width=2)
        c.create_line(x0 + length, y0 - 4, x0 + length, y0 + 4, fill="#2B3442", width=2)
        label = f"{meters} 米" if meters < 1000 else f"{meters / 1000:g} 公里"
        chip(x0 + length / 2, y0 - 11, label, anchor="s")

        # 右下：版权
        chip(w - 8, h - 10, self.layer["attr"], anchor="se", font_size=7, fg="#6B7688")

        self._draw_zoom_buttons(w)

    def _draw_zoom_buttons(self, w):
        c = self.canvas
        size = 30
        x1 = w - size - 12
        for i, (label, dy) in enumerate((("+", 0), ("−", 1))):
            y1 = 12 + dy * (size + 6)
            r = c.create_polygon(
                x1 + 6, y1, x1 + size - 6, y1, x1 + size, y1 + 6, x1 + size, y1 + size - 6,
                x1 + size - 6, y1 + size, x1 + 6, y1 + size, x1, y1 + size - 6, x1, y1 + 6,
                fill="#FFFFFF", outline="#D5DCE8", width=1, smooth=False,
            )
            t = c.create_text(x1 + size / 2, y1 + size / 2 - 1, text=label, fill="#2B3442",
                              font=("Microsoft YaHei UI", 15, "bold"))
            for item in (r, t):
                c.addtag_withtag("uibtn", item)
                c.tag_bind(item, "<Button-1>", lambda e, d=label: self._zoom_click(d))

    def _zoom_click(self, label):
        self._suppress_click = True
        if label == "+":
            self.apply_zoom(1, None, None)
        else:
            self.apply_zoom(-1, None, None)

    def apply_zoom(self, step, cx, cy):
        new_z = max(3, min(19, self.zoom + step))
        if new_z == self.zoom:
            return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        cx = w / 2 if cx is None else cx
        cy = h / 2 if cy is None else cy
        before = self.unproject(cx, cy)
        self.zoom = new_z
        after = self.unproject(cx, cy)
        self.center = (self.center[0] + (before[0] - after[0]), self.center[1] + (before[1] - after[1]))
        self.redraw()

    def _px_per_meter(self):
        lat = self.center[0]
        return TILE * (2 ** self.zoom) / (40075016.686 * math.cos(math.radians(lat))) if abs(lat) < 89 else 1.0

    # ---------------------------------------------------------------- 瓦片
    def _tile_path(self, key, z, x, y):
        d = os.path.join(CACHE, key, str(z))
        for ext in (".png", ".jpg"):
            p = os.path.join(d, f"{x}_{y}{ext}")
            if os.path.exists(p):
                return p
        return os.path.join(d, f"{x}_{y}.png")

    def _load_cached(self, key):
        _, z, x, y = key
        p = self._tile_path(key[0], z, x, y)
        if not os.path.exists(p):
            alt = p.replace(".png", ".jpg")
            if not os.path.exists(alt):
                return None
            p = alt
        try:
            img = tk.PhotoImage(file=p)
        except Exception:
            return None
        self._imgs[key] = img
        return img

    def _request_tile(self, key, tx, ty):
        with self._lock:
            if key in self._inflight:
                return
            self._inflight.add(key)
        threading.Thread(target=self._fetch_tile, args=(key, tx, ty), daemon=True).start()

    def _fetch_tile(self, key, tx, ty):
        name, z, _, _ = key
        layer = next((v for v in LAYERS.values() if v["key"] == name), None)
        try:
            if layer is None:
                return
            url = layer["url"].format(x=tx, y=ty, z=z, s=(layer.get("sub") or ["1"])[(tx + ty) % len(layer.get("sub") or ["1"])])
            data = None
            try:
                import requests

                r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 iPadLocator/1.0"})
                if r.status_code == 200 and r.content:
                    data = r.content
                    ext = ".png" if b"PNG" in data[:8] else ".jpg"
            except Exception:
                data = None
            if not data:
                return
            p = os.path.join(CACHE, name, str(z), f"{tx}_{ty}{ext}")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, p)
            self.ui_post(self.redraw)
        except Exception:
            pass
        finally:
            with self._lock:
                self._inflight.discard(key)

    # ---------------------------------------------------------------- 交互
    def _on_press(self, ev):
        cur = self.canvas.find_withtag("current")
        if cur and "uibtn" in self.canvas.gettags(cur[0]):
            self._drag = None
            self._moved = True
            return
        self._drag = (ev.x, ev.y)
        self._moved = False
        self.canvas.focus_set()

    def _on_drag(self, ev):
        if not self._drag:
            return
        dx, dy = ev.x - self._drag[0], ev.y - self._drag[1]
        if abs(dx) + abs(dy) > 3:
            self._moved = True
        if self._moved:
            cx, cy = self._center_px()
            lat, lon = tile2deg((cx - dx) / TILE, (cy - dy) / TILE, self.zoom)
            self.center = self._from_layer(lat, lon)
            self._drag = (ev.x, ev.y)
            self.redraw()

    def _on_release(self, ev):
        if self._suppress_click:
            self._suppress_click = False
            self._drag = None
            self._moved = False
            return
        if not self._moved and self._drag:
            lat, lon = self.unproject(ev.x, ev.y)
            self.add_point(lat, lon)
            self.on_status(f"已添加第 {len(self.points)} 个点：{lat:.6f}, {lon:.6f}")
        self._drag = None
        self._moved = False

    def _on_wheel(self, ev):
        self.apply_zoom(1 if ev.delta > 0 else -1, ev.x, ev.y)
