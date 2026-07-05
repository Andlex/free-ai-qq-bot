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

# ── Handlers ────────────────────────────────────────────────
new_cmd = on_command("new", priority=1, block=True)
session_cmd = on_command("session", aliases={"sid"}, priority=1, block=True)
help_cmd = on_command("help", aliases={"h"}, priority=1, block=True)
backend_cmd = on_command("backend", aliases={"model"}, priority=1, block=True)
msg_handler = on_message(priority=5, block=True)

@new_cmd.handle()
async def handle_new(matcher: Matcher, event: MessageEvent):
    sessions.clear(event.get_user_id())
    await matcher.finish("已开启新对话。")

@session_cmd.handle()
async def handle_session(matcher: Matcher, event: MessageEvent):
    sid = sessions.get(event.get_user_id())
    await matcher.finish(f"当前会话: {sid or '(无)'}")

@help_cmd.handle()
async def handle_help(matcher: Matcher):
    await matcher.finish(
        "命令列表:\n"
        "/new - 开启新对话\n"
        "/session - 查看当前会话\n"
        "/backend - 查看当前AI后端\n"
        "/help - 显示此帮助\n"
        "\n直接发消息即可对话，支持图片。"
    )

@backend_cmd.handle()
async def handle_backend(matcher: Matcher):
    b = detect_backend()
    names = {"mimo": "MiMo (免费)", "openai": "OpenAI", "claude": "Claude"}
    await matcher.finish(f"当前后端: {names.get(b, b)}")

@msg_handler.handle()
async def handle_message(matcher: Matcher, event: MessageEvent):
    uid = event.get_user_id()
    _user_queues[uid].put_nowait((matcher, event))
    if uid not in _active_processors:
        _active_processors.add(uid)
        asyncio.create_task(_process_queue(uid))

async def _process_queue(uid: str):
    q = _user_queues[uid]
    try:
        while True:
            try:
                matcher, event = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break
            try:
                msg = event.get_message()
                text = msg.extract_plain_text().strip()

                file_path = None
                for seg in msg:
                    if seg.type == "image":
                        url = seg.data.get("url") or seg.data.get("file")
                        if url:
                            file_path = await download_image(url)
                            if not text: text = "请分析这张图片"
                        break

                if not text and not file_path: continue

                sid = sessions.get(uid)
                out, new_sid = await asyncio.get_event_loop().run_in_executor(
                    None, run_ai, text, sid, file_path
                )

                if new_sid and new_sid != sid:
                    sessions.set(uid, new_sid)

                if file_path:
                    try: os.unlink(file_path)
                    except OSError: pass

                for i in range(0, len(out), CHUNK_SIZE):
                    await matcher.send(MessageSegment.text(out[i:i + CHUNK_SIZE]))
            except Exception:
                logger.error(f"handle_message error:\n{traceback.format_exc()}")
    finally:
        _active_processors.discard(uid)
