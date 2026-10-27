<#
  PCBA BOM 工作台 — 卸载脚本

  用法（普通用户权限即可）：
    powershell -ExecutionPolicy Bypass -File uninstall.ps1
  可选：
    -RemoveData   连数据（上传文件与输出结果）一起删除
    -Quiet        减少输出
#>
param(
  [switch]$RemoveData,
  [switch]$Quiet
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$AppId = 'PCBA-BOM-Workbench'
$AppName = 'PCBA BOM 工作台'

function Say([string]$text) { if (-not $Quiet) { Write-Host $text } }

$InstallDir = $PSScriptRoot
if (-not (Test-Path (Join-Path $InstallDir 'app\desktop.py'))) {
  # 从安装目录外面调用时（例如注册表卸载），按默认位置推断
  $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\$AppId"
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$defaultInstall = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs\$AppId"))
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
$markerPath = Join-Path $InstallDir 'install.json'

$marker = $null
if (Test-Path $markerPath) {
  try { $marker = Get-Content $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
}

# ---------- 0. 只允许卸载真正的安装目录，避免误删开发目录 ----------
$isDefaultInstall = ($InstallDir.TrimEnd('\') -eq $defaultInstall.TrimEnd('\'))
$installed = (Test-Path $markerPath) -or $isDefaultInstall
if (-not $installed -and (Test-Path $regPath)) {
  try {
    $regLoc = (Get-ItemProperty $regPath -ErrorAction SilentlyContinue).InstallLocation
    if ($regLoc -and ([IO.Path]::GetFullPath($regLoc).TrimEnd('\') -eq $InstallDir.TrimEnd('\'))) { $installed = $true }
  } catch { }
}
if (-not $installed) {
  Write-Host ''
  Write-Host '[错误] 该目录不是通过安装器安装的程序目录，已停止卸载，避免误删文件。' -ForegroundColor Red
  Write-Host ('  目录：' + $InstallDir)
  Write-Host '  如果这是直接解压运行的开发版，请手动删除该文件夹。'
  Write-Host ''
  if (-not $Quiet) { Read-Host '按回车键关闭' | Out-Null }
  exit 1
}

Say ""
Say "============================================================"
Say "  卸载 $AppName"
Say "  程序目录：$InstallDir"
Say "============================================================"
Say ""

# ---------- 1. 关闭正在运行的实例 ----------
$stopped = 0
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='pythonw3.11.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
  if ($_.CommandLine -and $_.CommandLine -like "*$InstallDir*desktop.py*") {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $stopped++ } catch { }
  }
}
if ($stopped) { Say "已关闭 $stopped 个正在运行的实例" }

Start-Sleep -Milliseconds 400

# ---------- 2. 删除快捷方式 ----------
$targets = @()
if ($marker -and $marker.shortcuts) { $targets += @($marker.shortcuts) }
try {
  $desktop = [Environment]::GetFolderPath('Desktop')
  if ($desktop) { $targets += (Join-Path $desktop "$AppName.lnk") }
} catch { }
$targets += (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk")

foreach ($t in ($targets | Select-Object -Unique)) {
  if ($t -and (Test-Path $t)) {
    Remove-Item $t -Force -ErrorAction SilentlyContinue
    Say "已删除快捷方式：$t"
  }
}

# ---------- 3. 删除注册表项 ----------
if (Test-Path $regPath) {
  Remove-Item $regPath -Recurse -Force -ErrorAction SilentlyContinue
  Say "已从「已安装的应用」中移除"
}

# ---------- 4. 数据目录 ----------
$DataDir = $null
if ($marker -and $marker.dataDir) { $DataDir = $marker.dataDir }
if (-not $DataDir) {
  $configFile = Join-Path $InstallDir 'config.json'
  $DataDir = Join-Path $env:LOCALAPPDATA "$AppId\data"
  if (Test-Path $configFile) {
    try {
      $cfg = Get-Content $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($cfg.workspace) { $DataDir = $cfg.workspace }
    } catch { }
  }
}

if (-not $RemoveData) {
  $answer = Read-Host "是否同时删除数据（上传文件、输出结果、物料库）？(y/N)"
  if ($answer -match '^[Yy]') { $RemoveData = $true }
}

# ---------- 5. 删除程序目录 ----------
# 离开安装目录再删，避免「当前目录被占用」导致删不干净
Set-Location $env:TEMP
if (Test-Path $InstallDir) {
  Get-ChildItem $InstallDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path $InstallDir) {
    Write-Host "[提示] 程序目录未能完全删除（可能有文件被占用）：$InstallDir" -ForegroundColor Yellow
  } else {
    Say "已删除程序目录"
  }
}

if ($RemoveData) {
  if ($DataDir -and (Test-Path $DataDir)) {
    Remove-Item $DataDir -Recurse -Force -ErrorAction SilentlyContinue
    Say "已删除数据目录：$DataDir"
  }
  if ($DataDir) {
    $parent = Split-Path -Parent $DataDir
    if ($parent -and (Test-Path $parent) -and -not (Get-ChildItem $parent -Force -ErrorAction SilentlyContinue)) {
      Remove-Item $parent -Force -ErrorAction SilentlyContinue
    }
  }
} else {
  Say "已保留数据目录：$DataDir"
}

Say ""
Say "卸载完成。"
Say ""
if (-not $Quiet) { Read-Host "按回车键关闭" | Out-Null }
