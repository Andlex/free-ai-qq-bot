"""Multi-backend AI support for QQ Bot."""
import os, subprocess, json
from pathlib import Path

BACKEND = os.environ.get("AI_BACKEND", "auto")  # auto, mimo, openai, claude
OPENCODE_BIN = os.environ.get("OPENCODE_BIN", "mimo")
OPENCODE_DIR = os.environ.get("OPENCODE_DIR", str(Path.home()))
MIMO_TIMEOUT = 300


def detect_backend() -> str:
    """Auto-detect which backend to use."""
    if BACKEND != "auto":
        return BACKEND
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return "mimo"  # free, no key needed


def run_ai(msg: str, session_id: str | None = None, file_path: str | None = None) -> tuple[str, str | None]:
    """Run AI inference, return (text, session_id)."""
    backend = detect_backend()
    if backend == "openai":
        return _run_openai(msg)
    elif backend == "claude":
        return _run_claude(msg)
    else:
        return _run_mimo(msg, session_id, file_path)


def _run_mimo(msg: str, session_id: str | None = None, file_path: str | None = None):
    import signal
    env = os.environ.copy()
    env["HOME"] = str(Path.home())
    cmd = [OPENCODE_BIN, "run", "--format", "json"]
    if session_id:
        cmd += ["--session", session_id]
    cmd.append(msg)
    if file_path:
        cmd += ["-f", file_path]
    proc = None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=OPENCODE_DIR, env=env, preexec_fn=os.setsid,
        )
        stdout, stderr = proc.communicate(timeout=MIMO_TIMEOUT)
        if proc.returncode != 0 and not stdout.strip():
            return f"Error: {stderr.strip()}" if stderr.strip() else "(no output)", session_id
        texts, sid = [], session_id
        for line in stdout.splitlines():
            try:
                ev = json.loads(line.strip())
            except ValueError:
                continue
            if ev.get("type") == "text":
                t = ev.get("part", {}).get("text", "")
                if t:
                    texts.append(t)
            if ev.get("type") == "error":
                return f"Error: {ev.get('error', {}).get('message', 'unknown')}", session_id
            if not sid:
                sid = ev.get("sessionID")
        return "\n".join(texts) if texts else "(no output)", sid
    except subprocess.TimeoutExpired:
        if proc:
            try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError: pass
        return "(timeout >5min)", session_id
    except Exception as e:
        if proc:
            try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError: pass
        return f"Error: {e}", session_id


def _run_openai(msg: str, session_id: str | None = None):
    try:
        import httpx
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": msg}]},
            timeout=60,
        )
        return r.json()["choices"][0]["message"]["content"], session_id
    except Exception as e:
        return f"Error: {e}", session_id


def _run_claude(msg: str, session_id: str | None = None):
    try:
        import httpx
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
            },
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "messages": [{"role": "user", "content": msg}]},
            timeout=60,
        )
        return r.json()["content"][0]["text"], session_id
    except Exception as e:
        return f"Error: {e}", session_id
