<#
  PCBA BOM 工作台 — 安装 / 升级脚本

  做的事：
    1. 把程序文件复制到安装目录（默认 %LOCALAPPDATA%\Programs\PCBA-BOM-Workbench）
    2. 写入 config.json，数据目录默认 %LOCALAPPDATA%\PCBA-BOM-Workbench\data
    3. 在桌面和开始菜单创建「PCBA BOM 工作台」快捷方式（使用应用图标）
    4. 注册「应用和功能」卸载入口
    5. 写入 install.json，供卸载脚本识别安装信息

  用法（推荐双击 安装.bat）：
    powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
  可选参数：
    -InstallDir <目录>     程序安装目录
    -DataDir <目录>        数据目录（上传文件 / 输出结果 / 任务快照）
    -ShortcutName <名称>   快捷方式名称
    -NoDesktopShortcut     不创建桌面图标
    -NoStartMenuShortcut   不创建开始菜单快捷方式
    -NoRegistry            不写注册表卸载项
    -Launch                安装完成后立即启动
    -Quiet                 减少输出（不等待回车）
#>
param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\PCBA-BOM-Workbench'),
  [string]$DataDir = (Join-Path $env:LOCALAPPDATA 'PCBA-BOM-Workbench\data'),
  [string]$ShortcutName = 'PCBA BOM 工作台',
  [switch]$NoDesktopShortcut,
  [switch]$NoStartMenuShortcut,
  [switch]$NoRegistry,
  [switch]$Launch,
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$AppId = 'PCBA-BOM-Workbench'
$SourceDir = $PSScriptRoot
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$DataDir = [IO.Path]::GetFullPath($DataDir)
$utf8Bom = New-Object System.Text.UTF8Encoding($true)

function Say([string]$text) { if (-not $Quiet) { Write-Host $text } }
function Fail([string]$text) {
  Write-Host ''
  Write-Host ('[错误] ' + $text) -ForegroundColor Red
  Write-Host ''
  exit 1
}

Say ''
Say '============================================================'
Say '  安装 PCBA BOM 工作台'
Say ('  源目录  ：' + $SourceDir)
Say ('  安装目录：' + $InstallDir)
Say ('  数据目录：' + $DataDir)
Say '============================================================'
Say ''

# ---------- 1. 检查源文件 ----------
foreach ($rel in @('app\desktop.py', 'app\server.py', 'start.bat', 'requirements.txt')) {
  if (-not (Test-Path (Join-Path $SourceDir $rel))) {
    Fail ('源目录不完整，缺少 ' + $rel + '。请把安装包完整解压后，再运行安装器。')
  }
}
if (-not (Test-Path $env:LOCALAPPDATA)) { Fail '无法确定用户数据目录（LOCALAPPDATA 为空）。' }

# ---------- 2. 关闭正在运行的实例 ----------
$stopped = 0
try {
  Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = $_.CommandLine
    if ($cmd -and $cmd -like '*app\desktop.py*' -and ($cmd -like ('*' + $InstallDir + '*') -or $cmd -like ('*' + $SourceDir + '*'))) {
      try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $stopped++ } catch { }
    }
  }
} catch { }
if ($stopped) {
  Say ('已关闭 ' + $stopped + ' 个正在运行的实例')
  Start-Sleep -Milliseconds 600
}

# ---------- 3. 复制程序文件 ----------
$excludeDirs = @('.venv', 'venv', 'logs', 'workspace', '.git', '__pycache__', '.pytest_cache')
$excludeFilePatterns = @('config.json', '*.pptx', '*.log')
function Copy-Tree([string]$src, [string]$dst) {
  if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Force -Path $dst | Out-Null }
  Get-ChildItem -LiteralPath $src -Force | ForEach-Object {
    if ($_.PSIsContainer) {
      if ($excludeDirs -contains $_.Name) { return }
      if ($_.Name -like '.dsh-office-*') { return }
      Copy-Tree $_.FullName (Join-Path $dst $_.Name)
    } else {
      $skip = $false
      foreach ($p in $excludeFilePatterns) { if ($_.Name -like $p) { $skip = $true } }
      if (-not $skip) { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dst $_.Name) -Force }
    }
  }
}

