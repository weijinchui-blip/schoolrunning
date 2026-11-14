# -*- coding: utf-8 -*-
"""
iPad 定位器 —— 图形界面

用 USB 连上 iPad/iPhone，直接把系统 GPS 改到任意坐标。
底层走 Apple 官方的 DVT 开发者通道（等同 Xcode 的 Simulate Location）。
"""

import json
import os
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import cities
import core
import map as mapmod
import search
import sensor_gen
import sensor_push

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "settings.json")

# 色板：低饱和蓝作主色，中性灰做层次，绿/橙/红只用于状态
BG = "#F1F3F7"
CARD = "#FFFFFF"
BORDER = "#E4E8EF"
LINE = "#EAEDF3"
TEXT = "#171A1F"
SUB = "#667085"
MUTED = "#98A2B3"
ACCENT = "#2563EB"
ACCENT_D = "#1D4ED8"
ACCENT_SOFT = "#EEF4FF"
GHOST_BG = "#F7F9FC"
GHOST_HOVER = "#EDF1F8"
OK = "#0E9F6E"
OK_SOFT = "#E6F7F1"
WARN = "#B54708"
WARN_SOFT = "#FEF3E7"
ERR = "#DC2626"
ERR_SOFT = "#FDECEC"
LOG_BG = "#0E1626"
SEARCH_PH = "输入地名，例如：深圳湾公园"

FONT = "Microsoft YaHei UI"
MONO = "Consolas"


