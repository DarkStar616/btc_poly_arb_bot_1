# kill_bot.ps1
Write-Output "Killing active bot processes..."
Write-Output "--------------------------------------------------"

$procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'python3.exe'"
$count = 0

foreach ($p in $procs) {
    if ($p.CommandLine -match "-m src.arb.cli" -and ($p.CommandLine -match "paper-live|verify-feeds|verify-soak")) {
        Write-Output "Killing PID $($p.ProcessId): $($p.CommandLine)"
        Stop-Process -Id $p.ProcessId -Force
        $count++
    }
}

if ($count -eq 0) {
    Write-Output "No matching bot processes found to kill."
}
else {
    Write-Output "Done. Killed $count processes."
}
Write-Output "--------------------------------------------------"
