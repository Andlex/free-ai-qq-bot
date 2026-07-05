#!/bin/bash
set -e
echo "=== Free AI QQ Bot 安装 ==="

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 需要 Python 3.10+"
    exit 1
fi

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "虚拟环境已创建"
fi

source .venv/bin/activate
pip install -r requirements.txt
echo "依赖已安装"

# 配置
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "请编辑 .env 填入你的 QQ Bot 信息"
    echo "  1. 打开 https://q.qq.com/ 申请机器人"
    echo "  2. 获取 AppID 和 AppSecret"
    echo "  3. 编辑 .env 填入"
else
    echo ".env 已存在，跳过"
fi

echo ""
echo "=== 安装完成 ==="
echo "运行方式:"
echo "  python bot.py"
