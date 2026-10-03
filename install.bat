@echo off
setlocal
net session >nul 2>&1 || (echo Run this as Administrator ^(right-click - Run as administrator^). & pause & exit /b 1)

python -m pip install psutil pystray pillow pywin32 || (echo pip install failed. & pause & exit /b 1)

for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%i"
set "TRK=%~dp0tracker.py"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute $env:PYW -Argument ('\"' + $env:TRK + '\"') -WorkingDirectory (Split-Path $env:TRK);" ^
  "$t = New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERDOMAIN\$env:USERNAME\";" ^
  "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DontStopOnIdleEnd -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew;" ^
  "$p = New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\$env:USERNAME\" -LogonType Interactive -RunLevel Limited;" ^
  "Register-ScheduledTask -TaskName GameTimeTracker -Action $a -Trigger $t -Settings $s -Principal $p -Force | Out-Null;" ^
  "Start-ScheduledTask -TaskName GameTimeTracker"
if errorlevel 1 (echo Failed to register the task. & pause & exit /b 1)

echo Installed. GameTimeTracker is running and will start at every logon.
pause