def enable_dpi_awareness():
    """让 Windows 别把窗口当位图拉伸，高分屏下字才不发虚。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system aware
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class Pill(tk.Canvas):
    """圆角状态胶囊：一个圆点 + 文字，比方块 Label 干净"""

    def __init__(self, master, text="未连接", fill="#E8EBF0", fg=SUB, bg=BG):
        super().__init__(master, bg=bg, highlightthickness=0, height=26, width=90)
        self._text, self._fill, self._fg = text, fill, fg
        self._font = tkfont.Font(family=FONT, size=9, weight="bold")
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def set(self, text, fill, fg):
        self._text, self._fill, self._fg = text, fill, fg
        self._draw()

    def _draw(self):
        self.delete("all")
        pad = 22
        w = max(self._font.measure(self._text) + pad + 12, 74)
        h = int(self["height"])
        if int(self["width"]) != w:
            self.configure(width=w)
        r = h / 2
        # 胶囊底：两个半圆 + 中间矩形
        self.create_oval(0, 0, h, h, fill=self._fill, outline="")
        self.create_oval(w - h, 0, w, h, fill=self._fill, outline="")
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=self._fill, outline="")
        self.create_oval(12, h / 2 - 3, 18, h / 2 + 3, fill=self._fg, outline="")
        self.create_text(24, h / 2, text=self._text, anchor="w", fill=self._fg, font=self._font)


class App(tk.Tk):
    def __init__(self):
        enable_dpi_awareness()
        super().__init__()
        self.title("iPad 定位器 · 系统定位模拟")

        try:
            self._scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except Exception:
            self._scale = 1.0
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = int(min(1120 * self._scale, sw - 60))
        h = int(min(920 * self._scale, sh - 120))
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max((sh - h) // 2 - 40, 8)}")
        self.minsize(int(1000 * min(self._scale, 1.2)), int(720 * min(self._scale, 1.2)))
        self.configure(bg=BG)

        self.engine = core.DeviceSession(log=self.log)
        self.walker = core.Walker(self.engine, log=self.log)
        self.devices = []
        self.favs = {}
        self._search_results = []
        self._search_after = None
        self._search_running = False
        self._log_open = True
        self.gait_cfg = {"stride": 1.05, "cadence": 170, "jitter": 2.5, "pause": 0.12}
        self._gait_seed = None
        self._logq = queue.Queue()
        self._uiq = queue.Queue()
        self._busy = False

        self.cfg = self._load_cfg()
        self._build_style()
        self._build_ui()
        self._restore_cfg()

        self.after(120, self._drain_log)
        self.after(500, self._tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(400, self.refresh_devices)

    # ---------------------------------------------------------------- 样式
    def _build_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT)
        st.configure("H1.TLabel", background=BG, foreground=TEXT, font=(FONT, 18, "bold"))
        st.configure("H2.TLabel", background=CARD, foreground=TEXT, font=(FONT, 12, "bold"))
        st.configure("Sub.TLabel", background=CARD, foreground=SUB, font=(FONT, 9))
        st.configure("Mini.TLabel", background=CARD, foreground=MUTED, font=(FONT, 8))
        st.configure("Field.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))

        st.configure("TButton", font=(FONT, 10), padding=(12, 6), borderwidth=0)
        st.configure(
            "Accent.TButton",
            font=(FONT, 10, "bold"),
            padding=(14, 8),
            background=ACCENT,
            foreground="#FFFFFF",
            borderwidth=0,
            focusthickness=0,
        )
        st.map(
            "Accent.TButton",
            background=[("disabled", "#A9C1F2"), ("pressed", ACCENT_D), ("active", ACCENT_D)],
            foreground=[("disabled", "#F3F6FC")],
        )
        st.configure(
            "Ghost.TButton",
            font=(FONT, 10),
            padding=(12, 6),
            background="#FBFCFE",
            foreground=TEXT,
            borderwidth=1,
            bordercolor="#D2DAE7",
            lightcolor="#FBFCFE",
            darkcolor="#FBFCFE",
            relief="solid",
        )
        st.map(
            "Ghost.TButton",
            background=[("pressed", "#EAF0F9"), ("active", "#F1F5FB")],
            bordercolor=[("active", "#B9C6DA"), ("pressed", "#A9B9D2")],
            foreground=[("disabled", "#AEB8C7")],
        )

        st.configure(
            "TEntry",
            padding=(8, 6),
            fieldbackground="#FBFCFE",
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            insertcolor=ACCENT,
        )
        st.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
        st.configure(
            "TCombobox",
            padding=(8, 5),
            fieldbackground="#FBFCFE",
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            arrowcolor=SUB,
        )
        st.map(
            "TCombobox",
            bordercolor=[("focus", ACCENT), ("hover", "#CFD8E6")],
            fieldbackground=[("readonly", "#FBFCFE")],
        )
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        st.configure(
            "TNotebook.Tab",
            padding=(18, 8),
            font=(FONT, 10),
            background=BG,
            foreground=SUB,
            borderwidth=0,
        )
        st.map(
            "TNotebook.Tab",
            background=[("selected", CARD)],
            foreground=[("selected", ACCENT)],
            expand=[("selected", (0, 0, 0, 0))],
        )
        st.configure(
            "Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor="#EDF1F7",
            borderwidth=0,
            thickness=6,
        )
        st.configure("TScrollbar", background="#D6DCE8", troughcolor=CARD, borderwidth=0, arrowsize=12)
        st.map("TScrollbar", background=[("active", "#BFC9DA")])

    def _card(self, parent, accent=None):
        """白卡片 + 细描边；accent 给顶部加一条彩色条，用来分区"""
        outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        if accent:
            tk.Frame(outer, bg=accent, height=3).pack(fill="x", side="top")
        return outer

    def _sep(self, parent, pady=0):
        """工具栏里的竖向分隔线"""
        f = tk.Frame(parent, bg=CARD)
        tk.Frame(f, bg=LINE, width=1, height=18).pack()
        f.pack(side="left", padx=8, pady=pady)
        return f

    def _field_label(self, parent, text):
        return tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=(FONT, 9))


    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # 状态栏先 pack，否则会被上面的 expand 区域挤成 0 高度
        bar = tk.Frame(self, bg="#FBFCFE", highlightbackground=BORDER, highlightthickness=0)
        tk.Frame(bar, bg=BORDER, height=1).pack(fill="x", side="top")
        line = tk.Frame(bar, bg="#FBFCFE")
        line.pack(fill="x")
        self.status_dot = tk.Canvas(line, width=10, height=10, bg="#FBFCFE", highlightthickness=0)
        self.status_dot.pack(side="left", padx=(16, 0))
        self._dot = self.status_dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="")
        self.status = tk.Label(
            line, text="就绪", bg="#FBFCFE", fg=SUB, font=(FONT, 9), anchor="w", pady=7
        )
        self.status.pack(side="left", padx=(8, 0))
        self.status_info = tk.Label(
            line, text="", bg="#FBFCFE", fg=MUTED, font=(FONT, 9), anchor="e", padx=16
        )
        self.status_info.pack(side="right")
        bar.pack(fill="x", side="bottom")

        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=16, pady=(14, 12))

        # 顶部标题
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        logo = tk.Canvas(head, width=38, height=38, bg=BG, highlightthickness=0)
        logo.pack(side="left", padx=(0, 10))
        logo.create_oval(1, 1, 37, 37, fill=ACCENT_SOFT, outline="")
        logo.create_oval(11, 9, 27, 25, outline=ACCENT, width=2)
        logo.create_oval(17, 15, 21, 19, fill=ACCENT, outline="")
        logo.create_line(19, 19, 19, 29, fill=ACCENT, width=2)

        tbox = tk.Frame(head, bg=BG)
        tbox.pack(side="left")
        tk.Label(tbox, text="iPad 定位器", bg=BG, fg=TEXT, font=(FONT, 18, "bold")).pack(anchor="w")
        tk.Label(
            tbox, text="USB 直连 · 系统级定位模拟 · Apple DVT 官方通道", bg=BG, fg=SUB, font=(FONT, 9)
        ).pack(anchor="w", pady=(1, 0))

        self.pill = Pill(head, "未连接", "#E8EBF0", SUB, bg=BG)
        self.pill.pack(side="right", pady=(6, 0))

        # 设备卡
        dev = self._card(root)
        dev.pack(fill="x", pady=(14, 0))
        inner = tk.Frame(dev, bg=CARD)
        inner.pack(fill="x", padx=16, pady=14)

        self._field_label(inner, "设备").grid(row=0, column=0, sticky="w")
        self.dev_combo = ttk.Combobox(inner, state="readonly", width=48, font=(FONT, 10))
        self.dev_combo.grid(row=1, column=0, sticky="we", pady=(5, 0))
        self.btn_refresh = ttk.Button(inner, text="刷新", style="Ghost.TButton", command=self.refresh_devices)
        self.btn_refresh.grid(row=1, column=1, padx=(8, 0), pady=(5, 0))
        self.btn_conn = ttk.Button(inner, text="连接设备", style="Accent.TButton", command=self.toggle_connect)
        self.btn_conn.grid(row=1, column=2, padx=(8, 0), pady=(5, 0))
        inner.columnconfigure(0, weight=1)
        self.dev_info = tk.Label(inner, text="正在检测设备…", bg=CARD, fg=SUB, font=(FONT, 9), anchor="w")
        self.dev_info.grid(row=2, column=0, columnspan=3, sticky="we", pady=(9, 0))

        # 搜索条（两页签共用）
        sbar = self._card(root)
        sbar.pack(fill="x", pady=(10, 0))
        r0 = tk.Frame(sbar, bg=CARD)
        r0.pack(fill="x", padx=16, pady=11)

        mag = tk.Canvas(r0, width=20, height=20, bg=CARD, highlightthickness=0)
        mag.pack(side="left", padx=(0, 8))
        mag.create_oval(2, 2, 13, 13, outline=ACCENT, width=2)
        mag.create_line(13, 13, 18, 18, fill=ACCENT, width=2)

        self.search_var = tk.StringVar(value=SEARCH_PH)
        self.search_combo = ttk.Combobox(
            r0, textvariable=self.search_var, font=(FONT, 10), width=44, foreground=MUTED
        )
        self.search_combo.pack(side="left")
        self.search_combo.bind("<Return>", lambda e: self.do_search())
        self.search_combo.bind("<FocusIn>", self._search_focus_in)
        self.search_combo.bind("<FocusOut>", self._search_focus_out)
        self.search_combo.bind("<<ComboboxSelected>>", self._search_pick)
        self.search_combo.bind("<KeyRelease>", self._search_typing)
        self.btn_search = ttk.Button(r0, text="搜索地名", style="Ghost.TButton", command=self.do_search)
        self.btn_search.pack(side="left", padx=(8, 0))
        self.btn_goto = ttk.Button(
            r0, text="设为定位", style="Accent.TButton", command=self._search_apply, state="disabled"
        )
        self.btn_goto.pack(side="left", padx=(8, 0))
        tk.Label(
            r0, text="百度地图 / OSM 数据 · 回车搜索 · 选中后可直接下发", bg=CARD, fg=MUTED, font=(FONT, 8)
        ).pack(side="right")

        # 主区：两个页签（定点 / 手绘轨迹）
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, pady=(10, 0))
        self.nb = nb
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        page1 = tk.Frame(nb, bg=BG)
        nb.add(page1, text="定点 / 自动移动")
        page2 = tk.Frame(nb, bg=BG)
        nb.add(page2, text="手绘轨迹")

        body = tk.Frame(page1, bg=BG)
        body.pack(fill="x", pady=(10, 0))
        body.columnconfigure(0, weight=1, uniform="c")
        body.columnconfigure(1, weight=1, uniform="c")

        self._build_target(body)
        self._build_move(body)
        # 卡片按内容高度收缩，剩余空间留给页签底部（比卡片里一大片空白好看）
        tk.Frame(page1, bg=BG).pack(fill="both", expand=True)
        self._build_map(page2)

        # 日志
        logc = self._card(root)
        logc.pack(fill="both", expand=False, pady=(10, 0))
        lh = tk.Frame(logc, bg=CARD)
        lh.pack(fill="x", padx=16, pady=(11, 6))
        tk.Label(lh, text="运行日志", bg=CARD, fg=TEXT, font=(FONT, 10, "bold")).pack(side="left")
        tk.Label(lh, text="  ✓ 成功 · ⚠ 注意 · ✗ 失败", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(
            side="left", pady=(2, 0)
        )
        ttk.Button(lh, text="清空", style="Ghost.TButton", command=self._clear_log).pack(side="right")
        self.btn_log = ttk.Button(lh, text="收起", style="Ghost.TButton", command=self._toggle_log)
        self.btn_log.pack(side="right", padx=(0, 6))

        wrap = tk.Frame(logc, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.log_wrap = wrap
        self.logbox = tk.Text(
            wrap,
            height=6,
            bg=LOG_BG,
            fg="#C7D2E3",
            insertbackground="#C7D2E3",
            relief="flat",
            font=(MONO, 9),
            wrap="word",
            padx=10,
            pady=8,
            spacing1=1,
            spacing3=1,
            borderwidth=0,
            highlightthickness=0,
        )
        self.logbox.tag_configure("ts", foreground="#5D6E8C")
        self.logbox.tag_configure("ok", foreground="#5DDBA0")
        self.logbox.tag_configure("warn", foreground="#F5C062")
        self.logbox.tag_configure("err", foreground="#F98A8A")
        self.logbox.tag_configure("dim", foreground="#8FA0B8")
        self.logbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, command=self.logbox.yview, orient="vertical")
        sb.pack(side="right", fill="y")
        self.logbox.configure(yscrollcommand=sb.set, state="disabled")

    def _build_target(self, parent):
        card = self._card(parent)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        f = tk.Frame(card, bg=CARD)
        f.pack(fill="both", expand=True, padx=16, pady=14)

        hdr = tk.Frame(f, bg=CARD)
        hdr.pack(anchor="w")
        tk.Frame(hdr, bg=ACCENT, width=4, height=16).pack(side="left", padx=(0, 9))
        tk.Label(hdr, text="目标位置", bg=CARD, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(
            f, text="填坐标或从预设里选，点「设定位置」立刻生效", bg=CARD, fg=SUB, font=(FONT, 9)
        ).pack(anchor="w", pady=(3, 12))

        grid = tk.Frame(f, bg=CARD)
        grid.pack(fill="x")
        self._field_label(grid, "纬度 Latitude").grid(row=0, column=0, sticky="w")
        self._field_label(grid, "经度 Longitude").grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.lat_var = tk.StringVar()
        self.lon_var = tk.StringVar()
        self.e_lat = ttk.Entry(grid, textvariable=self.lat_var, font=(MONO, 13), width=16)
        self.e_lon = ttk.Entry(grid, textvariable=self.lon_var, font=(MONO, 13), width=16)
        self.e_lat.grid(row=1, column=0, sticky="we", pady=(4, 0))
        self.e_lon.grid(row=1, column=1, sticky="we", padx=(10, 0), pady=(4, 0))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # 微调
        nudge = tk.Frame(f, bg=CARD)
        nudge.pack(fill="x", pady=(9, 0))
        for txt, dlat, dlon in (("北 ↑", 1, 0), ("南 ↓", -1, 0), ("西 ←", 0, -1), ("东 →", 0, 1)):
            ttk.Button(
                nudge, text=txt, style="Ghost.TButton", width=5,
                command=lambda a=dlat, b=dlon: self._nudge(a, b),
            ).pack(side="left", padx=(0, 5))
        tk.Label(nudge, text="每次约 22 米", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(
            side="left", padx=(6, 0)
        )

        tk.Frame(f, bg=LINE, height=1).pack(fill="x", pady=(14, 0))

        # 城市预设
        self._field_label(f, "城市 / 地标预设").pack(anchor="w", pady=(12, 3))
        rowc = tk.Frame(f, bg=CARD)
        rowc.pack(fill="x")
        self.city_combo = ttk.Combobox(
            rowc, values=list(cities.CITIES.keys()), state="readonly", font=(FONT, 10)
        )
        self.city_combo.pack(side="left", fill="x", expand=True)
        self.city_combo.set("选择城市或地标…")
        self.city_combo.bind("<<ComboboxSelected>>", self._city_pick)
        ttk.Button(rowc, text="收藏", style="Ghost.TButton", command=self._fav_add).pack(
            side="left", padx=(8, 0)
        )

        # 收藏
        self._field_label(f, "我的收藏").pack(anchor="w", pady=(10, 3))
        rowf = tk.Frame(f, bg=CARD)
        rowf.pack(fill="x")
        self.fav_combo = ttk.Combobox(rowf, state="readonly", font=(FONT, 10))
        self.fav_combo.pack(side="left", fill="x", expand=True)
        self.fav_combo.set("暂无收藏")
        self.fav_combo.bind("<<ComboboxSelected>>", self._fav_pick)
        ttk.Button(rowf, text="删除", style="Ghost.TButton", command=self._fav_del).pack(
            side="left", padx=(8, 0)
        )

        # 主按钮
        acts = tk.Frame(f, bg=CARD)
        acts.pack(fill="x", pady=(18, 0))
        self.btn_apply = ttk.Button(acts, text="设定位置", style="Accent.TButton", command=self.apply_location)
        self.btn_apply.pack(side="left", fill="x", expand=True)
        self.btn_clear = ttk.Button(
            acts, text="恢复真实定位", style="Ghost.TButton", command=self.clear_location
        )
        self.btn_clear.pack(side="left", padx=(8, 0))

        tk.Label(
            f,
            text="模拟仅在本工具运行期间有效；关掉程序或拔线，iPad 立即回到真实 GPS。",
            bg=CARD, fg=MUTED, font=(FONT, 8), wraplength=340, justify="left",
        ).pack(anchor="w", pady=(14, 0))

    def _build_move(self, parent):
        card = self._card(parent)
        card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        f = tk.Frame(card, bg=CARD)
        f.pack(fill="both", expand=True, padx=16, pady=14)

        hdr = tk.Frame(f, bg=CARD)
        hdr.pack(anchor="w")
        tk.Frame(hdr, bg="#10B981", width=4, height=16).pack(side="left", padx=(0, 9))
        tk.Label(hdr, text="让它动起来", bg=CARD, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(
            f, text="连续推送坐标，看起来像真的在走 / 在跑", bg=CARD, fg=SUB, font=(FONT, 9)
        ).pack(anchor="w", pady=(3, 12))

        self.mode = tk.StringVar(value="line")
        modes = tk.Frame(f, bg=CARD)
        modes.pack(anchor="w")
        for val, txt in (("line", "直线移动"), ("track", "轨迹回放"), ("jitter", "原地微抖")):
            tk.Radiobutton(
                modes, text=txt, value=val, variable=self.mode, bg=CARD, fg=TEXT,
                activebackground=CARD, activeforeground=ACCENT, selectcolor=CARD,
                font=(FONT, 10), highlightthickness=0, bd=0, command=self._mode_changed,
            ).pack(side="left", padx=(0, 14))

        # 模式对应的中间区（固定插槽，避免 pack 顺序错乱）
        self.slot = tk.Frame(f, bg=CARD)
        self.slot.pack(fill="x", pady=(12, 0))

        # 起终点
        self.frame_line = tk.Frame(self.slot, bg=CARD)
        self._field_label(self.frame_line, "起点（纬度 / 经度，留空 = 用左侧坐标）").pack(anchor="w")
        r1 = tk.Frame(self.frame_line, bg=CARD)
        r1.pack(fill="x", pady=(4, 0))
        self.s_lat = tk.StringVar()
        self.s_lon = tk.StringVar()
        ttk.Entry(r1, textvariable=self.s_lat, width=14, font=(MONO, 11)).pack(side="left")
        ttk.Entry(r1, textvariable=self.s_lon, width=14, font=(MONO, 11)).pack(side="left", padx=(7, 0))

        self._field_label(self.frame_line, "终点（纬度 / 经度）").pack(anchor="w", pady=(9, 0))
        r2 = tk.Frame(self.frame_line, bg=CARD)
        r2.pack(fill="x", pady=(4, 0))
        self.d_lat = tk.StringVar()
        self.d_lon = tk.StringVar()
        ttk.Entry(r2, textvariable=self.d_lat, width=14, font=(MONO, 11)).pack(side="left")
        ttk.Entry(r2, textvariable=self.d_lon, width=14, font=(MONO, 11)).pack(side="left", padx=(7, 0))

        # 轨迹文件
        self.frame_track = tk.Frame(self.slot, bg=CARD)
        self._field_label(self.frame_track, "轨迹文件（.gpx / .csv，两列 纬度,经度）").pack(anchor="w")
        r3 = tk.Frame(self.frame_track, bg=CARD)
        r3.pack(fill="x", pady=(4, 0))
        self.track_path = tk.StringVar()
        ttk.Entry(r3, textvariable=self.track_path, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(r3, text="选择", style="Ghost.TButton", command=self._pick_track).pack(side="left", padx=(8, 0))

        # 参数
        self.frame_param = tk.Frame(f, bg=CARD)
        self.frame_param.pack(fill="x", pady=(12, 0))
        p1 = tk.Frame(self.frame_param, bg=CARD)
        p1.pack(fill="x")
        self._field_label(p1, "速度 km/h").pack(side="left")
        self.speed = tk.StringVar(value="5")
        ttk.Combobox(
            p1, textvariable=self.speed, values=["1", "3", "5", "8", "10", "15", "20", "40", "60"], width=5
        ).pack(side="left", padx=(7, 14))
        self._field_label(p1, "推送间隔 秒").pack(side="left")
        self.interval = tk.StringVar(value="1")
        ttk.Combobox(
            p1, textvariable=self.interval, values=["0.5", "1", "2", "3", "5"], width=5
        ).pack(side="left", padx=(7, 0))

        self.jit_frame = tk.Frame(self.slot, bg=CARD)
        self._field_label(self.jit_frame, "抖动半径 米").pack(side="left")
        self.jit_r = tk.StringVar(value="3")
        ttk.Combobox(
            self.jit_frame, textvariable=self.jit_r, values=["1", "3", "5", "10", "20"], width=5
        ).pack(side="left", padx=(7, 0))

        # 动作
        acts = tk.Frame(f, bg=CARD)
        acts.pack(fill="x", pady=(18, 0))
        self.btn_walk = ttk.Button(acts, text="开始", style="Accent.TButton", command=self.start_walk)
        self.btn_walk.pack(side="left", fill="x", expand=True)
        self.btn_stop = ttk.Button(acts, text="停止", style="Ghost.TButton", command=self.stop_walk, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))

        self.prog = ttk.Progressbar(f, mode="determinate", maximum=100)
        self.prog.pack(fill="x", pady=(14, 0))
        self.move_hint = tk.Label(f, text="", bg=CARD, fg=SUB, font=(FONT, 9), anchor="w")
        self.move_hint.pack(anchor="w", pady=(7, 0))

        self._mode_changed()

    def _build_map(self, parent):
        bar = self._card(parent)
        bar.pack(fill="x")
        b = tk.Frame(bar, bg=CARD)
        b.pack(fill="x", padx=14, pady=9)

        r1 = tk.Frame(b, bg=CARD)
        r1.pack(fill="x")
        self.map_info = tk.Label(r1, text="点数 0 · 里程 0 米", bg=CARD, fg=TEXT, font=(MONO, 9))
        self.map_info.pack(side="right")

        self._field_label(r1, "底图").pack(side="left")
        self.map_layer = tk.StringVar(value="高德 · 中文路网")
        cb = ttk.Combobox(
            r1, textvariable=self.map_layer, values=list(mapmod.LAYERS.keys()),
            state="readonly", width=16, font=(FONT, 9),
        )
        cb.pack(side="left", padx=(7, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.mapw.set_layer(self.map_layer.get()))

        self._sep(r1)

        ttk.Button(r1, text="撤销上一点", style="Ghost.TButton",
                   command=lambda: self.mapw.undo()).pack(side="left", padx=(0, 5))
        ttk.Button(r1, text="清空", style="Ghost.TButton",
                   command=lambda: self.mapw.clear()).pack(side="left", padx=(0, 5))
        self.btn_loop = ttk.Button(r1, text="闭合路线", style="Ghost.TButton", command=self._toggle_loop)
        self.btn_loop.pack(side="left", padx=(0, 5))
        ttk.Button(r1, text="居中", style="Ghost.TButton",
                   command=lambda: self.mapw.fit_points()).pack(side="left")

        self._sep(r1)

        ttk.Button(r1, text="自检", style="Ghost.TButton",
                   command=self.self_check).pack(side="left", padx=(0, 5))
        ttk.Button(r1, text="传感器流", style="Ghost.TButton",
                   command=self.export_sensor).pack(side="left")

        r2 = tk.Frame(b, bg=CARD)
        r2.pack(fill="x", pady=(9, 0))
        self._field_label(r2, "速度 km/h").pack(side="left")
        self.map_speed = tk.StringVar(value="5")
        self.cb_speed = ttk.Combobox(
            r2, textvariable=self.map_speed, values=["1", "3", "5", "8", "10", "15", "20", "40"],
            width=5, font=(FONT, 9),
        )
        self.cb_speed.pack(side="left", padx=(7, 12))
        self._field_label(r2, "间隔 秒").pack(side="left")
        self.map_interval = tk.StringVar(value="1")
        ttk.Combobox(
            r2, textvariable=self.map_interval, values=["0.5", "1", "2", "3"],
            width=5, font=(FONT, 9),
        ).pack(side="left", padx=(7, 0))

        self._sep(r2)

        self.sim_on = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r2, text="拟真步态", variable=self.sim_on, bg=CARD, fg=TEXT,
            activebackground=CARD, activeforeground=ACCENT, selectcolor=CARD,
            font=(FONT, 10), highlightthickness=0, bd=0, command=self._sim_toggle,
        ).pack(side="left", padx=(0, 5))
        ttk.Button(r2, text="参数", style="Ghost.TButton", command=self.gait_dialog).pack(side="left")

        self._sep(r2)

        self.btn_play = ttk.Button(r2, text="沿轨迹播放", style="Accent.TButton", command=self.play_path)
        self.btn_play.pack(side="left")
        self.btn_pstop = ttk.Button(r2, text="停止", style="Ghost.TButton",
                                    command=self.stop_walk, state="disabled")
        self.btn_pstop.pack(side="left", padx=(5, 10))
        self.map_prog = ttk.Progressbar(r2, mode="determinate", maximum=100)
        self.map_prog.pack(side="left", fill="x", expand=True)

        hint = tk.Label(
            parent,
            text="左键加点 · 拖拽平移 · 滚轮缩放 · 右键撤销　|　画完点「沿轨迹播放」，iPad 沿这条线移动",
            bg=BG, fg=MUTED, font=(FONT, 8),
        )
        hint.pack(side="bottom", anchor="w", pady=(5, 0))

        self.mapw = mapmod.MapCanvas(parent, ui_post=self._uiq.put, on_status=self._map_status)
        self.mapw.pack(fill="both", expand=True, pady=(8, 0))
        self.mapw.set_layer(self.map_layer.get())
        try:
            la, lo = self.read_coords()
            self.mapw.set_center(la, lo, 16)
        except Exception:
            pass

    def _map_status(self, msg):
        self.set_status(msg, SUB)
        n = len(self.mapw.points)
        m = self.mapw.total_meters()
        self.map_info.configure(text=f"点数 {n} · 里程 {m:.0f} 米" if m < 1000 else f"点数 {n} · 里程 {m / 1000:.2f} 公里")

    def _toggle_loop(self):
        self.mapw.closed = not self.mapw.closed
        self.btn_loop.configure(text="取消闭合" if self.mapw.closed else "闭合路线")
        self.mapw.redraw()
        self._map_status("路线已闭合（终点连回起点）" if self.mapw.closed else "已取消闭合")

    def play_path(self):
        pts = self.mapw.path_for_play()
        if len(pts) < 2:
            messagebox.showwarning("轨迹太短", "先在地图上点几个点，画出要走的线。")
            return
        if not self.engine.connected:
            self.connect(then=self.play_path)
            return
        if self.walker.running:
            messagebox.showinfo("正在播放", "先点「停止」再重新播放。")
            return
        try:
            interval = max(float(self.map_interval.get()), 0.2)
        except ValueError:
            interval = 1.0
        try:
            if self.sim_on.get():
                gait = self._gait()
                if not gait.in_window():
                    if not messagebox.askyesno(
                        "配速不在统计窗口",
                        f"{gait.describe()}\n\n"
                        "校园跑只统计 1.5~6.5 m/s 区间内的速度，当前配速超出这个范围，"
                        "这段里程很可能不被计入。仍然继续？",
                    ):
                        return
                self.walker.walk_gait(pts, gait, interval=interval)
            else:
                try:
                    speed = float(self.map_speed.get())
                except ValueError:
                    speed = 5.0
                self.walker.walk_path(pts, speed_kmh=speed, interval=interval)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("播放失败", str(exc))
            return
        self.btn_play.configure(state="disabled")
        self.btn_pstop.configure(state="normal")
        self.btn_walk.configure(state="disabled")
        self.set_status("拟真播放中…" if self.sim_on.get() else "沿轨迹移动中…", ACCENT)

    # ---------------------------------------------------------------- 拟真步态
    def _gait(self, seed="keep"):
        c = self.gait_cfg
        if seed == "keep":
            seed = self._gait_seed
        return core.Gait(
            stride_m=c.get("stride", 1.05),
            cadence=c.get("cadence", 170),
            jitter_m=c.get("jitter", 2.5),
            pause_prob=c.get("pause", 0.12),
            seed=seed,
        )

    def _sim_toggle(self):
        try:
            self.cb_speed.configure(state="disabled" if self.sim_on.get() else "readonly")
        except Exception:
            pass
        if self.sim_on.get():
            g = self._gait()
            self.set_status(f"拟真步态：{g.describe()}", OK)
        else:
            self.set_status("匀速模式：按「速度 km/h」直接推送", SUB)
        self._refresh_status_info()

    def _refresh_status_info(self):
        """状态栏右侧：一眼看到设备 + 步态，不用去翻日志"""
        try:
            dev = "未连接"
            if self.engine.connected:
                dev = self.engine.info.get("name") or "已连接"
            parts = [f"设备 {dev}"]
            try:
                if self.sim_on.get():
                    g = self._gait()
                    parts.append(f"步态 {g.stride_m:g} × {g.cadence:g}")
                    parts.append(f"{g.speed * 3.6:.1f} km/h")
            except Exception:
                pass
            self._status_info("   ·   ".join(parts))
        except Exception:
            pass

    def gait_dialog(self):
        win = tk.Toplevel(self)
        win.title("拟真步态参数")
        win.configure(bg=CARD)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()

        f = tk.Frame(win, bg=CARD)
        f.pack(padx=18, pady=14)
        tk.Label(f, text="速度 = 步幅 × 步频", bg=CARD, fg=TEXT, font=(FONT, 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        tk.Label(
            f, text="步数和距离要对得上，配速要落在合理区间", bg=CARD, fg=SUB, font=(FONT, 9)
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))

        c = self.gait_cfg
        vars_ = {
            "stride": tk.StringVar(value=str(c.get("stride", 1.05))),
            "cadence": tk.StringVar(value=str(c.get("cadence", 170))),
            "jitter": tk.StringVar(value=str(c.get("jitter", 2.5))),
            "pause": tk.StringVar(value=str(c.get("pause", 0.12))),
        }
        rows = [
            ("步幅（米）", "stride", "0.75 走路 / 1.05 常规跑 / 1.20 大步跑"),
            ("步频（步/分）", "cadence", "110 走路 / 160~180 跑步"),
            ("GPS 噪声（米）", "jitter", "真实手机定位通常 2~6 米"),
            ("每公里停顿概率", "pause", "0 不停 / 0.12 约每 8 公里一次红灯"),
        ]
        for i, (label, key, tip) in enumerate(rows):
            tk.Label(f, text=label, bg=CARD, fg=SUB, font=(FONT, 9)).grid(
                row=2 + i * 2, column=0, sticky="w", pady=(6, 0)
            )
            ttk.Entry(f, textvariable=vars_[key], width=10, font=(FONT, 10)).grid(
                row=2 + i * 2, column=1, sticky="w", padx=(10, 12), pady=(6, 0)
            )
            tk.Label(f, text=tip, bg=CARD, fg="#9AA3AF", font=(FONT, 8)).grid(
                row=2 + i * 2, column=2, sticky="w", pady=(6, 0)
            )

        preview = tk.Label(f, text="", bg=CARD, fg=OK, font=(FONT, 10, "bold"))
        preview.grid(row=11, column=0, columnspan=3, sticky="w", pady=(14, 0))

        mount_names = {"hand": "手持（屏幕朝上）", "pocket": "揣兜（屏幕朝内）", "arm": "臂包（屏幕朝外）"}
        mount_var = tk.StringVar(value=mount_names.get(c.get("mount", "hand"), "手持（屏幕朝上）"))
        tk.Label(f, text="设备固定方式", bg=CARD, fg=SUB, font=(FONT, 9)).grid(
            row=10, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Combobox(
            f, textvariable=mount_var, state="readonly", width=16, font=(FONT, 9),
            values=list(mount_names.values()),
        ).grid(row=10, column=1, sticky="w", padx=(10, 12), pady=(6, 0))
        tk.Label(f, text="影响重力落在哪个轴、哪个方向晃得最厉害", bg=CARD, fg="#9AA3AF",
                 font=(FONT, 8)).grid(row=10, column=2, sticky="w", pady=(6, 0))

        def refresh(*_a):
            try:
                g = core.Gait(
                    float(vars_["stride"].get()), float(vars_["cadence"].get()),
                    float(vars_["jitter"].get()), float(vars_["pause"].get()),
                )
            except ValueError:
                preview.configure(text="填的数字看不懂", fg=ERR)
                return
            ok = g.in_window()
            preview.configure(
                text=g.describe()
                + ("\n在 1.5~6.5 m/s 统计窗口内 ✓" if ok else "\n⚠ 超出 1.5~6.5 m/s，可能不计里程"),
                fg=OK if ok else WARN,
            )

        for v in vars_.values():
            v.trace_add("write", refresh)
        refresh()

        presets = tk.Frame(f, bg=CARD)
        presets.grid(row=12, column=0, columnspan=3, sticky="w", pady=(12, 0))
        tk.Label(presets, text="常用：", bg=CARD, fg=SUB, font=(FONT, 9)).pack(side="left")
        for name, s, cd in (("健走", 0.78, 118), ("慢跑", 0.95, 155), ("常规跑", 1.05, 170), ("快跑", 1.18, 182)):
            ttk.Button(
                presets, text=name, style="Ghost.TButton",
                command=lambda s=s, cd=cd: (vars_["stride"].set(str(s)), vars_["cadence"].set(str(cd))),
            ).pack(side="left", padx=(4, 0))

        btns = tk.Frame(f, bg=CARD)
        btns.grid(row=13, column=0, columnspan=3, sticky="e", pady=(16, 0))

        def save():
            try:
                g = core.Gait(
                    float(vars_["stride"].get()), float(vars_["cadence"].get()),
                    float(vars_["jitter"].get()), float(vars_["pause"].get()),
                )
            except ValueError:
                messagebox.showwarning("填错了", "四个参数都要是数字。", parent=win)
                return
            self.gait_cfg = {
                "stride": g.stride_m, "cadence": g.cadence,
                "jitter": g.jitter_m, "pause": g.pause_prob,
                "mount": {v: k for k, v in {
                    "hand": "手持（屏幕朝上）", "pocket": "揣兜（屏幕朝内）", "arm": "臂包（屏幕朝外）",
                }.items()}.get(mount_var.get(), "hand"),
            }
            self._save_cfg()
            self.set_status(g.describe(), SUB)
            self.log("拟真参数：" + g.describe())
            win.destroy()

        ttk.Button(btns, text="取消", style="Ghost.TButton", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="保存", style="Accent.TButton", command=save).pack(side="right", padx=(0, 8))
        win.update_idletasks()
        win.geometry(f"+{self.winfo_rootx() + 200}+{self.winfo_rooty() + 160}")

    def self_check(self):
        """按校园跑服务端的口径，把接下来要发的轨迹先跑一遍并统计。"""
        import random as _rnd

        pts = self.mapw.path_for_play()
        if len(pts) < 2:
            messagebox.showwarning("轨迹太短", "先在地图上画一条线（至少 2 个点）再自检。")
            return
        try:
            interval = max(float(self.map_interval.get()), 0.2)
        except ValueError:
            interval = 1.0
        total = sum(
            core.haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
            for i in range(len(pts) - 1)
        )
        seed = _rnd.randrange(1, 1 << 30)
        gait = self._gait(seed=seed)
        samples = [(t, la, lo) for t, la, lo, _v, _s in core.gait_samples(pts, gait, interval)]
        st = core.analyze_track(samples, total, gait)
        if not st:
            return
        self._gait_seed = seed

        ok = st["in_range"] >= 0.85 and st["jumps"] == 0 and gait.in_window()
        report = (
            "轨迹自检（按校园跑服务端口径）\n"
            f"{'─' * 36}\n"
            f"轨迹：{len(pts)} 个点，全长 {total:.0f} 米\n"
            f"模拟耗时：{st['duration'] / 60:.1f} 分钟，上报 {st['n']} 个点（{interval:g} 秒 1 点）\n"
            f"步态：步幅 {gait.stride_m:g} m × 步频 {gait.cadence:g} 步/分 → {gait.speed:.2f} m/s\n"
            f"平均速度：{st['avg_mps']:.2f} m/s（{st['avg_kmh']:.1f} km/h，配速 {st['avg_pace']:.2f}）\n"
            f"瞬时速度范围：{st['min_mps']:.2f} ~ {st['max_mps']:.2f} m/s\n"
            f"落在 1.5~6.5 m/s 的区间占比：{st['in_range'] * 100:.1f}%\n"
            f"瞬移点（>12 m/s）：{st['jumps']} 个\n"
            f"步数：约 {st['steps']} 步（与距离自洽）\n"
            f"{'─' * 36}\n"
            + ("结论：轨迹层面没有明显异常，可以播。\n" if ok else "结论：有指标不正常，建议调参数或换路线。\n")
            + f"（本次用的种子 {seed}，播放时会复现这条轨迹）\n\n"
            "能控制的：轨迹形状、速度曲线、步频配速、定位漂移、停顿。\n"
            "控制不了的：手机的陀螺仪/加速度是硬件数据，电脑端没有接口能伪造。"
            "如果对方逐秒比对运动传感器，静止放着的设备会对不上，这一项本工具做不到。"
        )
        self.log(
            f"自检：{total:.0f} 米 / {st['avg_kmh']:.1f} km/h / 配速 {st['avg_pace']:.2f} / "
            f"区间命中 {st['in_range'] * 100:.0f}% / 瞬移 {st['jumps']}"
        )
        messagebox.showinfo("自检结果", report)

    def export_sensor(self):
        """按当前轨迹 + 步态生成 IMU 流，并推到设备上。"""
        pts = self.mapw.path_for_play()
        if len(pts) < 2:
            messagebox.showwarning("轨迹太短", "先在地图上画一条线，传感器流是按轨迹推的。")
            return
        gait = self._gait()
        mount = self.gait_cfg.get("mount", "hand")
        try:
            stream = sensor_gen.generate(pts, gait, mount=mount, fs=50, seed=gait.seed)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("生成失败", str(exc))
            return
        st = sensor_gen.summarize(stream)
        meta = stream["meta"]
        size_mb = len(str(stream["data"])) / 1024 / 1024
        if size_mb > 35 and not messagebox.askyesno(
            "文件比较大",
            f"这条轨迹要生成 {st['samples']} 个采样点（约 {size_mb:.0f} MB），推送会慢一点。继续？",
        ):
            return

        report = (
            "传感器数据流（已按轨迹 + 步态推导）\n"
            f"{'─' * 36}\n"
            f"采样：{meta['fs']} Hz，{st['samples']} 个点，{meta['duration'] / 60:.1f} 分钟\n"
            f"步态：步幅 {meta['stride_m']:g} m × 步频 {meta['cadence']:g} 步/分\n"
            f"竖直加速度：{st['az_min']:.2f} ~ {st['az_max']:.2f} g（峰峰 {st['az_pp']:.2f} g）\n"
            f"水平晃动峰峰：{st['ax_pp']:.2f} g\n"
            f"最大角速度：{st['gz_max']:.2f} rad/s\n"
            f"主频实测 {st['peak_hz']:.3f} Hz ＝ 步频 {st['expect_hz']:.3f} Hz ✓\n"
            f"固定方式：{ {'hand': '手持', 'pocket': '揣兜', 'arm': '臂包'}.get(meta['mount'], meta['mount']) }\n"
            f"{'─' * 36}\n"
            "数据已推到设备：/var/mobile/Media/sensorspoof.json\n\n"
            "但这一步只是「把数据放到了设备上」。\n"
            "要让 App（微信 / 小程序）真的读到这些读数，需要越狱 + 安装 sensor_spoof 插件，\n"
            "插件会 hook CoreMotion，按 50 Hz 把这份数据回放给它。\n\n"
            "为什么电脑端做不到：我枚举了这台 iPad 的 59 个 RSD 服务，没有任何一个能写传感器读数；\n"
            "库里的 accelerometer/gyroscope 字样只是「这台设备有没有这个硬件」的声明，诊断接口是只读的。\n"
            "源码在 sensor_spoof/ 目录，编译和上机需要你自己在越狱设备上验证。"
        )
        self.log(
            f"生成传感器流：{st['samples']} 点 / {meta['duration']:.0f}s / "
            f"主频 {st['peak_hz']:.2f} Hz / 峰峰 {st['az_pp']:.2f} g"
        )
        self.set_status("正在推送到设备…", ACCENT)

        def ok(path):
            self.set_status("传感器流已推到设备", OK)
            self.log(f"✓ 已写入设备 /var/mobile/Media/sensorspoof.json（本地副本 {path}）")
            messagebox.showinfo("传感器流", report)

        def err(exc):
            self.set_status(f"推送失败：{exc}", ERR)
            messagebox.showerror("推送失败", f"{exc}\n\n本地文件已生成，设备可能没连上。")

        self.bg(sensor_push.push_stream, stream, self._current_udid(), on_ok=ok, on_err=err)

    # -------------------------------------------------------------- 地名搜索
    def _baidu_ak(self):
        ak = (self.cfg.get("baidu_ak") or os.environ.get("BAIDU_AK") or "").strip()
        return ak or None

    def do_search(self, keyword=None, quiet=False):
        q = (keyword if keyword is not None else self.search_var.get()).strip()
        if not q or q == SEARCH_PH or self._search_running:
            return
        self._search_running = True
        self.btn_search.configure(state="disabled", text="搜索中")
        self.bg(
            search.search_places,
            q,
            8,
            self._baidu_ak(),
            on_ok=lambda res: self._search_done(q, res),
            on_err=self._search_fail,
        )

    def _search_focus_in(self, _evt=None):
        if self.search_var.get() == SEARCH_PH:
            self.search_var.set("")
            try:
                self.search_combo.configure(foreground=TEXT)
            except Exception:
                pass

    def _search_focus_out(self, _evt=None):
        if not self.search_var.get().strip():
            self.search_var.set(SEARCH_PH)
            try:
                self.search_combo.configure(foreground=MUTED)
            except Exception:
                pass

    def _search_typing(self, ev):
        if ev.keysym in ("Return", "Up", "Down", "Escape", "Tab", "Left", "Right"):
            return
        if self._search_after:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
            self._search_after = None
        q = self.search_var.get().strip()
        if len(q) < 2:
            return
        self._search_after = self.after(650, lambda: self.do_search(q, quiet=True))

    def _search_done(self, q, results):
        self._search_running = False
        self._search_after = None
        self.btn_search.configure(state="normal", text="搜索")
        self._search_results = list(results or [])
        if not self._search_results:
            self.btn_goto.configure(state="disabled")
            self.search_combo["values"] = []
            self.set_status(f"没有搜到「{q}」", WARN)
            self.log(f"搜索「{q}」：无结果")
            return
        self.search_combo["values"] = [search.label_of(r) for r in self._search_results]
        self.search_combo.current(0)
        self.btn_goto.configure(state="normal")
        self.log(f"搜索「{q}」→ {len(self._search_results)} 条（来源 {self._search_results[0].get('src', '?')}）")
        self._apply_search_index(0, jump=False, log_it=False)

    def _search_fail(self, exc):
        self._search_running = False
        self._search_after = None
        self.btn_search.configure(state="normal", text="搜索")
        self.btn_goto.configure(state="disabled")
        self.search_combo["values"] = []
        self.set_status(f"搜索失败：{exc}", ERR)

    def _search_pick(self, _evt=None):
        i = self.search_combo.current()
        if 0 <= i < len(self._search_results):
            self._apply_search_index(i, jump=False)

    def _search_apply(self):
        i = self.search_combo.current()
        if not (0 <= i < len(self._search_results)):
            i = 0
        if not self._search_results:
            messagebox.showinfo("先搜索", "在上面输入地名，选一条结果后再点「设为定位」。")
            return
        self._apply_search_index(i, jump=True)

    def _apply_search_index(self, i, jump=False, log_it=True):
        if not (0 <= i < len(self._search_results)):
            return
        r = self._search_results[i]
        lat, lon = r["lat"], r["lon"]
        self.mapw.set_center(lat, lon, 17)
        self.mapw.set_target(lat, lon)
        self.lat_var.set(f"{lat:.6f}")
        self.lon_var.set(f"{lon:.6f}")
        self.set_status(f"{r['name']}  {lat:.6f}, {lon:.6f}", OK)
        if log_it:
            self.log(f"选中：{r['name']}  {r['addr']}  →  {lat:.6f}, {lon:.6f}（{r.get('src')}）")
        if not jump:
            return
        if not self.engine.connected:
            self.connect(then=lambda: self._apply_search_index(i, jump=True, log_it=False))
            return
        name = r["name"]

        def ok(_r):
            self.log(f"✓ 已定位到 {name}（{lat:.6f}, {lon:.6f}）")
            self.set_status(f"已定位到 {name}", OK)

        self.bg(self.engine.set_location, lat, lon, on_ok=ok)
        self._save_cfg()

    # -------------------------------------------------------------- 日志/调度
    def log(self, msg: str) -> None:
        self._logq.put(msg)

    def _drain_log(self):
        # 后台线程的任务结果统一走队列回到主线程执行（tkinter 非线程安全）
        try:
            while True:
                cb = self._uiq.get_nowait()
                try:
                    cb()
                except Exception as exc:  # noqa: BLE001
                    self.log(f"界面回调出错：{exc}")
        except queue.Empty:
            pass
        try:
            while True:
                msg = self._logq.get_nowait()
                import time as _t

                stamp = _t.strftime("%H:%M:%S")
                tag = "dim"
                body = msg
                if msg.startswith("✓"):
                    tag, body = "ok", msg[1:].strip()
                elif msg.startswith("✗"):
                    tag, body = "err", msg[1:].strip()
                elif msg.startswith("⚠"):
                    tag, body = "warn", msg[1:].strip()
                self.logbox.configure(state="normal")
                self.logbox.insert("end", f"{stamp}  ", ("ts",))
                self.logbox.insert("end", body + "\n", (tag,))
                self.logbox.see("end")
                self.logbox.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._drain_log)

    def _clear_log(self):
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")

    def _toggle_log(self):
        self._set_log(not self._log_open)

    def _set_log(self, open_it: bool):
        if open_it and not self._log_open:
            self.log_wrap.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        elif not open_it and self._log_open:
            self.log_wrap.pack_forget()
        self._log_open = open_it
        self.btn_log.configure(text="收起" if open_it else "展开")

    def _on_tab_changed(self, _evt=None):
        # 画轨迹时把日志收起来，让地图占满；回到定点页再展开
        try:
            idx = self.nb.index(self.nb.select())
        except Exception:
            return
        self._set_log(idx == 0)

    def set_status(self, text: str, color: str = SUB):
        self.status.configure(text=text, fg=color)
        try:
            dot = {OK: OK, ERR: ERR, WARN: WARN}.get(color, MUTED)
            self.status_dot.itemconfigure(self._dot, fill=dot)
        except Exception:
            pass

    def _status_info(self, text=""):
        try:
            self.status_info.configure(text=text)
        except Exception:
            pass

    def _set_pill(self, text: str, bg: str, fg: str):
        try:
            self.pill.set(text, bg, fg)
        except Exception:
            self.pill.configure(text=text)

    def bg(self, fn, *args, on_ok=None, on_err=None):
        def run():
            try:
                r = fn(*args)
            except Exception as exc:  # noqa: BLE001
                msg = f"{type(exc).__name__}: {exc}"
                self.log(f"✗ {msg}")

                def err_ui():
                    self.set_status(msg, ERR)
                    if on_err:
                        on_err(exc)

                self._uiq.put(err_ui)
                return

            def ok_ui():
                if on_ok:
                    on_ok(r)

            self._uiq.put(ok_ui)

        threading.Thread(target=run, daemon=True).start()

    # ---------------------------------------------------------------- 设备
    def refresh_devices(self):
        self.btn_refresh.configure(state="disabled")
        self.dev_info.configure(text="正在检测设备…")
        self.bg(self.engine.list_devices, on_ok=self._devices_ready, on_err=lambda e: self._devices_failed())

    def _devices_ready(self, devices):
        self.btn_refresh.configure(state="normal")
        self.devices = devices or []
        if not self.devices:
            self.dev_combo["values"] = []
            self.dev_combo.set("")
            self.dev_info.configure(text="没有检测到设备：请用数据线连接 iPad，解锁屏幕并点「信任」", fg=ERR)
            return
        labels = [
            f"{d['name']}  ·  {d.get('model', '')}  ·  iPadOS {d.get('ios', '?')}  ·  {d['connection']}"
            for d in self.devices
        ]
        changed = labels != list(self.dev_combo["values"])
        self.dev_combo["values"] = labels
        if self.dev_combo.get() not in labels:
            self.dev_combo.current(0)
        if self.engine.connected:
            info = self.engine.info
            self.dev_info.configure(
                text=f"{info.get('name')}  ·  {info.get('model')}  ·  iPadOS {info.get('ios')}  ·  通道就绪",
                fg=OK,
            )
        else:
            d = self.devices[0]
            self.dev_info.configure(
                text=f"已发现 {len(self.devices)} 台设备   UDID {d['udid'][:16]}…", fg=SUB
            )
        if changed:
            d = self.devices[0]
            self.log(f"发现设备：{d['name']} ({d.get('model')} / iPadOS {d.get('ios')})")

    def _devices_failed(self):
        self.btn_refresh.configure(state="normal")
        self.dev_info.configure(text="检测设备失败，确认 iTunes / Apple 设备服务已安装并在运行", fg=ERR)

    def _current_udid(self):
        idx = self.dev_combo.current()
        if 0 <= idx < len(self.devices):
            return self.devices[idx]["udid"]
        return None

    def toggle_connect(self):
        if self.engine.connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self, then=None):
        udid = self._current_udid()
        if udid is None:
            messagebox.showwarning("没有设备", "先把 iPad 用数据线连上电脑，解锁并点「信任」。")
            return
        self.btn_conn.configure(state="disabled", text="连接中…")
        self._set_pill("连接中", "#FEF3C7", WARN)

        def ok(_r):
            self.btn_conn.configure(state="normal", text="断开")
            self._set_pill("已连接", "#DCFCE7", OK)
            info = self.engine.info
            self.dev_info.configure(
                text=f"{info.get('name')}  ·  {info.get('model')}  ·  iPadOS {info.get('ios')}  ·  通道就绪",
                fg=OK,
            )
            self.set_status("已连接，可以设定坐标了", OK)
            self._refresh_status_info()
            try:
                la, lo = self.read_coords()
                self.mapw.set_center(la, lo)
                self.mapw.set_target(la, lo)
            except Exception:
                pass
            if then:
                then()

        def err(_e):
            self.btn_conn.configure(state="normal", text="连接设备")
            self._set_pill("未连接", "#E8EBF0", SUB)
            messagebox.showerror(
                "连接失败",
                "连不上设备。逐项检查：\n"
                "1) 数据线是不是只能充电的线\n"
                "2) iPad 是否解锁并点了「信任此电脑」\n"
                "3) 设置 → 隐私与安全性 → 开发者模式 是否已打开（开了要重启一次）\n\n"
                "详细信息看下方日志。",
            )

        self.bg(self.engine.connect, udid, on_ok=ok, on_err=err)

    def disconnect(self):
        self.stop_walk(silent=True)
        self.btn_conn.configure(state="disabled")
        self.bg(
            self.engine.disconnect,
            on_ok=lambda _r: (
                self.btn_conn.configure(state="normal", text="连接设备"),
                self._set_pill("未连接", "#E8EBF0", SUB),
                self.set_status("已断开，设备恢复真实定位", SUB),
                self._refresh_status_info(),
            ),
            on_err=lambda _e: self.btn_conn.configure(state="normal", text="断开"),
        )

    # ---------------------------------------------------------------- 坐标
    def read_coords(self):
        try:
            lat = float(self.lat_var.get().strip())
            lon = float(self.lon_var.get().strip())
        except ValueError:
            raise ValueError("纬度/经度要填数字，例如 39.908722 和 116.397499")
        if not -90 <= lat <= 90:
            raise ValueError("纬度范围是 -90 ~ 90")
        if not -180 <= lon <= 180:
            raise ValueError("经度范围是 -180 ~ 180")
        return lat, lon

    def _nudge(self, dlat, dlon):
        try:
            lat, lon = self.read_coords()
        except ValueError:
            lat, lon = 39.908722, 116.397499
        self.lat_var.set(f"{lat + dlat * 0.0002:.6f}")
        self.lon_var.set(f"{lon + dlon * 0.0002:.6f}")

    def _city_pick(self, _evt=None):
        name = self.city_combo.get()
        if name in cities.CITIES:
            lat, lon = cities.CITIES[name]
            self.lat_var.set(f"{lat:.6f}")
            self.lon_var.set(f"{lon:.6f}")
            self.set_status(f"已填入 {name}", SUB)

    def apply_location(self):
        try:
            lat, lon = self.read_coords()
        except ValueError as exc:
            messagebox.showwarning("坐标不对", str(exc))
            return
        if not self.engine.connected:
            self.log("还没连接，先自动连接设备…")
            self.connect(then=lambda: self.apply_location())
            return
        self.btn_apply.configure(state="disabled", text="发送中…")

        def ok(_r):
            self.btn_apply.configure(state="normal", text="设定位置")
            self.set_status(f"定位已改到 {lat:.6f}, {lon:.6f}", OK)
            self.log(f"✓ 定位已设为 {lat:.6f}, {lon:.6f}")
            try:
                self.mapw.set_target(lat, lon)
            except Exception:
                pass
            self._save_cfg()

        def err(_e):
            self.btn_apply.configure(state="normal", text="设定位置")

        self.bg(self.engine.set_location, lat, lon, on_ok=ok, on_err=err)

    def clear_location(self):
        if not self.engine.connected:
            self.set_status("还没连接设备", WARN)
            return
        self.bg(
            self.engine.clear_location,
            on_ok=lambda _r: (
                self.set_status("已恢复真实定位", OK),
                self.log("✓ 已撤销模拟，设备回到真实 GPS"),
            ),
        )

    # ---------------------------------------------------------------- 移动
    def _mode_changed(self):
        mode = self.mode.get()
        for w in (self.frame_line, self.frame_track, self.jit_frame):
            w.pack_forget()
        if mode == "line":
            self.frame_line.pack(fill="x")
            self.move_hint.configure(text="起点留空 = 用左侧坐标；步行填 5，跑步填 10", fg=SUB)
        elif mode == "track":
            self.frame_track.pack(fill="x")
            self.move_hint.configure(text="按文件里的点顺序逐个推送", fg=SUB)
        else:
            self.jit_frame.pack(fill="x")
            self.move_hint.configure(text="在设定坐标附近小幅随机跳动，避免长时间同一坐标", fg=SUB)

    def _pick_track(self):
        path = filedialog.askopenfilename(
            title="选择轨迹文件",
            filetypes=[("轨迹文件", "*.gpx *.csv"), ("GPX", "*.gpx"), ("CSV", "*.csv")],
        )
        if path:
            self.track_path.set(path)

    def start_walk(self):
        if not self.engine.connected:
            self.connect(then=self.start_walk)
            return
        mode = self.mode.get()
        try:
            interval = max(float(self.interval.get()), 0.2)
        except ValueError:
            interval = 1.0
        try:
            if mode == "line":
                if self.s_lat.get().strip() and self.s_lon.get().strip():
                    try:
                        sl = (float(self.s_lat.get()), float(self.s_lon.get()))
                    except ValueError:
                        messagebox.showwarning("起点不对", "起点要填数字，或直接留空用左侧坐标")
                        return
                else:
                    sl = self.read_coords()
                if not (self.d_lat.get().strip() and self.d_lon.get().strip()):
                    messagebox.showwarning("缺少终点", "直线移动要填终点坐标（纬度、经度）")
                    return
                try:
                    dl = (float(self.d_lat.get()), float(self.d_lon.get()))
                except ValueError:
                    messagebox.showwarning("终点不对", "终点要填数字，例如 39.920000 和 116.400000")
                    return
                try:
                    speed = float(self.speed.get())
                except ValueError:
                    speed = 5.0
                self.walker.walk_line(sl, dl, speed_kmh=speed, interval=interval)
                self.move_hint.configure(text=f"从 {sl[0]:.5f},{sl[1]:.5f} 走向 {dl[0]:.5f},{dl[1]:.5f}", fg=OK)
            elif mode == "track":
                path = self.track_path.get().strip()
                if not path:
                    messagebox.showwarning("没选文件", "先选一个 .gpx 或 .csv 轨迹文件")
                    return
                pts = core.parse_gpx(path) if path.lower().endswith(".gpx") else core.parse_csv_points(path)
                if len(pts) < 2:
                    messagebox.showwarning("文件里没有坐标", "这个文件没解析出有效坐标点")
                    return
                self.walker.walk_points(pts, interval=interval)
                self.move_hint.configure(text=f"回放 {len(pts)} 个点", fg=OK)
            else:
                center = self.read_coords()
                try:
                    radius = float(self.jit_r.get())
                except ValueError:
                    radius = 3.0
                self.walker.jitter(center, radius_m=radius, interval=max(interval, 2.0))
                self.move_hint.configure(text=f"在 {center[0]:.5f},{center[1]:.5f} 附近抖动", fg=OK)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("启动失败", str(exc))
            return
        self.btn_walk.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.set_status("移动中…", ACCENT)

    def stop_walk(self, silent=False):
        try:
            if self.walker.running:
                self.walker.stop()
        except Exception:
            pass
        self.prog["value"] = 0
        try:
            self.map_prog["value"] = 0
        except Exception:
            pass
        self.btn_walk.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        try:
            self.btn_play.configure(state="normal")
            self.btn_pstop.configure(state="disabled")
        except Exception:
            pass
        if not silent:
            self.move_hint.configure(text="已停止", fg=SUB)
            self.set_status("已停止", SUB)

    def _tick(self):
        if self.walker.running:
            pct = max(0.0, min(1.0, self.walker.progress)) * 100
            self.prog["value"] = pct
            try:
                self.map_prog["value"] = pct
            except Exception:
                pass
        self._refresh_status_info()
        self.after(400, self._tick)

    # ---------------------------------------------------------------- 收藏
    def _fav_add(self):
        try:
            lat, lon = self.read_coords()
        except ValueError as exc:
            messagebox.showwarning("坐标不对", str(exc))
            return
        name = self.city_combo.get() or f"{lat:.5f},{lon:.5f}"
        base = name
        i = 2
        while name in self.favs:
            name = f"{base} #{i}"
            i += 1
        self.favs[name] = [lat, lon]
        self._sync_favs()
        self._save_cfg()
        self.log(f"已收藏：{name}")

    def _fav_del(self):
        name = self.fav_combo.get()
        if name and name in self.favs:
            self.favs.pop(name, None)
            self._sync_favs()
            self._save_cfg()
            self.log(f"已删除收藏：{name}")

    def _fav_pick(self, _evt=None):
        name = self.fav_combo.get()
        if name in self.favs:
            lat, lon = self.favs[name]
            self.lat_var.set(f"{lat:.6f}")
            self.lon_var.set(f"{lon:.6f}")

    def _sync_favs(self):
        self.fav_combo["values"] = list(self.favs.keys())
        if not self.favs:
            self.fav_combo.set("暂无收藏")

    # ---------------------------------------------------------------- 配置
    def _load_cfg(self):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _restore_cfg(self):
        self.favs = {k: list(v) for k, v in (self.cfg.get("favs") or {}).items()}
        self._sync_favs()
        last = self.cfg.get("last") or [39.908722, 116.397499]
        self.lat_var.set(f"{last[0]:.6f}")
        self.lon_var.set(f"{last[1]:.6f}")
        self.speed.set(str(self.cfg.get("speed", "5")))
        self.interval.set(str(self.cfg.get("interval", "1")))
        g = self.cfg.get("gait") or {}
        if g:
            self.gait_cfg = {
                "stride": float(g.get("stride", 1.05)),
                "cadence": float(g.get("cadence", 170)),
                "jitter": float(g.get("jitter", 2.5)),
                "pause": float(g.get("pause", 0.12)),
            }
        self.map_interval.set(str(self.cfg.get("map_interval", self.interval.get())))
        try:
            self.sim_on.set(bool(self.cfg.get("sim", True)))
        except Exception:
            pass
        self._sim_toggle()

    def _save_cfg(self):
        try:
            data = {
                "favs": self.favs,
                "speed": self.speed.get(),
                "interval": self.interval.get(),
                "gait": self.gait_cfg,
                "sim": bool(self.sim_on.get()),
            }
            try:
                data["map_interval"] = self.map_interval.get()
            except Exception:
                pass
            try:
                data["baidu_ak"] = self.cfg.get("baidu_ak", "")
            except Exception:
                pass
            try:
                data["last"] = list(self.read_coords())
            except ValueError:
                pass
            with open(CFG_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self):
        try:
            self.stop_walk(silent=True)
        except Exception:
            pass
        self._save_cfg()
        try:
            self.set_status("正在断开设备…", SUB)
            self.engine.shutdown()
        except Exception:
            pass
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
