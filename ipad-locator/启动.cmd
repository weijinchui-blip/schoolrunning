@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "%~dp0main.py"
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0main.py"
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    echo 未找到 pythonw，用控制台模式启动...
    python "%~dp0main.py"
    pause
    exit /b
)

echo.
echo   没有找到 Python。
echo   请先安装 Python 3.10 或更新版本（安装时勾选 Add Python to PATH），
echo   然后在命令行执行：pip install pymobiledevice3
echo.
pause
