# Agent Home diagnostics. Writes diag-<COMPUTERNAME>.txt next to this script;
# Syncthing carries it back to the other computer so Claude can read it.
$ErrorActionPreference = 'Continue'
$env:WSL_UTF8 = '1'
$out = New-Object System.Collections.Generic.List[string]
function Add-Line($s) { $out.Add([string]$s) }
function Run-Check($label, [scriptblock]$block) {
  Add-Line ''
  Add-Line ('=== ' + $label)
  try { (& $block 2>&1 | Out-String -Width 220).TrimEnd() -split "`r?`n" | ForEach-Object { Add-Line $_ } }
  catch { Add-Line ('ERROR: ' + $_.Exception.Message) }
}

Add-Line ('time: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz') + '  tz: ' + (Get-TimeZone).Id)
Add-Line ('computer: ' + $env:COMPUTERNAME + '  user: ' + $env:USERDOMAIN + '\' + $env:USERNAME)
Add-Line ('home: ' + $PSScriptRoot)

Run-Check 'python on PATH' { Get-Command py, python, python3, pythonw -ErrorAction SilentlyContinue | Select-Object Name, Source | Format-Table -AutoSize }
Run-Check 'py -0p' { py -0p }
Run-Check 'python --version' { python --version }
Run-Check 'scheduled tasks' {
  Get-ScheduledTask -TaskName 'AgentHome-*' | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    '{0} state={1} lastRun={2} result=0x{3:X} action={4} {5}' -f $_.TaskName, $_.State, $i.LastRunTime, $i.LastTaskResult, $_.Actions[0].Execute, $_.Actions[0].Arguments
  }
}
Run-Check 'listeners on 8777 (Windows)' {
  Get-NetTCPConnection -LocalPort 8777 -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    '{0}:{1} {2} pid={3} {4}' -f $_.LocalAddress, $_.LocalPort, $_.State, $_.OwningProcess, $p.Path
  }
}
Run-Check 'processes running server.py' {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server.py*' } | ForEach-Object { '{0} {1}' -f $_.ProcessId, $_.CommandLine }
}
foreach ($u in 'http://127.0.0.1:8777/health', 'http://localhost:8777/health') {
  Run-Check ('GET ' + $u) { (Invoke-WebRequest -UseBasicParsing $u -TimeoutSec 4).Content }
}
Run-Check 'proxy (WinINET)' { Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' | Select-Object ProxyEnable, ProxyServer, ProxyOverride, AutoConfigURL | Format-List }
Run-Check 'proxy (WinHTTP)' { netsh winhttp show proxy }
Run-Check 'server.log (Windows)' { Get-Content (Join-Path $env:LOCALAPPDATA 'agent-home\server.log') -Tail 20 }
Run-Check 'WSL' { wsl.exe -e sh -c 'hostname; date; command -v python3; python3 --version; (ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep 8777; tail -n 20 ~/.local/share/agent-home/server.log 2>/dev/null' }
Run-Check 'files in home' { Get-ChildItem $PSScriptRoot | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize }

$path = Join-Path $PSScriptRoot ('diag-' + $env:COMPUTERNAME + '.txt')
[IO.File]::WriteAllLines($path, $out, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ''
Write-Host ('Done. Saved ' + $path)
Write-Host 'It syncs to the other computer in a few seconds. Tell Claude it is done.'
