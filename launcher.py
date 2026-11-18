#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Makes sure the start page's server is up, then opens the page at most once every couple of hours.

Run by AgentHome-Unlock on every unlock (and by AgentHome-Open with --force after logon).
The server check happens every time, even when the page isn't due to open again.
"""

import argparse
import os
import subprocess
import sys
import time

import server


def last_open():
    try:
        with open(os.path.join(server.state_dir(), "last_open.txt"), encoding="utf-8") as f:
            return float(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0.0


def start_server(port):
    if os.name == "nt":
        if subprocess.run(["schtasks", "/Run", "/TN", "AgentHome-Server"], capture_output=True).returncode == 0:
            return
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(exe):
            exe = sys.executable
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([exe, os.path.join(server.HOME, "server.py"), "--port", str(port)], creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([sys.executable, os.path.join(server.HOME, "server.py"), "--port", str(port)], start_new_session=True)


def ensure_server(port):
    """True once the server answers, starting it first if needed."""
    if server.healthy(port):
        return True
    start_server(port)
    for _ in range(40):
        if server.healthy(port):
            return True
        time.sleep(0.5)
    server.log("launcher: server did not come up on port %d" % port)
    return False


def main():
    parser = argparse.ArgumentParser(description="Open the start page after unlock")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGENT_HOME_PORT", server.DEFAULT_PORT)))
    parser.add_argument("--hours", type=float, default=2.0, help="don't reopen if it was opened less than this long ago")
    parser.add_argument("--force", action="store_true", help="ignore --hours")
    parser.add_argument("--dry-run", action="store_true", help="only say what would happen")
    args = parser.parse_args()

    up = server.healthy(args.port) if args.dry_run else ensure_server(args.port)
    age = time.time() - last_open()
    if not args.force and age < args.hours * 3600:
        print("server %s; opened %.0f minutes ago, not opening again" % ("up" if up else "down", age / 60))
        return 0 if up else 1
    if args.dry_run:
        print("server %s; would open (last opened %.0f minutes ago)" % ("up" if up else "down", age / 60))
        return 0
    if not up:
        return 1
    server.open_page("http://127.0.0.1:%d/" % args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
