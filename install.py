#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registers the scheduled tasks that keep the start page running and open it by itself.

  AgentHome-Server  at logon, then every 5 minutes: server.py. Only one copy runs, so
                    the repeat is a watchdog that brings the server back if it died.
  AgentHome-Open    shortly after logon: launcher.py --force (opens the page)
  AgentHome-Unlock  on unlock: launcher.py (makes sure the server is up; opens the page if it's been 2+ hours)

Run once per machine by double-clicking install.bat; --uninstall removes them all.
The tasks run as the current user, so no admin rights are needed. Inside WSL
(when Windows has no Python of its own) the tasks start the server through wsl.exe.
"""

import argparse
import datetime
import os
import platform
import subprocess
import sys
from xml.sax.saxutils import escape

HOME = os.path.dirname(os.path.abspath(__file__))
TASKS = ("AgentHome-Server", "AgentHome-Open", "AgentHome-Unlock")


def in_wsl():
    return "microsoft" in platform.uname().release.lower()


def run(cmd):
    r = subprocess.run(cmd, capture_output=True)
    out = (r.stdout or b"") + (r.stderr or b"")
    for enc in ("utf-8", "gbk", "cp437"):
        try:
            return r.returncode, out.decode(enc)
        except UnicodeDecodeError:
            continue
    return r.returncode, out.decode("utf-8", "replace")


def schtasks():
    return "schtasks.exe" if in_wsl() else "schtasks"


def windows_user():
    if in_wsl():
        return run(["cmd.exe", "/c", "echo %USERDOMAIN%\\%USERNAME%"])[1].strip()
    return "%s\\%s" % (os.environ["USERDOMAIN"], os.environ["USERNAME"])


def windows_path(path):
    if in_wsl():
        return run(["wslpath", "-w", path])[1].strip()
    return path


def action(script, extra=""):
    target = os.path.join(HOME, script)
    if in_wsl():
        return r"C:\Windows\System32\wsl.exe", ('-e python3 "%s" %s' % (target, extra)).strip()
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    return exe, ('"%s" %s' % (target, extra)).strip()


def task_xml(description, trigger, command, arguments, user, time_limit, restart):
    restart_xml = "<RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>" if restart else ""
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{desc}</Description></RegistrationInfo>
  <Triggers>{trigger}</Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>{limit}</ExecutionTimeLimit>
    <Priority>7</Priority>
    {restart}
  </Settings>
  <Actions Context="Author"><Exec><Command>{cmd}</Command><Arguments>{args}</Arguments><WorkingDirectory>{wd}</WorkingDirectory></Exec></Actions>
</Task>
""".format(desc=escape(description), trigger=trigger, user=escape(user), limit=time_limit, restart=restart_xml,
           cmd=escape(command), args=escape(arguments), wd=escape(windows_path(HOME)))


def register(name, xml):
    path = os.path.join(HOME, ".%s.xml" % name)
    with open(path, "w", encoding="utf-16") as f:
        f.write(xml)
    try:
        return run([schtasks(), "/Create", "/TN", name, "/XML", windows_path(path), "/F"])
    finally:
        os.remove(path)


def stop_servers():
    """Stop every running copy of this folder's server.py, so the one started afterwards is the only one."""
    run([schtasks(), "/End", "/TN", "AgentHome-Server"])
    target = os.path.join(HOME, "server.py")
    if in_wsl():
        run(["pkill", "-f", target])
        return
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:AGENT_HOME_SERVER) } "
              "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", script],
                   env=dict(os.environ, AGENT_HOME_SERVER=target), capture_output=True)


def make_shortcut(port=8777):
    """开机首页.url on the desktop, so the page is opened from the server rather than as a local file."""
    if in_wsl():
        return None
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop')"],
                       capture_output=True)
    desktop = r.stdout.decode("utf-8", "replace").strip()
    if not desktop or not os.path.isdir(desktop):
        return None
    path = os.path.join(desktop, "开机首页.url")
    with open(path, "w", encoding="ascii", newline="\r\n") as f:
        f.write("[InternetShortcut]\nURL=http://127.0.0.1:%d/\n" % port)
    return path


def hermes_line():
    """The sentence to paste to Hermes: the first code block under 「第 1 步」 in incoming/KICKOFF.md."""
    path = os.path.join(os.path.dirname(HOME), "incoming", "KICKOFF.md")
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return None, path
    blocks = text.split("## 第 1 步", 1)[-1].split("```")
    return (blocks[1].strip() if len(blocks) > 2 else None), path


