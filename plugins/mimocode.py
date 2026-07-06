#!/usr/bin/env python3
"""Free AI QQ Bot — NoneBot2 plugin with multi-backend support."""
import asyncio, hashlib, json, os, time, traceback
from collections import defaultdict
from pathlib import Path

import httpx
from nonebot import on_message, on_command, logger, get_driver
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.matcher import Matcher

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from ai_backend import run_ai, detect_backend

# ── Config ──────────────────────────────────────────────────
SESSION_FILE = Path(__file__).parent.parent / "sessions.json"
IMAGE_DIR = Path.home() / ".cache" / "qq-images"
CHUNK_SIZE = 1900

# ── Session store ───────────────────────────────────────────
class SessionStore:
    def __init__(self):
        self._data: dict[str, str] = {}
        if SESSION_FILE.exists():
            try: self._data = json.loads(SESSION_FILE.read_text())
            except Exception: pass
    def _save(self):
        SESSION_FILE.write_text(json.dumps(self._data, indent=2))
    def get(self, uid: str) -> str | None:
        return self._data.get(uid)
    def set(self, uid: str, sid: str):
        self._data[uid] = sid
        self._save()
    def clear(self, uid: str):
        self._data.pop(uid, None)
        self._save()

sessions = SessionStore()

# ── Per-user message queue ──────────────────────────────────
_user_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
_active_processors: set[str] = set()

# ── Image cache cleanup ─────────────────────────────────────
def _cleanup_image_cache():
    if not IMAGE_DIR.exists(): return
    now = time.time()
    count = sum(1 for f in IMAGE_DIR.iterdir()
                if f.is_file() and (now - f.stat().st_mtime) > 604800 and not f.unlink() or False)
    if count: logger.info(f"Image cache: cleaned {count} old files")

driver = get_driver()
driver.on_startup(_cleanup_image_cache)

# ── Image download ──────────────────────────────────────────
async def download_image(url: str) -> str | None:
    try:
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=30, follow_redirects=True)
            if r.status_code == 200 and len(r.content) > 100:
                ct = r.headers.get("content-type", "")
                suffix = ".jpg" if "jpeg" in ct or "jpg" in ct else ".png"
                name = hashlib.md5(r.content).hexdigest()[:12] + suffix
                path = IMAGE_DIR / name
                path.write_bytes(r.content)
                return str(path)
    except Exception as e:
        logger.warning(f"Image download error: {e}")
    return None

# ── Session key helper ──────────────────────────────────────
def get_session_key(event: MessageEvent) -> str:
    """Get session key: group_{group_openid} for groups, user_{user_id} for C2C."""
    group_openid = getattr(event, 'group_openid', None)
    if group_openid:
        return f"group_{group_openid}"
    return f"user_{event.get_user_id()}"

def get_chat_type(event: MessageEvent) -> str:
    return "群聊" if getattr(event, 'group_openid', None) else "私聊"

# ── QQ Bot API ──────────────────────────────────────────────
_token_cache = {"token": None, "expires": 0}

def _get_qq_config():
    """延迟读取环境变量，确保 .env 已加载"""
    return os.environ.get("QQ_APP_ID", ""), os.environ.get("QQ_APP_SECRET", "")

async def get_qq_access_token() -> str | None:
    """获取 QQ Bot access_token"""
    import time
    now = time.time()
    if _token_cache["token"] and _token_cache["expires"] > now:
        return _token_cache["token"]

    app_id, app_secret = _get_qq_config()
    if not app_id or not app_secret:
        logger.warning("QQ_APP_ID 或 QQ_APP_SECRET 未配置")
        return None

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://bots.qq.com/app/getAppAccessToken",
                json={"appId": app_id, "clientSecret": app_secret},
                timeout=10,
            )
            data = r.json()
            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 7200))
            if token:
                _token_cache["token"] = token
                _token_cache["expires"] = now + expires_in - 60
                return token
    except Exception as e:
        logger.error(f"获取 access_token 失败: {e}")
    return None

async def get_user_info(user_openid: str) -> dict | None:
    """通过 openid 获取用户信息"""
    token = await get_qq_access_token()
    if not token:
        return None

    app_id, _ = _get_qq_config()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.sgroup.qq.com/v2/users/{user_openid}",
                headers={"Authorization": f"Bot {app_id}.{token}"},
                timeout=10,
            )
            logger.info(f"QQ API 响应: status={r.status_code}, body={r.text[:200]}")
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
    return None

