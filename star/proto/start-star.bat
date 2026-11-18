@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 星图原型：启动本机服务（只在 127.0.0.1，DeepSeek 密钥留在服务里），然后打开页面。
rem 关掉标题为「星图原型服务」的小窗口就停了。
start "星图原型服务" /min python star_server.py
timeout /t 1 /nobreak >nul
start "" http://127.0.0.1:8791/
