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
    "error": 0xE74C3C,         # แดง = error
    "test": 0x3498DB,          # ฟ้า = ทดสอบ
    "manual": 0x95A5A6,        # เทา = อื่น ๆ
}
TITLES = {
    "stop": "✅ Claude ทำงานเสร็จแล้ว",
    "notification": "🔔 Claude ต้องการให้คุณตอบ/ยืนยัน",
    "error": "⛔ เกิด error",
    "test": "🧪 ทดสอบการเชื่อมต่อ Discord สำเร็จ",
    "manual": "🔔 Claude แจ้งเตือน",
}
# สถานะภาษาไทยสั้น ๆ ใช้เป็น fallback ของ "สรุป" เมื่อไม่มีเนื้อหา
# หรือใช้เกริ่นนำเมื่อเนื้อหาที่ดึงมาไม่มีภาษาไทยเลย
STATUS_TH = {
    "stop": "งานเสร็จแล้ว",
    "notification": "รอคุณตอบ/ยืนยัน",
    "error": "เกิดข้อผิดพลาด",
    "test": "ทดสอบสำเร็จ",
    "manual": "แจ้งเตือน",
}


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


def short_summary(event, body, limit=200):
    """สร้างข้อความสรุปสั้น ๆ (เน้นภาษาไทย) ว่า 'สรุปเป็นยังไง'

    - ดึงเนื้อหาต้น ๆ ของ body มาตัด markdown แล้วย่อให้สั้น
    - ถ้าไม่มีเนื้อหา ใช้สถานะภาษาไทยตาม event
    - ถ้าเนื้อหาไม่มีภาษาไทยเลย เติมสถานะไทยนำหน้าให้เสมอ
    """
    status = STATUS_TH.get(event, STATUS_TH["manual"])
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

    if not _has_thai(gist):            # เนื้อหาเป็นภาษาอังกฤษล้วน -> เติมไทยนำหน้า
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
    url = ""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            url = (data.get("webhook_url") or "").strip()
        except Exception as e:
            log(f"อ่าน config ไม่ได้: {e}")
    # environment variable มีสิทธิ์เหนือกว่าไฟล์ config
    url = os.environ.get("DISCORD_WEBHOOK_URL", url).strip()
    return url


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


def install_hooks():
    """ติดตั้ง Stop + Notification hook ลง user-level settings.json

    merge กับของเดิม (เช่น hook อื่น / ค่า theme) ไม่เขียนทับทั้งไฟล์
    และอ้าง path ของ notify.py ตามเครื่องปัจจุบัน จึงย้ายไปเครื่องอื่นได้
    """
    path = user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_settings(path)

    script = str(HERE / "notify.py")
    hooks = data.setdefault("hooks", {})
    specs = [
        ("Stop", "stop", "แจ้งเตือน Discord (งานเสร็จ)"),
        ("Notification", "notification", "แจ้งเตือน Discord (รอคุณตอบ)"),
    ]
    for event_name, arg, status_msg in specs:
        entry = {
            "hooks": [
                {
                    "type": "command",
                    "command": "python",
                    "args": [script, "--event", arg],
                    "timeout": 20,
                    "statusMessage": status_msg,
                }
            ]
        }
        lst = hooks.get(event_name)
        if not isinstance(lst, list):
            lst = []
        # เอา hook เดิมที่อ้างถึง notify.py ออกก่อน (กันซ้ำ / อัปเดต path ให้เป็นของเครื่องนี้)
        lst = [h for h in lst if "notify.py" not in json.dumps(h, ensure_ascii=False)]
        lst.append(entry)
        hooks[event_name] = lst

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def uninstall_hooks():
    """ถอนเฉพาะ hook ที่อ้างถึง notify.py ออกจาก user-level settings.json"""
    path = user_settings_path()
    data = _load_settings(path)
    hooks = data.get("hooks", {})
    for event_name in ("Stop", "Notification"):
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
    """อ่าน JSON payload ที่ Claude Code ส่งมาทาง stdin (ถ้ามี)"""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
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
    if event in ("notification", "error"):
        return payload.get("message", "")
    if event == "test":
        return "ถ้าคุณเห็นข้อความนี้ แปลว่าตั้งค่าถูกต้องแล้ว 🎉"
    return ""


def build_payload(event, text, payload):
    proj = project_name(payload)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = resolve_body(event, text, payload)
    summary = short_summary(event, body)  # สรุปสั้น ๆ ภาษาไทย 1 ย่อหน้า ว่าสรุปเป็นยังไง

    # เอาแค่สรุปสั้น 1 ย่อหน้า ไม่ดั๊มพ์ข้อความเต็ม (เยอะเกินไป อ่านยากบนมือถือ)
    embed = {
        "title": TITLES.get(event, TITLES["manual"]),
        "color": COLORS.get(event, COLORS["manual"]),
        "description": f"📝 **สรุป:** {summary}",
        "fields": [
            {"name": "📁 Project", "value": proj, "inline": True},
            {"name": "🕒 เวลา", "value": ts, "inline": True},
        ],
    }
    return {"username": "Claude Code", "embeds": [embed]}


def send(webhook_url, data_obj):
    data = json.dumps(data_obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            # Discord/Cloudflare บล็อก UA เริ่มต้นของ Python (error 1010) จึงต้องตั้งเอง
            "User-Agent": "ClaudeCodeNotifier/1.0 (+https://claude.com/claude-code)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description="ส่งการแจ้งเตือนเข้า Discord")
    ap.add_argument("--event", default=None, help="stop | notification | error | test")
    ap.add_argument("--text", default=None, help="ข้อความที่อยากส่ง")
    ap.add_argument("--test", action="store_true", help="ส่งข้อความทดสอบ")
    ap.add_argument("--install-hooks", action="store_true",
                    help="ติดตั้ง Stop/Notification hook ลง user-level settings.json")
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
        print("   • Stop         → แจ้งเตือนตอน Claude ทำงานเสร็จ")
        print("   • Notification → แจ้งเตือนตอน Claude รอคุณตอบ/ยืนยัน")
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

    event = (args.event or payload.get("hook_event_name") or "").lower()
    if event == "subagentstop":
        event = "stop"
    if args.test:
        event = "test"
    if not event:
        event = "manual"

    text = args.text
    if text is None and args.positional:
        text = " ".join(args.positional)

    webhook_url = load_config()
    not_configured = (
        not webhook_url
        or webhook_url.startswith("<")
        or not webhook_url.startswith("https://")
    )
    if not_configured:
        log(f"config ยังไม่ครบ (event={event}) — ข้ามการส่ง")
        if is_hook:
            return 0  # อย่าทำให้ hook ล้ม
        print(
            "⛔ ยังไม่ได้ตั้งค่า webhook_url ใน notify_config.json",
            file=sys.stderr,
        )
        return 2

    data_obj = build_payload(event, text, payload)
    try:
        status, body = send(webhook_url, data_obj)
        log(f"ส่งสำเร็จ event={event} status={status}")
        if not is_hook:
            print(f"✅ ส่ง Discord สำเร็จ (status={status})")
        return 0
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")
        log(f"ส่งไม่สำเร็จ event={event} HTTP {e.code}: {err_body}")
        if not is_hook:
            print(f"⛔ Discord error HTTP {e.code}: {err_body}", file=sys.stderr)
        return 0 if is_hook else 1
    except Exception as e:
        log(f"ส่งไม่สำเร็จ event={event}: {e}")
        if not is_hook:
            print(f"⛔ ส่งไม่สำเร็จ: {e}", file=sys.stderr)
        return 0 if is_hook else 1


if __name__ == "__main__":
    sys.exit(main())