if ($InstallDir.TrimEnd('\') -ne $SourceDir.TrimEnd('\')) {
  Say '正在复制程序文件 ...'
  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
  Copy-Tree $SourceDir $InstallDir
} else {
  Say '安装目录与源目录相同，跳过复制（就地安装）'
}

# ---------- 4. 数据目录与 config.json ----------
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$version = '0.0.0'
$initFile = Join-Path $InstallDir 'app\__init__.py'
if (Test-Path $initFile) {
  $initText = Get-Content -Raw -Encoding UTF8 $initFile
  $m = [regex]::Match($initText, '__version__\s*=\s*"([^"]+)"')
  if ($m.Success) { $version = $m.Groups[1].Value }
}
$installedAt = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$cfg = [ordered]@{
  workspace   = $DataDir
  version     = $version
  installedAt = $installedAt
}
[IO.File]::WriteAllText((Join-Path $InstallDir 'config.json'), ($cfg | ConvertTo-Json), $utf8Bom)
Say ('已写入 config.json（版本 ' + $version + '）')

# ---------- 5. 快捷方式 ----------
$wsh = New-Object -ComObject WScript.Shell
$startBat = Join-Path $InstallDir 'start.bat'
$icon = Join-Path $InstallDir 'app\static\assets\app.ico'
$shortcuts = @()

function New-AppShortcut([string]$path) {
  $parent = Split-Path -Parent $path
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $sc = $wsh.CreateShortcut($path)
  $sc.TargetPath = $startBat
  $sc.WorkingDirectory = $InstallDir
  if (Test-Path $icon) { $sc.IconLocation = ($icon + ',0') }
  $sc.WindowStyle = 7
  $sc.Description = 'PCBA BOM 工作台 — BOM 三方核对与生成'
  $sc.Save()
  Say ('已创建快捷方式：' + $path)
}

if (-not $NoDesktopShortcut) {
  $desktop = [Environment]::GetFolderPath('Desktop')
  if ($desktop) {
    $lnk = Join-Path $desktop ($ShortcutName + '.lnk')
    New-AppShortcut $lnk
    $shortcuts += $lnk
  } else {
    Say '[提示] 未能定位桌面目录，跳过桌面图标'
  }
}
if (-not $NoStartMenuShortcut) {
  $menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
  $lnk = Join-Path $menu ($ShortcutName + '.lnk')
  New-AppShortcut $lnk
  $shortcuts += $lnk
}

# ---------- 6. 卸载注册表项 ----------
if (-not $NoRegistry) {
  $regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\' + $AppId
  New-Item -Path $regPath -Force | Out-Null
  $uninstallCmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallDir 'uninstall.ps1') + '"'
  $sizeKb = 0
  try {
    $sum = (Get-ChildItem $InstallDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    if ($sum) { $sizeKb = [int]($sum / 1KB) }
  } catch { }
  Set-ItemProperty -Path $regPath -Name DisplayName -Value 'PCBA BOM 工作台'
  Set-ItemProperty -Path $regPath -Name DisplayVersion -Value $version
  Set-ItemProperty -Path $regPath -Name Publisher -Value '内部工具'
  Set-ItemProperty -Path $regPath -Name InstallLocation -Value $InstallDir
  if (Test-Path $icon) { Set-ItemProperty -Path $regPath -Name DisplayIcon -Value ($icon + ',0') }
  Set-ItemProperty -Path $regPath -Name UninstallString -Value $uninstallCmd
  Set-ItemProperty -Path $regPath -Name QuietUninstallString -Value ($uninstallCmd + ' -Quiet')
  Set-ItemProperty -Path $regPath -Name InstallDate -Value (Get-Date -Format 'yyyyMMdd')
  Set-ItemProperty -Path $regPath -Name EstimatedSize -Value $sizeKb -Type DWord
  Set-ItemProperty -Path $regPath -Name NoModify -Value 1 -Type DWord
  Set-ItemProperty -Path $regPath -Name NoRepair -Value 1 -Type DWord
  Say '已注册「应用和功能」卸载入口'
}

# ---------- 7. 安装标记 ----------
$marker = [ordered]@{
  appId        = $AppId
  version      = $version
  installedAt  = $installedAt
  installDir   = $InstallDir
  dataDir      = $DataDir
  shortcutName = $ShortcutName
  shortcuts    = @($shortcuts)
}
[IO.File]::WriteAllText((Join-Path $InstallDir 'install.json'), ($marker | ConvertTo-Json), $utf8Bom)

Say ''
Say '安装完成。'
Say ('  程序目录：' + $InstallDir)
Say ('  数据目录：' + $DataDir)
if ($shortcuts.Count -gt 0) { Say ('  快捷方式：' + $ShortcutName + '.lnk（桌面 / 开始菜单）') }
Say '  以后双击桌面上的「PCBA BOM 工作台」图标即可打开。'
Say '  升级时重新运行本安装器即可，数据与已建环境会保留。'
Say ''
if ($Launch) {
  Say '正在启动 PCBA BOM 工作台 ...'
  Start-Process -FilePath $startBat -WorkingDirectory $InstallDir
}
if (-not $Quiet) { Write-Host '按回车键关闭 ...'; Read-Host | Out-Null }