# ── Handlers ────────────────────────────────────────────────
new_cmd = on_command("new", priority=1, block=True)
session_cmd = on_command("session", aliases={"sid"}, priority=1, block=True)
help_cmd = on_command("help", aliases={"h"}, priority=1, block=True)
backend_cmd = on_command("backend", aliases={"model"}, priority=1, block=True)
userinfo_cmd = on_command("userinfo", aliases={"ui"}, priority=1, block=True)
msg_handler = on_message(priority=5, block=True)

@new_cmd.handle()
async def handle_new(matcher: Matcher, event: MessageEvent):
    key = get_session_key(event)
    sessions.clear(key)
    await matcher.finish("已开启新对话。")

@session_cmd.handle()
async def handle_session(matcher: Matcher, event: MessageEvent):
    key = get_session_key(event)
    sid = sessions.get(key)
    chat = get_chat_type(event)
    await matcher.finish(f"[{chat}] 当前会话: {sid or '(无)'}")

@help_cmd.handle()
async def handle_help(matcher: Matcher, event: MessageEvent):
    chat = get_chat_type(event)
    text = f"[{chat}] 命令列表:\n"
    text += "/new - 开启新对话\n"
    text += "/session - 查看当前会话\n"
    text += "/backend - 查看当前AI后端\n"
    text += "/userinfo - 查看用户信息\n"
    text += "/help - 显示此帮助\n"
    text += "\n直接发消息即可对话，支持图片。"
    await matcher.finish(text)

@backend_cmd.handle()
async def handle_backend(matcher: Matcher):
    b = detect_backend()
    names = {"mimo": "MiMo (免费)", "openai": "OpenAI", "claude": "Claude"}
    await matcher.finish(f"当前后端: {names.get(b, b)}")

@userinfo_cmd.handle()
async def handle_userinfo(matcher: Matcher, event: MessageEvent):
    user_id = event.get_user_id()
    group_openid = getattr(event, 'group_openid', None)
    msg_id = getattr(event, 'id', None)
    chat = get_chat_type(event)

    # 从事件中获取基本信息
    text = f"[{chat}] 用户信息:\n"
    text += f"OpenID: {user_id}\n"

    # 尝试通过 API 获取详细信息
    info = await get_user_info(user_id)
    if info:
        text += f"昵称: {info.get('username', '未知')}\n"
        text += f"头像: {info.get('avatar', '无')}\n"
    else:
        text += "昵称: (需申请权限)\n"

    if group_openid:
        text += f"所在群: {group_openid}\n"
    if msg_id:
        text += f"消息ID: {msg_id}"

    await matcher.finish(text)

@msg_handler.handle()
async def handle_message(matcher: Matcher, event: MessageEvent):
    user_id = event.get_user_id()
    group_openid = getattr(event, 'group_openid', None)
    chat_type = "群聊" if group_openid else "私聊"

    logger.info(f"[{chat_type}] User: {user_id} | Group: {group_openid or 'N/A'}")

    key = get_session_key(event)
    _user_queues[key].put_nowait((matcher, event))
    if key not in _active_processors:
        _active_processors.add(key)
        asyncio.create_task(_process_queue(key))

async def _process_queue(key: str):
    q = _user_queues[key]
    try:
        while True:
            try:
                matcher, event = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break
            try:
                msg = event.get_message()
                text = msg.extract_plain_text().strip()

                user_id = event.get_user_id()
                group_openid = getattr(event, 'group_openid', None)
                msg_id = getattr(event, 'id', None)
                timestamp = getattr(event, 'timestamp', None)
                logger.info(f"Message received: user={user_id}, group={group_openid}, msg_id={msg_id}, time={timestamp}")

                file_path = None
                for seg in msg:
                    if seg.type == "image":
                        url = seg.data.get("url") or seg.data.get("file")
                        if url:
                            file_path = await download_image(url)
                            if not text: text = "请分析这张图片"
                        break

                if not text and not file_path: continue

                sid = sessions.get(key)
                logger.info(f"Processing message: {text[:50]}... (session: {sid})")
                out, new_sid = await asyncio.get_event_loop().run_in_executor(
                    None, run_ai, text, sid, file_path
                )
                logger.info(f"AI response: {out[:100]}... (new_session: {new_sid})")

                if new_sid and new_sid != sid:
                    sessions.set(key, new_sid)

                if file_path:
                    try: os.unlink(file_path)
                    except OSError: pass

                for i in range(0, len(out), CHUNK_SIZE):
                    await matcher.send(MessageSegment.text(out[i:i + CHUNK_SIZE]))
            except Exception:
                logger.error(f"handle_message error:\n{traceback.format_exc()}")
    finally:
        _active_processors.discard(key)
