#!/usr/bin/env bash
# 一键启动 Event Monitor
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "==> 创建虚拟环境 .venv"
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "==> 安装依赖"
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> 启动服务: http://127.0.0.1:8000"
cd backend
exec uvicorn main:app --host 127.0.0.1 --port 8000
