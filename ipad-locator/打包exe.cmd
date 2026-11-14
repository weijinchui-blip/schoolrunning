@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"

echo ================================================
echo   打包 iPad 定位器为 exe
echo ================================================

"%PY%" -m pip install -q --disable-pip-version-check pyinstaller
if errorlevel 1 (
    echo 安装 pyinstaller 失败，先手动执行: pip install pyinstaller
    pause
    exit /b 1
)

"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "iPad定位器" ^
  --collect-all pymobiledevice3 ^
  --collect-all pytun_pmd3 ^
  --hidden-import pymobiledevice3.remote.userspace_tunnel ^
  --hidden-import pymobiledevice3.services.dvt.instruments.dvt_provider ^
  --hidden-import pymobiledevice3.services.dvt.instruments.location_simulation ^
  main.py

echo.
if exist "dist\iPad定位器.exe" (
    echo 打包完成: %cd%\dist\iPad定位器.exe
) else (
    echo 打包失败，看上面的报错。
)
pause
