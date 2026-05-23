#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 激活虚拟环境
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
else
    echo "错误：未找到虚拟环境 .venv/，请先运行: python3 -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\""
    exit 1
fi

# 启动 F-Agent
python3 main.py "$@"
