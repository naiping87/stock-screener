Unregister-ScheduledTask -TaskName "StockScreenerAlert" -Confirm:$false -ErrorAction SilentlyContinue

# Run pythonw.exe directly (no console window) -- avoids VBS middleman that can cause CMD flashes
$action = New-ScheduledTaskAction `
    -Execute "C:\Users\ediso\AppData\Local\Programs\Python\Python312\pythonw.exe" `
    -Argument "`"C:\Users\ediso\OneDrive\cctest\stock-screener\alert_monitor.py`"" `
    -WorkingDirectory "C:\Users\ediso\OneDrive\cctest\stock-screener"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -Compatibility Win8

Register-ScheduledTask -TaskName "StockScreenerAlert" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
Write-Host "Done -- pythonw.exe runs directly, no console flash"
