@echo off
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName GameTimeTracker -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName GameTimeTracker -Confirm:$false"
echo Task removed. Your log files on the Desktop were left untouched.
pause
