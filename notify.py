# -*- coding: utf-8 -*-
"""
notify.py — ส่งการแจ้งเตือนเข้า Discord ผ่าน Webhook

ใช้ได้ 2 แบบ:
  1) เป็น Claude Code hook (อ่าน JSON payload จาก stdin อัตโนมัติ):
       python notify.py --event stop
       python notify.py --event notification
  2) เรียกเองจากคอมมานด์ไลน์:
       python notify.py --event error --text "ข้อความ error"
       python notify.py --text "ข้อความอะไรก็ได้"
       python notify.py --test          # ทดสอบว่า webhook ถูกต้อง

การตั้งค่า (เลือกอย่างใดอย่างหนึ่ง):
  - แก้ไฟล์ notify_config.json ที่อยู่ข้าง ๆ สคริปต์นี้ (แนะนำ), หรือ
  - กำหนด environment variable: DISCORD_WEBHOOK_URL
"""

import sys
import os
import re
import json
import argparse
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ให้ข้อความภาษาไทยที่ print ออก console อ่านออก (Windows codepage มักไม่ใช่ UTF-8)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "notify_config.json"
LOG_PATH = HERE / "notify.log"

# สี embed แยกตามเหตุการณ์ (ค่า decimal ของสี Discord)
COLORS = {
    "stop": 0x2ECC71,          # เขียว = งานเสร็จ
    "notification": 0xF1C40F,  # เหลือง = รอคุณตอบ
    "permission": 0xE67E22,    # ส้มเข้ม = ขอ permission
    "error": 0xE74C3C,         # แดง = error
    "test": 0x3498DB,          # ฟ้า = ทดสอบ
    "ask": 0xF39C12,           # ส้ม = มีคำถาม
    "plan": 0x9B59B6,          # ม่วง = เสนอแผน
    "manual": 0x95A5A6,        # เทา = อื่น ๆ
}
TITLES = {
    "stop": "✅ Claude ทำงานเสร็จแล้ว",
    "notification": "🔔 Claude ต้องการให้คุณตอบ/ยืนยัน",
    "permission": "🔐 Claude ขอ permission — รอคุณอนุมัติ",
    "error": "⛔ เกิด error",
    "test": "🧪 ทดสอบการเชื่อมต่อ Discord สำเร็จ",
    "ask": "❓ Claude มีคำถามให้คุณตอบ",
    "plan": "📋 Claude เสนอแผน รออนุมัติ",
    "manual": "🔔 Claude แจ้งเตือน",
}
# สถานะภาษาไทยสั้น ๆ ใช้เป็น fallback ของ "สรุป" เมื่อไม่มีเนื้อหา
# หรือใช้เกริ่นนำเมื่อเนื้อหาที่ดึงมาไม่มีภาษาไทยเลย
STATUS_TH = {
    "stop": "งานเสร็จแล้ว",
    "notification": "รอคุณตอบ/ยืนยัน",
    "permission": "รอคุณอนุมัติ permission",
    "error": "เกิดข้อผิดพลาด",
    "test": "ทดสอบสำเร็จ",
    "ask": "มีคำถามรอคุณตอบ",
    "plan": "รออนุมัติแผน",
    "manual": "แจ้งเตือน",
}

# ---- ภาษาอังกฤษ (ใช้เมื่อ config teams_language = "en") ----
TITLES_EN = {
    "stop": "✅ Claude finished the task",
    "notification": "🔔 Claude needs your input",
    "permission": "🔐 Claude requests permission",
    "error": "⛔ An error occurred",
    "test": "🧪 Connection test succeeded",
    "ask": "❓ Claude has a question for you",
    "plan": "📋 Claude proposed a plan — awaiting approval",
    "manual": "🔔 Claude notification",
}
STATUS_EN = {
    "stop": "Task finished",
    "notification": "Awaiting your input",
    "permission": "Awaiting permission approval",
    "error": "An error occurred",
    "test": "Test succeeded",
    "ask": "You have a question to answer",
    "plan": "Plan awaiting approval",
    "manual": "Notification",
}
# ป้ายฟิลด์ในการ์ด แยกตามภาษา (สรุป / โปรเจกต์ / เวลา / ผู้ส่ง)
LABELS = {
    "th": {"summary": "สรุป", "project": "Project", "time": "เวลา", "from": "From"},
    "en": {"summary": "Summary", "project": "Project", "time": "Time", "from": "From"},
}


