# 大肥鱼 AI 虚拟主播 - 一键启动（启动前先清理）
# 流程：清理 -> 弹幕监听 -> 字幕/口型/状态采集 -> WebUI -> 主程序 -> 健康检查

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot

function Step($text)  { Write-Host "`n== $text ==" -ForegroundColor Cyan }
function Ok($text)    { Write-Host "  [OK]   $text" -ForegroundColor Green }
function Warn2($text) { Write-Host "  [WARN] $text" -ForegroundColor Yellow }
function Err2($text)  { Write-Host "  [FAIL] $text" -ForegroundColor Red }

# Get-NetTCPConnection 在这台机器上会偶发返回空（端口明明是开的），
# 统一用 TcpClient 直接连，判断更可靠。
function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        return $client.ConnectAsync("127.0.0.1", $port).Wait(600)
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '   大肥鱼 AI 虚拟主播 - 一键启动' -ForegroundColor Cyan
Write-Host '   清理 -> 弹幕监听 -> 字幕/口型 -> WebUI -> 主程序' -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan

# ---------- 1. 清理 ----------
Step '1/6 清理上次运行的残留进程、端口和临时文件'

$patterns = @(
    'main\.py',
    'webui\.py',
    'caption_printer\.py',
    'songroom_lipsync\.py',
    'songroom_overlay\.py',
    'character_manager\.py'
)

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = $_.CommandLine
    if (-not $cmd) { return }
    foreach ($p in $patterns) {
        if ($cmd -match $p) {
            try {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
                Write-Host ("  已停止 {0} (PID {1})" -f $_.Name, $_.ProcessId)
            } catch { }
            break
        }
    }
}

Get-Process -Name WssBarrageServer -ErrorAction SilentlyContinue | ForEach-Object {
    $p = $_
    # 先尝试正常关闭，让它把系统代理还原；关不掉再强杀
    try { [void]$p.CloseMainWindow() } catch { }
    if (-not $p.WaitForExit(3000)) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { }
    }
    Write-Host ("  已停止 WssBarrageServer (PID {0})" -f $p.Id)
}

Start-Sleep -Milliseconds 800

# 兜底：仍占用这些端口的 python / 弹幕监听进程也结束（不要动 3425 LLM 中转）
foreach ($port in 5500, 8081, 8082, 8090, 12345, 8888, 8827) {
    $owners = @()
    foreach ($line in (& netstat -ano)) {
        if ($line -match ("^\s*TCP\s+\S+:" + $port + "\s+\S+\s+LISTENING\s+(\d+)")) {
            $owners += [int]$matches[1]
        }
    }
    foreach ($ownerPid in ($owners | Sort-Object -Unique)) {
        $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        if ($proc -and ($proc.ProcessName -like 'python*' -or $proc.ProcessName -like 'WssBarrageServer*')) {
            try {
                Stop-Process -Id $proc.Id -Force -ErrorAction Stop
                Write-Host ("  释放端口 {0}（已停止 {1} PID {2}）" -f $port, $proc.ProcessName, $proc.Id)
            } catch { }
        }
    }
}
Start-Sleep -Milliseconds 500

# 临时产物，启动后会自动重建
$songroom = Join-Path $root 'out\songroom'
if (Test-Path $songroom) {
    Get-ChildItem $songroom -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.pid', '.lock' -or $_.Name -in 'state.json', 'mouth.json' } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
Get-ChildItem (Join-Path $root 'out') -Filter 'edge_tts_*.mp3' -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
Ok '残留已清理（日志、bgm_cache、歌曲文件都保留）'

# ---------- 2. 弹幕监听 ----------
Step '2/6 启动抖音弹幕监听（端口 8888）'
$grabDir = Join-Path $root 'tools\DouyinBarrageGrab'
$grabExe = Join-Path $grabDir 'WssBarrageServer.exe'
if (-not (Test-Path $grabExe)) {
    Err2 "找不到弹幕监听程序：$grabExe"
} else {
    Start-Process -FilePath $grabExe -WorkingDirectory $grabDir
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port 8888) { break }
        Start-Sleep -Milliseconds 500
    }
    if (Test-Port 8888) {
        Ok '弹幕监听已就绪：ws://127.0.0.1:8888'
    } else {
        Warn2 '8888 端口 20 秒内未监听，请查看弹幕监听窗口的报错'
    }
}

