# Free-AI-QQ-Bot

**零成本 AI QQ 机器人** — 不需要 OpenAI API Key，不需要任何付费服务。

基于 NoneBot2 + MiMoCode 免费模型，一行命令部署，5 分钟上线。

## 为什么做这个？

大多数 QQ AI 机器人需要：
- OpenAI API Key（$5 起充）
- 云服务器（¥50+/月）
- 复杂的配置流程

这个项目：
- **零成本**：使用 MiMo 免费模型，无需任何 API Key
- **零服务器**：本地运行，有电脑就行
- **零配置**：改一行 QQ Bot ID 就能用
- **零门槛**：不需要懂 AI，不需要懂编程

## 功能

- 文本对话（多轮上下文）
- 图片识别（发图给 AI 分析）
- 会话管理（`/new` 新对话，`/session` 查看会话）
- 多后端支持（MiMo 免费 / OpenAI / Claude）
- 自动重连（WebSocket 断线自动恢复）

## 快速开始

### 1. 申请 QQ Bot

1. 打开 [QQ 开放平台](https://q.qq.com/)
2. 创建机器人（选择"公域机器人"）
3. 获取 `AppID` 和 `AppSecret`

### 2. 安装

```bash
# 克隆项目
git clone https://github.com/Andlex/free-ai-qq-bot.git
cd free-ai-qq-bot

# 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置

复制 `.env.example` 为 `.env`，填入你的 QQ Bot 信息：

```bash
cp .env.example .env
```

编辑 `.env`：
```env
DRIVER=~fastapi+~httpx+~websockets
QQ_IS_SANDBOX=true
QQ_BOTS='[
  {
    "id": "你的AppID",
    "token": "你的AppSecret",
    "secret": "你的AppSecret",
    "intent": {
      "c2c_group_at_messages": true
    }
  }
]'
```

### 4. 运行

```bash
python bot.py
```

在 QQ 上给机器人发消息，即可开始对话。

### 5. 后台运行（可选）

```bash
# 使用 systemd
sudo cp deploy/qq-ai-bot.service /etc/systemd/system/
sudo systemctl enable --now qq-ai-bot
```

## 使用 OpenAI / Claude（可选）

如果需要更强的模型，在 `.env` 中配置对应的 API Key：

```env
# 使用 OpenAI
AI_BACKEND=openai
OPENAI_API_KEY=sk-xxx

# 使用 Claude
AI_BACKEND=claude
ANTHROPIC_API_KEY=sk-ant-xxx

# 使用免费 MiMo（默认，无需任何 Key）
AI_BACKEND=mimo
```

## 命令列表

| 命令 | 说明 |
|---|---|
| `/new` | 开启新对话 |
| `/session` | 查看当前会话 |
| `/help` | 显示帮助 |

## 项目结构

```
free-ai-qq-bot/
├── bot.py              # 入口
├── plugins/
│   └── mimocode.py     # 核心插件
├── src/
│   └── ai_backend.py   # 多后端 AI 支持
├── .env.example        # 配置模板
├── requirements.txt    # 依赖
└── README.md
```

## 常见问题

**Q: 需要服务器吗？**
A: 不需要。本地电脑运行即可，保持在线就行。

**Q: 需要付费吗？**
A: 不需要。MiMo 免费模型完全免费，无限制。

**Q: 支持群聊吗？**
A: 当前支持私聊。群聊 @ 机器人功能开发中。

**Q: 支持图片吗？**
A: 支持。发送图片给机器人，AI 会分析图片内容。

## 技术栈

- [NoneBot2](https://nonebot.dev/) — Python 异步机器人框架
- [nonebot-adapter-qq](https://github.com/nonebot/adapter-qq) — QQ 官方 API 适配器
- [MiMoCode](https://mimocode.com/) — 免费 AI 模型

## License

MIT
