@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 --version >nul 2>nul
if not errorlevel 1 (
  py -3 install.py %*
  goto done
)
python --version >nul 2>nul
if not errorlevel 1 (
  python install.py %*
  goto done
)
echo Windows Python not found, trying WSL...
wsl.exe -e python3 install.py %*
:done
echo.
pause
