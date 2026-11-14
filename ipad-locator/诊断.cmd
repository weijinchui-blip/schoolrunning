@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"

echo ================================================
echo   iPad 定位器 · 环境自检
echo ================================================
echo.

"%PY%" -c "import sys;print('Python:', sys.version)"
"%PY%" -c "import tkinter;print('tkinter: OK', tkinter.TkVersion)"
"%PY%" -c "import pymobiledevice3,importlib.metadata as m;print('pymobiledevice3:', m.version('pymobiledevice3'))"
echo.
echo --- 当前连接的设备 ---
"%PY%" -m pymobiledevice3 usbmux list
echo.
echo --- 链路测试（连设备 -> 设坐标 -> 撤销）---
"%PY%" selftest.py

echo.
pause