def _norm_lang(v, default="th"):
    """normalize ค่า config ภาษา → "th" หรือ "en" (รับ th/thai/en/english ฯลฯ)"""
    v = (v or "").strip().lower()
    if v in ("en", "eng", "english"):
        return "en"
    if v in ("th", "tha", "thai"):
        return "th"
    return default


def _title(event, lang="th"):
    table = TITLES_EN if lang == "en" else TITLES
    return table.get(event, table["manual"])


def _status(event, lang="th"):
    table = STATUS_EN if lang == "en" else STATUS_TH
    return table.get(event, table["manual"])


def _has_thai(s):
    """มีอักษรไทยอย่างน้อยหนึ่งตัวไหม"""
    return any("฀" <= ch <= "๿" for ch in s)


def _clean_md(line):
    """ตัด markdown ทั่วไปออกจาก 1 บรรทัด ให้เหลือข้อความอ่านง่าย"""
    s = line.strip()
    s = re.sub(r"^#{1,6}\s*", "", s)          # หัวข้อ #, ##
    s = re.sub(r"^>\s?", "", s)               # blockquote
    s = re.sub(r"^[-*+]\s+", "", s)           # bullet
    s = re.sub(r"^\d+[.)]\s+", "", s)         # ลำดับเลข 1. 2)
    s = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", s)      # inline/`code`
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)          # **bold**
    s = re.sub(r"__([^_]+)__", r"\1", s)              # __bold__
    s = re.sub(r"\*([^*]+)\*", r"\1", s)              # *italic*
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)    # [text](url) -> text
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def short_summary(event, body, limit=200, lang="th"):
    """สร้างข้อความสรุปสั้น ๆ ว่า 'สรุปเป็นยังไง' (heuristic ไม่พึ่ง AI)

    - ดึงเนื้อหาต้น ๆ ของ body มาตัด markdown แล้วย่อให้สั้น
    - ถ้าไม่มีเนื้อหา ใช้คำสถานะตาม event ในภาษาที่เลือก
    - โหมดไทย: ถ้าเนื้อหาไม่มีภาษาไทยเลย เติมสถานะไทยนำหน้าให้ "รู้สึกเป็นไทย"
    - โหมดอังกฤษ: คืน gist ตามจริง (เส้นทางหลักของ event stop ใช้ AI แปลเป็น
      อังกฤษให้อยู่แล้ว; heuristic เป็น fallback จึงไม่ฝืนแปลเนื้อหาเอง)
    """
    status = _status(event, lang)
    if not body:
        return status

    lines = [_clean_md(ln) for ln in body.splitlines()]
    gist = " ".join(ln for ln in lines if ln).strip()
    if not gist:
        return status

    if len(gist) > limit:
        cut = gist[:limit].rstrip()
        sp = cut.rfind(" ")
        if sp > limit * 0.6:           # ถอยไปตัดที่ช่องว่างล่าสุด กันคำขาดกลางคำ
            cut = cut[:sp].rstrip()
        gist = cut + "…"

    if lang != "en" and not _has_thai(gist):   # เนื้อหาอังกฤษล้วน (โหมดไทย) -> เติมไทยนำหน้า
        return f"{status}: {gist}"
    return gist


def log(msg):
    """เขียน log ลงไฟล์ (hook ทำงานเงียบ ๆ จึงต้อง log ไว้ดีบั๊ก)"""
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_config():
    """อ่านค่าตั้งจาก notify_config.json (+ env override) คืนเป็น dict"""
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"อ่าน config ไม่ได้: {e}")

    webhook = (cfg.get("webhook_url") or "").strip()
    # environment variable มีสิทธิ์เหนือกว่าไฟล์ config
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", webhook).strip()

    api_key = (cfg.get("anthropic_api_key") or "").strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY", api_key).strip()

    oauth_token = (cfg.get("oauth_token") or "").strip()
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", oauth_token).strip()

    teams = (cfg.get("teams_webhook_url") or "").strip()
    teams = os.environ.get("TEAMS_WEBHOOK_URL", teams).strip()

    # ภาษาข้อความที่ส่งเข้า Teams: "en" (ดีฟอลต์) หรือ "th"
    teams_language = _norm_lang(
        os.environ.get("TEAMS_LANGUAGE", cfg.get("teams_language", "")), "en"
    )

    return {
        "webhook_url": webhook,
        "teams_webhook_url": teams,
        "teams_language": teams_language,
        "anthropic_api_key": api_key,
        "oauth_token": oauth_token,
        # ขอ token สดจาก `ant auth print-credentials` ตอนเรียก (auto-refresh)
        "oauth_from_ant": bool(cfg.get("oauth_from_ant", False)),
        # ดึง token จาก Claude Code login (~/.claude/.credentials.json) ที่ login ไว้แล้ว
        "oauth_from_claude_code": bool(cfg.get("oauth_from_claude_code", False)),
        # สรุปด้วย AI เมื่อมี key/token (ปิดได้ด้วย "ai_summary": false)
        "ai_summary": bool(cfg.get("ai_summary", True)),
        # แท็ก @ ตอน event สำคัญ ให้มือถือเด้งชัด (default: error + ตอนรอคุณ)
        "mention_user_id": (cfg.get("mention_user_id") or "").strip(),
        "mention_events": cfg.get(
            "mention_events",
            ["stop", "error", "ask", "plan", "notification", "permission"],
        ),
        # Teams @mention: id = email/UPN หรือ AAD object id, name = ชื่อที่โชว์ในแท็ก
        "teams_mention_id": (cfg.get("teams_mention_id") or "").strip(),
        "teams_mention_name": (cfg.get("teams_mention_name") or "").strip(),
        # ชื่อผู้ส่ง โชว์ช่อง "From" (ห้องรวมหลายคนจะได้รู้ว่าอันไหนของใคร)
        "sender_name": (cfg.get("sender_name") or "").strip(),
    }


