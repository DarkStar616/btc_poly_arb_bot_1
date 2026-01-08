# list_bot.ps1
Write-Output "Searching for active bot processes..."
Write-Output "--------------------------------------------------"
Write-Output "PID`tRun-ID`t`tCommand"
Write-Output "--------------------------------------------------"

$procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'python3.exe'"
$count = 0

foreach ($p in $procs) {
    if ($p.CommandLine -match "-m src.arb.cli" -and ($p.CommandLine -match "paper-live|verify-feeds|verify-soak")) {
        $run_id = "N/A"
        if ($p.CommandLine -match "--run-id\s+([^\s]+)") {
            $run_id = $Matches[1]
        }
        Write-Output "$($p.ProcessId)`t$run_id`t`t$($p.CommandLine)"
        $count++
    }
}

if ($count -eq 0) {
    Write-Output "No matching bot processes found."
}
Write-Output "--------------------------------------------------"
Write-Output "Total: $count"
