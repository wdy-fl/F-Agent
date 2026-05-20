$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (Test-Path ".venv\Scripts\Activate.ps1") {
    . ".venv\Scripts\Activate.ps1"
} else {
    Write-Host "错误：未找到虚拟环境 .venv\，请先运行: python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -e `".[dev]`""
    exit 1
}

python main.py $args
