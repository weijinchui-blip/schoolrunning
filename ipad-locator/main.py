# -*- coding: utf-8 -*-
"""iPad 定位器 —— 启动入口"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    try:
        import pymobiledevice3  # noqa: F401
    except Exception:
        import tkinter as tk
        from tkinter import messagebox

        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(
            "缺少依赖",
            "没有装 pymobiledevice3。\n\n在命令行执行：\n    pip install pymobiledevice3\n\n然后重新打开本工具。",
        )
        r.destroy()
        return 1

    from gui import App

    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        err = traceback.format_exc()
        try:
            with open(os.path.join(HERE, "崩溃日志.txt"), "a", encoding="utf-8") as fh:
                fh.write(err + "\n" + "-" * 60 + "\n")
        except Exception:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox

            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("启动失败", err[-1200:])
            r.destroy()
        except Exception:
            print(err)
        sys.exit(1)
