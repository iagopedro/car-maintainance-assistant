param(
    [switch]$Reset,
    [int]$Port = 8001
)
# Starts an isolated Rodagem instance for UI flow tests; it never touches db.sqlite3 or media/.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$data = Join-Path $root '.local\flows'
if ($Reset -and (Test-Path $data)) {
    Remove-Item -LiteralPath $data -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $data | Out-Null
$env:RODAGEM_DB_PATH = Join-Path $data 'flows.sqlite3'
$env:RODAGEM_MEDIA_ROOT = Join-Path $data 'media'
$env:RODAGEM_COOKIE_SUFFIX = 'flows'
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python (Join-Path $root 'manage.py') migrate --noinput | Out-Null
Write-Output "Instancia de fluxos: http://127.0.0.1:$Port (dados em $data)"
& $python (Join-Path $root 'manage.py') runserver "127.0.0.1:$Port" --noreload