# ---------- 3. 字幕 / 口型 / 状态采集 ----------
Step '3/6 启动字幕、口型和直播状态采集'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\start-caption-printer.ps1')
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\start-songroom-lipsync.ps1')
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\start-songroom-overlay.ps1')

# ---------- 4. WebUI + 角色管理 ----------
Step '4/6 启动 WebUI 控制台（8081）和角色管理页（8090）'
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Err2 "找不到虚拟环境：$py"
} else {
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', ('title 大肥鱼 WebUI && "' + $py + '" webui.py')) -WorkingDirectory $root
    Ok 'WebUI 窗口已启动：http://127.0.0.1:8081'
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', ('title 大肥鱼 角色管理 && "' + $py + '" tools\character_manager.py')) -WorkingDirectory $root
    Ok '角色管理窗口已启动：http://127.0.0.1:8090'
}

# ---------- 5. 主程序 ----------
Step '5/6 启动主程序（Live2D 12345 / HTTP API 8082）'
if (Test-Path $py) {
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', ('title 大肥鱼 主程序 && "' + $py + '" main.py')) -WorkingDirectory $root
    Ok '主程序窗口已启动（首次加载模型稍慢）'
}

# ---------- 6. 健康检查 ----------
Step '6/6 健康检查（最多等 60 秒）'
$checks = @(
    @{ Name = '弹幕监听 8888';      Port = 8888 },
    @{ Name = '主程序 API 8082';    Port = 8082 },
    @{ Name = 'Live2D 画面 12345';  Port = 12345 },
    @{ Name = '字幕服务 5500';      Port = 5500 },
    @{ Name = 'WebUI 8081';         Port = 8081 },
    @{ Name = '角色管理 8090';      Port = 8090 }
)

$deadline = (Get-Date).AddSeconds(60)
do {
    $all = $true
    foreach ($c in $checks) {
        if (-not (Test-Port $c.Port)) { $all = $false }
    }
    if ($all) { break }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)

foreach ($c in $checks) {
    if (Test-Port $c.Port) {
        Ok $c.Name
    } else {
        Warn2 ($c.Name + ' 未监听')
    }
}

try {
    $models = Invoke-RestMethod 'http://127.0.0.1:3425/v1/models' -TimeoutSec 3
    Ok ('LLM 中转 3425 正常（可用模型 ' + @($models.data).Count + ' 个）')
} catch {
    Err2 'LLM 中转 3425 不可用，主程序将无法回复。请先启动你的本地中转服务'
}

try {
    $cfg = Get-Content (Join-Path $root 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host ("  当前配置：LLM={0} / {1}，TTS={2}" -f $cfg.chat_type, $cfg.claude.model, $cfg.audio_synthesis_type) -ForegroundColor Gray
} catch { }

Write-Host ''
Write-Host '启动完成。' -ForegroundColor Cyan
Write-Host '  角色管理：http://127.0.0.1:8090 （切皮套 / 换音色 / 改人设）' -ForegroundColor Cyan
Write-Host '  OBS 浏览器源：http://127.0.0.1:12345/Live2D/stage-portrait.html （竖屏用这个，横屏用 stage-landscape.html）' -ForegroundColor Cyan
Write-Host '  字幕/口型服务会自己发布状态，OBS 里加好浏览器源和虚拟摄像头即可开播。' -ForegroundColor Cyan
Write-Host ''
Read-Host '按回车关闭本窗口（各服务在各自的窗口里继续运行）'