def copy_to_clipboard(text):
    try:
        if in_wsl():
            return subprocess.run(["clip.exe"], input=text.encode("utf-16"), capture_output=True).returncode == 0
        # clip.exe keeps the UTF-16 BOM as a stray character; PowerShell's Set-Clipboard doesn't.
        env = dict(os.environ, AGENT_HOME_CLIP=text)
        return subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:AGENT_HOME_CLIP"],
                              env=env, capture_output=True).returncode == 0
    except OSError:
        return False


def open_file(path):
    if in_wsl():
        run(["cmd.exe", "/c", "start", "", windows_path(path)])
    else:
        os.startfile(path)


def main():
    parser = argparse.ArgumentParser(description="Install the start page's scheduled tasks")
    parser.add_argument("--uninstall", action="store_true", help="remove both tasks and stop the server")
    parser.add_argument("--no-start", action="store_true", help="don't start the server right away")
    parser.add_argument("--quiet", action="store_true", help="reinstall only: skip the desktop shortcut, clipboard and setup guide")
    args = parser.parse_args()

    if os.name != "nt" and not in_wsl():
        print("只支持 Windows，或者 Windows 里的 WSL。")
        return 1

    if args.uninstall:
        stop_servers()
        for name in TASKS:
            code, out = run([schtasks(), "/Delete", "/TN", name, "/F"])
            print("%s：%s" % (name, "已删除" if code == 0 else "删除失败 " + out.strip()))
        return 0

    stop_servers()
    user = windows_user()
    logon = "<LogonTrigger><Enabled>true</Enabled><UserId>%s</UserId></LogonTrigger>" % escape(user)
    # A logon trigger's own repeat only starts at the next logon, and these machines stay logged on for
    # days, so the 5-minute watchdog is a time trigger starting now.
    every_5_min = ("<TimeTrigger><Repetition><Interval>PT5M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>"
                   "<StartBoundary>%s</StartBoundary><Enabled>true</Enabled></TimeTrigger>"
                   % datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    logon_later = "<LogonTrigger><Enabled>true</Enabled><UserId>%s</UserId><Delay>PT20S</Delay></LogonTrigger>" % escape(user)
    unlock = ("<SessionStateChangeTrigger><Enabled>true</Enabled><StateChange>SessionUnlock</StateChange>"
              "<UserId>%s</UserId></SessionStateChangeTrigger>" % escape(user))
    server_cmd, server_args = action("server.py")
    open_cmd, open_args = action("launcher.py", "--force")
    unlock_cmd, unlock_args = action("launcher.py")
    plans = [
        ("AgentHome-Server", task_xml("开机首页：登录时启动本地服务，之后每 5 分钟检查一次，停了就自动拉起",
                                      logon + every_5_min, server_cmd, server_args, user, "PT0S", True)),
        ("AgentHome-Open", task_xml("开机首页：登录后打开首页", logon_later, open_cmd, open_args, user, "PT5M", False)),
        ("AgentHome-Unlock", task_xml("开机首页：解锁时先确认服务在跑；距上次打开超过 2 小时就再打开首页",
                                      unlock, unlock_cmd, unlock_args, user, "PT5M", False)),
    ]
    failed = False
    for name, xml in plans:
        code, out = register(name, xml)
        print("%s：%s" % (name, "已注册" if code == 0 else "注册失败 " + out.strip()))
        failed = failed or code != 0
    if failed:
        print("有任务没注册上。可以把上面的报错发给 Claude。")
        return 1
    if in_wsl():
        print("提示：这台 Windows 没找到自己的 Python，任务会通过 WSL 启动，登录时可能闪一下黑窗口。")
    if not args.no_start:
        run([schtasks(), "/Run", "/TN", "AgentHome-Server"])
        run([schtasks(), "/Run", "/TN", "AgentHome-Open"])
        print("首页服务已重启（旧的都停掉了），浏览器马上会打开 http://127.0.0.1:8777")
    print("完成。服务会一直在跑：万一停了，5 分钟内自动拉起。开机会自动打开首页；离开两小时以上回来解锁时，也会再打开一次。")
    if args.quiet:
        return 0
    shortcut = make_shortcut()
    if shortcut:
        print("桌面上放了一个「开机首页」快捷方式，以后从它打开，不要双击 index.html。")
    line, kickoff = hermes_line()
    if line and copy_to_clipboard(line):
        print("下一步：要贴给 Hermes 的那句话已经复制好了，打开 Hermes 或 Claude Code 直接粘贴就行。")
    if os.path.exists(kickoff):
        open_file(kickoff)
        print("开工说明已打开：%s" % windows_path(kickoff))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