def user_settings_path():
    """path ของ settings.json ระดับ user (ใช้ได้ทุกโปรเจกต์)"""
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return Path(home) / ".claude" / "settings.json"


def _load_settings(path):
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            return json.loads(raw)
    return {}


# hook events ที่สคริปต์นี้ดูแล (ใช้ทั้งตอน install / uninstall)
HOOK_EVENTS = ("Stop", "Notification", "PermissionRequest", "PreToolUse")


def install_hooks(path=None):
    """ติดตั้ง hook ลง user-level settings.json (merge ไม่ทับของเดิม)

    - Stop              → งานเสร็จ
    - Notification      → รอ input/idle (ยิงเฉพาะ CLI; ใบที่เป็นเรื่อง permission
                          สคริปต์ข้ามให้ เพราะ PermissionRequest ครอบคลุมแล้ว)
    - PermissionRequest → Claude ขอ permission — ยิงจาก engine โดยตรง จึงเด้งแม้ใน
      desktop app / VS Code ที่ hook Notification ไม่ทำงาน (ต้อง Claude Code ≥ 2.1.x)
    - PreToolUse (AskUserQuestion|ExitPlanMode) → ตอน Claude ถาม/เสนอแผน
      (สำคัญ: Notification hook ของ Claude Code ไม่ยิงให้ AskUserQuestion
       จึงต้องดักที่ PreToolUse แทน — passive ไม่บล็อก tool)
    อ้าง path ของ notify.py ตามเครื่องปัจจุบัน จึงย้ายไปเครื่องอื่นได้
    """
    path = path or user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_settings(path)

    script = str(HERE / "notify.py")
    hooks = data.setdefault("hooks", {})
    # (event_name, matcher, event_arg, statusMessage)
    specs = [
        ("Stop", None, "stop", "แจ้งเตือน Discord (งานเสร็จ)"),
        ("Notification", None, "notification", "แจ้งเตือน Discord (รอ input)"),
        ("PermissionRequest", None, "permission", "แจ้งเตือน Discord (ขอ permission)"),
        ("PreToolUse", "AskUserQuestion|ExitPlanMode", None,
         "แจ้งเตือน Discord (มีคำถาม/แผน)"),
    ]
    for event_name, matcher, arg, status_msg in specs:
        cmd = {
            "type": "command",
            "command": "python",
            # ไม่ใส่ --event → ให้ derive จาก payload (PreToolUse รวม 2 tool)
            "args": [script] if arg is None else [script, "--event", arg],
            "timeout": 30,
            "statusMessage": status_msg,
        }
        entry = {"hooks": [cmd]}
        if matcher:
            entry["matcher"] = matcher

        lst = hooks.get(event_name)
        if not isinstance(lst, list):
            lst = []
        # เอา hook เดิมที่อ้างถึง notify.py ออกก่อน (กันซ้ำ / อัปเดต path+timeout)
        lst = [h for h in lst if "notify.py" not in json.dumps(h, ensure_ascii=False)]
        lst.append(entry)
        hooks[event_name] = lst

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def uninstall_hooks(path=None):
    """ถอนเฉพาะ hook ที่อ้างถึง notify.py ออกจาก user-level settings.json"""
    path = path or user_settings_path()
    data = _load_settings(path)
    hooks = data.get("hooks", {})
    for event_name in HOOK_EVENTS:
        lst = hooks.get(event_name)
        if isinstance(lst, list):
            lst = [h for h in lst if "notify.py" not in json.dumps(h, ensure_ascii=False)]
            if lst:
                hooks[event_name] = lst
            else:
                hooks.pop(event_name, None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_stdin_json():
    """อ่าน JSON payload ที่ Claude Code ส่งมาทาง stdin (ถ้ามี)

    อ่านเป็น bytes แล้ว decode UTF-8 เอง — กัน codec ของ Windows (cp874 ฯลฯ)
    ทำ payload ภาษาไทยเพี้ยนเป็น surrogate จนตอน encode ส่งเข้า Discord ไม่ได้
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        buf = getattr(sys.stdin, "buffer", None)
        raw = buf.read() if buf is not None else sys.stdin.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if not raw or not raw.strip():
            return {}
        return json.loads(raw)
    except Exception as e:
        log(f"อ่าน stdin ไม่ได้: {e}")
        return {}


def project_name(payload):
    cwd = payload.get("cwd") or os.getcwd()
    try:
        return Path(cwd).name or str(cwd)
    except Exception:
        return str(cwd)


def transcript_preview(payload, limit=1000):
    """ดึงข้อความล่าสุดของ Claude จาก transcript มาเป็นตัวอย่างสรุป (best-effort)"""
    path = payload.get("transcript_path")
    if not path:
        return ""
    try:
        p = Path(path)
        if not p.exists():
            return ""
        last_text = ""
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                role = obj.get("type") or obj.get("role")
                if role != "assistant":
                    continue
                msg = obj.get("message", obj)
                content = msg.get("content") if isinstance(msg, dict) else None
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    text = "\n".join(parts).strip()
                if text:
                    last_text = text
        last_text = last_text.strip()
        if len(last_text) > limit:
            last_text = last_text[:limit].rstrip() + "…"
        return last_text
    except Exception as e:
        log(f"อ่าน transcript ไม่ได้: {e}")
        return ""


def resolve_body(event, text, payload):
    if text:
        return text
    if event == "stop":
        return transcript_preview(payload)
    if event == "ask":  # PreToolUse ของ AskUserQuestion → ดึงคำถามมาโชว์
        ti = payload.get("tool_input") or {}
        qs = ti.get("questions")
        if isinstance(qs, list) and qs:
            return "\n".join(
                q.get("question", "") for q in qs if isinstance(q, dict)
            ).strip()
        return ti.get("question") or payload.get("message", "")
    if event == "plan":  # PreToolUse ของ ExitPlanMode → ดึงแผน
        ti = payload.get("tool_input") or {}
        return ti.get("plan") or payload.get("message", "")
    if event == "permission":  # PermissionRequest → บอกว่า tool ไหนกำลังจะทำอะไร
        tool = payload.get("tool_name") or ""
        ti = payload.get("tool_input") or {}
        detail = ""
        if isinstance(ti, dict):
            for key in ("command", "file_path", "url", "prompt", "description"):
                v = ti.get(key)
                if isinstance(v, str) and v.strip():
                    detail = v.strip()
                    break
            if not detail and ti:
                detail = json.dumps(ti, ensure_ascii=False)
        got = f"{tool}: {detail}" if (tool and detail) else (tool or detail)
        return got or payload.get("message", "")
    if event in ("notification", "error"):
        return payload.get("message", "")
    if event == "test":
        return "ถ้าคุณเห็นข้อความนี้ แปลว่าตั้งค่าถูกต้องแล้ว 🎉"
    return ""


def derive_event(cli_event, payload):
    """แปลง (--event, payload จาก hook) → ชื่อ event ภายใน (stop/ask/plan/permission/…)"""
    event = (cli_event or payload.get("hook_event_name") or "").lower()
    if event == "subagentstop":
        event = "stop"
    if event == "permissionrequest":  # hook PermissionRequest → ขอ permission
        event = "permission"
    if event == "pretooluse":
        # Notification hook ไม่ยิงให้ AskUserQuestion — เราดักที่ PreToolUse แทน
        tool = (payload.get("tool_name") or "").lower()
        event = {"askuserquestion": "ask", "exitplanmode": "plan"}.get(tool, "notification")
    return event


def should_skip(event, payload):
    """event ที่มี hook อื่นครอบคลุมอยู่แล้ว → ข้าม กันเด้งซ้ำ (คืนเหตุผล หรือ None)

    ใน CLI ตอน permission dialog ขึ้น จะยิงทั้ง Notification (ข้อความ
    "Claude needs your permission to use X") และ PermissionRequest —
    ฝั่ง PermissionRequest ให้รายละเอียดดีกว่า (รู้ tool + คำสั่ง) จึงเก็บอันนั้นไว้
    """
    if event == "notification" and "permission" in (payload.get("message") or "").lower():
        return "notification เรื่อง permission — PermissionRequest hook ดูแลอยู่แล้ว"
    return None


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
# Haiku: ถูก+เร็ว เหมาะกับสรุปสั้น (hook มี timeout จำกัด)
SUMMARY_MODEL = "claude-haiku-4-5"


def _ant_token():
    """ขอ access token สด ๆ จาก `ant auth print-credentials --access-token`

    เป็นวิธี OAuth ที่ auto-refresh (ต้องลง ant CLI + `ant auth login` มาก่อน)
    """
    try:
        out = subprocess.run(
            ["ant", "auth", "print-credentials", "--access-token"],
            capture_output=True, text=True, timeout=10,
        )
        return (out.stdout or "").strip()
    except Exception as e:
        log(f"ขอ ant token ไม่ได้: {e}")
        return ""


def _find_access_token(obj):
    """หา accessToken จาก JSON โครงสร้างไหนก็ได้ (best-effort, ไม่แตะ refreshToken)"""
    if isinstance(obj, dict):
        for k in ("accessToken", "access_token"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in obj.values():
            t = _find_access_token(v)
            if t:
                return t
    elif isinstance(obj, list):
        for v in obj:
            t = _find_access_token(v)
            if t:
                return t
    return ""


def _claude_code_token(path=None):
    """อ่าน OAuth access token จาก credential store ของ Claude Code (ที่ login ไว้)

    best-effort: ไฟล์ไม่มี/อ่านไม่ได้ → คืน "" (ให้ fallback).
    หมายเหตุ: token นี้เป็นของ subscription อาจถูก /v1/messages ปฏิเสธ หรือหมดอายุ
    ได้ — ถ้าพลาด ai_summary จะ fallback ไปสรุปแบบตัดคำเอง
    """
    try:
        if path is None:
            home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
            path = Path(home) / ".claude" / ".credentials.json"
        path = Path(path)
        if not path.exists():
            return ""
        return _find_access_token(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        log(f"อ่าน claude code token ไม่ได้: {e}")
        return ""


def resolve_auth(config):
    """เลือกวิธี auth เรียก Anthropic API — คืน (scheme, token)

    ลำดับ: oauth_token > anthropic_api_key > oauth_from_ant > oauth_from_claude_code
    - "bearer"    = OAuth (ต้องแนบ header anthropic-beta: oauth-2025-04-20)
    - "x-api-key" = API key ปกติ (ถาวร)
    """
    config = config or {}
    oauth = (config.get("oauth_token") or "").strip()
    if oauth:
        return "bearer", oauth
    api_key = (config.get("anthropic_api_key") or "").strip()
    if api_key:
        return "x-api-key", api_key
    if config.get("oauth_from_ant"):
        tok = _ant_token()
        if tok:
            return "bearer", tok
    if config.get("oauth_from_claude_code"):
        tok = _claude_code_token()
        if tok:
            return "bearer", tok
    return None, ""


def ai_summary(body, auth, timeout=6, lang="th"):
    """เรียก Claude (Haiku) สรุป 1-2 ประโยค — คืน None ถ้าพลาด (ให้ fallback)

    lang = "th" (ดีฟอลต์) หรือ "en" กำหนดภาษาของบทสรุปที่ให้ AI ตอบกลับ
    auth = (scheme, token) โดย scheme เป็น "bearer" (OAuth) หรือ "x-api-key"
    ใช้ urllib ล้วน ไม่พึ่ง SDK เพื่อคงสภาพ zero-dependency ของโปรเจกต์
    """
    scheme, token = auth
    if not token:
        return None
    if lang == "en":
        system = (
            "You summarize Claude Code's work for the user. "
            "Summarize the message below in English in 1-2 short sentences "
            "(around 120 characters), focusing on what was accomplished or what "
            "problem was hit. Reply with only the summary — no preamble, no markdown."
        )
    else:
        system = (
            "คุณคือผู้ช่วยสรุปงานของ Claude Code ให้ผู้ใช้ชาวไทย "
            "สรุปข้อความต่อไปนี้เป็นภาษาไทยสั้น ๆ ไม่เกิน 1-2 ประโยค (ราว 120 ตัวอักษร) "
            "เน้นใจความว่าทำอะไรเสร็จหรือติดปัญหาอะไร "
            "ตอบเฉพาะบทสรุปล้วน ๆ ห้ามมีคำนำ ห้ามใช้ markdown"
        )
    headers = {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if scheme == "bearer":
        # OAuth token: ใช้ Authorization: Bearer + ต้องมี beta header นี้
        headers["authorization"] = f"Bearer {token}"
        headers["anthropic-beta"] = "oauth-2025-04-20"
    else:
        headers["x-api-key"] = token
    req_obj = {
        "model": SUMMARY_MODEL,
        "max_tokens": 200,
        "system": system,
        "messages": [{"role": "user", "content": body[:4000]}],
    }
    try:
        data = json.dumps(req_obj, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            ANTHROPIC_API_URL, data=data, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8", "replace"))
        parts = [
            b.get("text", "")
            for b in obj.get("content", [])
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        summary = " ".join(parts).strip()
        return summary or None
    except Exception as e:
        log(f"ai_summary ล้มเหลว: {e}")
        return None


def resolve_summary(event, body, config, lang="th"):
    """เลือกวิธีสรุป: ใช้ AI เฉพาะตอนงานเสร็จ (stop) + มี auth + เนื้อหายาวพอ

    lang = "th" (ดีฟอลต์) หรือ "en" — ส่งต่อให้ทั้ง AI และ heuristic
    เหตุการณ์อื่น (ask/plan/notification/error) ใช้ heuristic เร็ว ๆ ไม่หน่วง
    (PreToolUse ยิงก่อน tool ทำงาน จึงไม่อยากให้ช้าเพราะรอ API)
    """
    config = config or {}
    use_ai = config.get("ai_summary", True)
    if event == "stop" and body and use_ai and len(body) > 160:
        auth = resolve_auth(config)
        if auth[1]:
            s = ai_summary(body, auth, lang=lang)
            if s:
                return s
    return short_summary(event, body, lang=lang)


def build_payload(event, text, payload, config=None, summary=None):
    config = config or {}
    proj = project_name(payload)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if summary is None:  # main คำนวณครั้งเดียวแล้วส่งมา (กัน AI ยิงซ้ำหลายช่องทาง)
        summary = resolve_summary(event, resolve_body(event, text, payload), config)

    fields = [
        {"name": "📁 Project", "value": proj, "inline": True},
        {"name": "🕒 เวลา", "value": ts, "inline": True},
    ]
    sender = config.get("sender_name")
    if sender:  # ห้องรวมหลายคน: บอกว่าอันนี้ของใคร
        fields.append({"name": "👤 From", "value": sender, "inline": True})

    # เอาแค่สรุปสั้น 1 ย่อหน้า ไม่ดั๊มพ์ข้อความเต็ม (เยอะเกินไป อ่านยากบนมือถือ)
    embed = {
        "title": TITLES.get(event, TITLES["manual"]),
        "color": COLORS.get(event, COLORS["manual"]),
        "description": f"📝 **สรุป:** {summary}",
        "fields": fields,
    }
    data = {"username": "Claude Code", "embeds": [embed]}

    # แท็ก @ เฉพาะ event สำคัญ ให้มือถือเด้งแรง (ต้องตั้ง mention_user_id ก่อน)
    mention_id = config.get("mention_user_id")
    if mention_id and event in config.get("mention_events", []):
        data["content"] = f"<@{mention_id}> {TITLES.get(event, TITLES['manual'])}"
        data["allowed_mentions"] = {"parse": ["users"]}
    return data


# สี Adaptive Card ของ Teams (มีชุดจำกัด ไม่ใช่ hex อิสระแบบ Discord)
TEAMS_COLORS = {
    "stop": "good", "notification": "warning", "permission": "warning",
    "error": "attention", "test": "accent", "ask": "warning", "plan": "accent",
    "manual": "default",
}


def build_teams_payload(event, text, payload, config=None, summary=None, lang=None):
    """สร้าง payload ให้ Microsoft Teams (Adaptive Card ผ่าน Workflows webhook)

    lang = "th"/"en" ควบคุมภาษาการ์ด (หัวข้อ/ป้าย/สรุป); None = อ่านจาก
    config["teams_language"] (ดีฟอลต์ en) ให้เรียกแบบ standalone ได้ด้วย
    """
    config = config or {}
    if lang is None:
        lang = _norm_lang(config.get("teams_language"), "en")
    proj = project_name(payload)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if summary is None:
        summary = resolve_summary(event, resolve_body(event, text, payload), config, lang)

    labels = LABELS["en"] if lang == "en" else LABELS["th"]
    facts = [
        {"title": f"📁 {labels['project']}", "value": proj},
        {"title": f"🕒 {labels['time']}", "value": ts},
    ]
    sender = config.get("sender_name")
    if sender:  # ห้องรวมหลายคน: บอกว่าอันนี้ของใคร
        facts.append({"title": f"👤 {labels['from']}", "value": sender})

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            # แถบหัวมีพื้นหลังสีตามสถานะ (bleed = ขยายเต็มขอบการ์ด) เห็นสถานะปราดเดียว
            {"type": "Container", "style": TEAMS_COLORS.get(event, "default"),
             "bleed": True, "items": [
                {"type": "TextBlock", "text": _title(event, lang),
                 "weight": "Bolder", "size": "Medium", "wrap": True},
            ]},
            {"type": "TextBlock", "text": f"📝 **{labels['summary']}:** {summary}", "wrap": True},
            {"type": "FactSet", "facts": facts},
        ],
    }
    # แท็ก @ คนเดียว (Teams) → คนนั้นเด้งเตือนแม้ mute channel ไว้; คนอื่นไม่โดน
    mention_id = config.get("teams_mention_id")
    if mention_id and event in config.get("mention_events", []):
        name = config.get("teams_mention_name") or mention_id
        tag = f"<at>{name}</at>"
        # ใส่บรรทัดแท็กไว้ใต้หัวข้อ + ผูก entity ให้ Teams รู้ว่า tag ใคร
        card["body"].insert(1, {"type": "TextBlock", "text": tag, "wrap": True})
        card["msteams"] = {"entities": [{
            "type": "mention",
            "text": tag,
            "mentioned": {"id": mention_id, "name": name},
        }]}

    # ห่อแบบ Workflows/Power Automate ("Post to a channel when a webhook request is received")
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }


def _retry_after(err):
    """อ่านวินาทีที่ควรรอจาก header Retry-After (ถ้ามี)"""
    try:
        ra = err.headers.get("Retry-After") if getattr(err, "headers", None) else None
        return float(ra) if ra else 0.0
    except Exception:
        return 0.0


def send(webhook_url, data_obj, retries=2):
    """POST เข้า webhook + retry ตอนเจอ 429/5xx/เน็ตสะดุด

    backoff แบบ exponential และเคารพ header Retry-After; 4xx อื่นโยน error เลย
    (ช่วยกันแจ้งเตือนหายเวลา Discord/Power Automate rate-limit หรือเน็ตกระตุก)
    """
    data = json.dumps(data_obj, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        # Discord/Cloudflare บล็อก UA เริ่มต้นของ Python (error 1010) จึงต้องตั้งเอง
        "User-Agent": "ClaudeCodeNotifier/1.0 (+https://claude.com/claude-code)",
    }
    for attempt in range(retries + 1):
        req = urllib.request.Request(webhook_url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if attempt >= retries or not (e.code == 429 or e.code >= 500):
                raise  # หมด retry หรือเป็น 4xx อื่น (URL ผิด/ถูกลบ) → โยนเลย
            wait = _retry_after(e) or (2 ** attempt)
            log(f"retry {attempt + 1}/{retries} หลัง HTTP {e.code} (รอ ~{min(wait, 8):.0f}s)")
            time.sleep(min(wait, 8))
        except urllib.error.URLError as e:
            if attempt >= retries:
                raise
            log(f"retry {attempt + 1}/{retries} หลังเน็ตสะดุด: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError("send: หมด retry ผิดปกติ")  # กันไว้ (ปกติ return/raise ในลูปแล้ว)


def main():
    ap = argparse.ArgumentParser(description="ส่งการแจ้งเตือนเข้า Discord")
    ap.add_argument("--event", default=None,
                    help="stop | notification | permission | error | test")
    ap.add_argument("--text", default=None, help="ข้อความที่อยากส่ง")
    ap.add_argument("--test", action="store_true", help="ส่งข้อความทดสอบ")
    ap.add_argument("--install-hooks", action="store_true",
                    help="ติดตั้ง hook แจ้งเตือน (Stop/Notification/PermissionRequest/"
                         "PreToolUse) ลง user-level settings.json")
    ap.add_argument("--uninstall-hooks", action="store_true",
                    help="ถอน hook ของสคริปต์นี้ออกจาก user-level settings.json")
    ap.add_argument("positional", nargs="*", help="ข้อความ (แบบไม่ต้องใส่ --text)")
    args = ap.parse_args()

    if args.install_hooks:
        try:
            path = install_hooks()
        except Exception as e:
            print(f"⛔ ติดตั้ง hook ไม่สำเร็จ: {e}", file=sys.stderr)
            return 1
        print("✅ ติดตั้ง hook ระดับ user (ใช้ได้ทุกโปรเจกต์) เรียบร้อย")
        print(f"   ไฟล์: {path}")
        print("   • Stop              → แจ้งเตือนตอน Claude ทำงานเสร็จ")
        print("   • Notification      → แจ้งเตือนตอน Claude รอ input (CLI)")
        print("   • PermissionRequest → แจ้งเตือนตอน Claude ขอ permission")
        print("   • PreToolUse        → แจ้งเตือนตอน Claude ถามคำถาม/เสนอแผน")
        print()
        print("⚠️  รีสตาร์ต Claude Code (หรือเปิดเมนู /hooks หนึ่งครั้ง) เพื่อให้ hook มีผล")
        return 0

    if args.uninstall_hooks:
        try:
            path = uninstall_hooks()
        except Exception as e:
            print(f"⛔ ถอน hook ไม่สำเร็จ: {e}", file=sys.stderr)
            return 1
        print(f"✅ ถอน hook ของสคริปต์นี้ออกจาก user-level แล้ว: {path}")
        return 0

    payload = read_stdin_json()
    is_hook = bool(payload) and not args.test

    event = derive_event(args.event, payload)
    if args.test:
        event = "test"
    if not event:
        event = "manual"

    skip = should_skip(event, payload)
    if skip:
        log(f"ข้าม event={event}: {skip}")
        return 0

    text = args.text
    if text is None and args.positional:
        text = " ".join(args.positional)

    config = load_config()

    def _valid_url(u):
        return bool(u) and u.startswith("https://") and not u.startswith("<")

    # คำนวณสรุป "ครั้งเดียวต่อภาษา" แล้วแคชไว้ — ถ้าทุกช่องภาษาเดียวกันก็ใช้ร่วม
    # (กัน AI ยิงซ้ำ); Teams เลือกภาษาได้ผ่าน teams_language ส่วน Discord เป็นไทย
    body = resolve_body(event, text, payload)
    discord_lang = "th"
    teams_lang = _norm_lang(config.get("teams_language"), "en")
    _summaries = {}

    def summary_for(lang):
        if lang not in _summaries:
            _summaries[lang] = resolve_summary(event, body, config, lang)
        return _summaries[lang]

    channels = []
    if _valid_url(config.get("webhook_url")):
        channels.append((
            "Discord", config["webhook_url"],
            build_payload(event, text, payload, config, summary=summary_for(discord_lang)),
        ))
    if _valid_url(config.get("teams_webhook_url")):
        channels.append((
            "Teams", config["teams_webhook_url"],
            build_teams_payload(event, text, payload, config,
                                summary=summary_for(teams_lang), lang=teams_lang),
        ))

    if not channels:
        log(f"config ยังไม่ครบ (event={event}) — ข้ามการส่ง")
        if is_hook:
            return 0  # อย่าทำให้ hook ล้ม
        print(
            "⛔ ยังไม่ได้ตั้งค่า webhook (Discord/Teams) ใน notify_config.json",
            file=sys.stderr,
        )
        return 2

    # ส่งทุกช่องทางแบบอิสระ — ช่องนึงล้มไม่กระทบอีกช่อง
    ok_any = False
    for name, url, data_obj in channels:
        try:
            status, _ = send(url, data_obj)
            log(f"ส่งสำเร็จ event={event} ({name}) status={status}")
            ok_any = True
            if not is_hook:
                print(f"✅ ส่ง {name} สำเร็จ (status={status})")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", "replace")
            log(f"ส่งไม่สำเร็จ event={event} ({name}) HTTP {e.code}: {err_body}")
            if not is_hook:
                print(f"⛔ {name} error HTTP {e.code}: {err_body}", file=sys.stderr)
        except Exception as e:
            log(f"ส่งไม่สำเร็จ event={event} ({name}): {e}")
            if not is_hook:
                print(f"⛔ {name} ส่งไม่สำเร็จ: {e}", file=sys.stderr)
    return 0 if (is_hook or ok_any) else 1


if __name__ == "__main__":
    sys.exit(main())
