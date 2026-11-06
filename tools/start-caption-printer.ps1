$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root 'out\songroom'
[void][IO.Directory]::CreateDirectory($out)

# Get-NetTCPConnection 在部分环境下会误报端口占用，统一用 TcpClient 实测
function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        return $client.ConnectAsync('127.0.0.1', $port).Wait(600)
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

$health = $null
try { $health = Invoke-RestMethod 'http://127.0.0.1:5500/health' -TimeoutSec 2 } catch { }
if ($health -and $health.service -eq 'local-caption-printer') {
    Write-Output 'CAPTION_PRINTER_ALREADY_RUNNING'
    exit 0
}
if (Test-Port 5500) { throw 'Port 5500 is in use; no second service started' }
$process = Start-Process -FilePath (Join-Path $root '.venv\Scripts\python.exe') `
    -ArgumentList @('-u','tools/caption_printer.py') -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $out 'caption.stdout.txt') -RedirectStandardError (Join-Path $out 'caption.stderr.txt')
[IO.File]::WriteAllText((Join-Path $out 'caption.pid'), [string]$process.Id)
Write-Output "CAPTION_PRINTER_LAUNCHED PID=$($process.Id)"
