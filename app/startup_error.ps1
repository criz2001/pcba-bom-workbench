<#
  PCBA BOM 工作台 — 启动失败提示

  由 start.bat 在失败时调用：把原因用消息框展示出来，
  避免桌面快捷方式以最小化方式运行时看不到控制台输出。
#>
param(
  [string]$Key = 'unknown',
  [string]$LogFile = ''
)

$ErrorActionPreference = 'SilentlyContinue'
$nl = [string][char]13 + [string][char]10

$messages = @{
  no_python = '未检测到 Python 3.10 或更高版本。' + $nl + $nl + '请先安装 Python（安装时勾选 Add Python to PATH），然后重新运行 安装.bat。'
  python_old = '检测到的 Python 版本过低（需要 3.10 或更高版本）。' + $nl + $nl + '请升级 Python，然后重新运行 安装.bat。'
  env_failed = '运行环境准备失败：无法创建 .venv 或安装依赖。' + $nl + $nl + '常见原因：没有网络、代理拦截 PyPI、Python 安装不完整。' + $nl + '请检查网络后重新运行 安装.bat。' + $nl + $nl + '详细日志：logs\start.log'
  start_timeout = '应用窗口未能在 60 秒内启动。' + $nl + $nl + '请查看 logs\desktop.log 末尾的错误信息；' + $nl + '如果反复失败，请重新运行 安装.bat 修复运行环境。'
}
$text = $messages[$Key]
if (-not $text) { $text = '启动失败。请查看 logs\start.log 与 logs\desktop.log。' }

if ($LogFile) {
  try {
    Add-Content -LiteralPath $LogFile -Value ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Key) -Encoding UTF8
  } catch { }
}

if ($env:BOM_NONINTERACTIVE -ne '1') {
  try {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($text, 'PCBA BOM 工作台 — 启动失败', 'OK', 'Error')
  } catch { }
}
