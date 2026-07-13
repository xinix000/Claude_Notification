# Discord Notify สำหรับ Claude Code

แจ้งเตือนเข้า **Discord และ/หรือ Microsoft Teams** อัตโนมัติเมื่อ Claude Code:
- ✅ ทำงานเสร็จ (`Stop`) — สีเขียว
- 🔐 ขอ permission รอคุณอนุมัติ (`PermissionRequest`) — สีส้มเข้ม
- ❓ มีคำถามให้ตอบ (`PreToolUse` / AskUserQuestion) — สีส้ม
- 📋 เสนอแผน รออนุมัติ (`PreToolUse` / ExitPlanMode) — สีม่วง
- 🔔 รออินพุต / idle (`Notification` — ยิงเฉพาะ CLI) — สีเหลือง
- ⛔ เกิด error (เรียกสคริปต์เอง) — สีแดง

> แต่ละการแจ้งเตือนเป็น **📝 สรุปสั้น ๆ ภาษาไทยแค่ 1 ย่อหน้า** อ่านปราดเดียวรู้เรื่อง — ไม่ดั๊มพ์ข้อความเต็มให้รก
> ตอนงานเสร็จ ถ้าตั้ง `anthropic_api_key` ไว้ จะให้ **Claude (Haiku) สรุปให้ตรงประเด็นยิ่งขึ้น** (ไม่ตั้งก็ใช้สรุปแบบตัดคำได้)

> 👥 **จะให้ทั้งทีมใช้ (ส่งเข้าห้อง Teams ร่วม แต่ละคนเด้งเฉพาะของตัวเอง)?** → ดู **[TEAMS_SETUP.md](TEAMS_SETUP.md)**

> เดิมตั้งใจใช้ LINE แต่ LINE Notify ปิดตัวแล้ว (มี.ค. 2025) และ Messaging API ต้องสร้าง Official Account + ยืนยัน SMS จึงเปลี่ยนมาใช้ Discord webhook ที่ตั้งค่าง่ายกว่ามาก

---

## ขั้นตอนตั้งค่า (ทำครั้งเดียว ~2 นาที)

### 1) สร้าง Discord Webhook
1. เปิด Discord (แอปหรือเว็บ) → เข้า **เซิร์ฟเวอร์ของคุณ** (ถ้ายังไม่มี กด `+` สร้างเซิร์ฟเวอร์ส่วนตัวฟรีก่อน)
2. เลือกห้อง (channel) ที่อยากให้แจ้งเตือนเข้า → กด **ไอคอนฟันเฟือง (Edit Channel)** ข้างชื่อห้อง
3. เมนูซ้าย → **Integrations** → **Webhooks** → **New Webhook**
4. (ตั้งชื่อ/รูปตามใจ เช่น `Claude Code`) → กด **Copy Webhook URL**

### 2) ใส่ค่าลงไฟล์ config
เปิดไฟล์ [`notify_config.json`](notify_config.json) วาง URL ที่ copy มา (ดูคีย์ครบที่ [`notify_config.example.json`](notify_config.example.json)):
```json
{
  "webhook_url": "https://discord.com/api/webhooks/xxxx/yyyy"
}
```
คีย์เสริม (ใส่หรือไม่ก็ได้):
- `anthropic_api_key` — Claude API key (`x-api-key`) เพื่อให้ **Haiku สรุปงานให้** ตอน `Stop`; เว้นว่าง = สรุปแบบตัดคำ · **แนะนำ (ถาวร ไม่หมดอายุ)**
- ใช้ **OAuth แทน API key** ก็ได้ (ลำดับความสำคัญ: `oauth_token` > `anthropic_api_key` > `oauth_from_ant`):
  - `oauth_token` — วาง OAuth access token ตรง ๆ → ใช้ `Authorization: Bearer` + `anthropic-beta: oauth-2025-04-20` · ⚠️ **token หมดอายุ ต้องเปลี่ยนเรื่อย ๆ**
  - `oauth_from_claude_code: true` — **ดึง token จาก Claude Code login ที่มีอยู่แล้ว** (`~/.claude/.credentials.json`) → ไม่ต้องลง/วางอะไรเลย · ⚠️ เป็น token ของ subscription อาจถูก `/v1/messages` ปฏิเสธ (คนละสโคปกับ dev OAuth) — ถ้าไม่ผ่านจะ fallback ไปสรุปแบบตัดคำ
  - `oauth_from_ant: true` — ขอ token สดจาก `ant auth print-credentials` (auto-refresh, OAuth ถูกวิธี) · ต้องลง [`ant` CLI](https://platform.claude.com/docs/en/api/sdks/cli) + `ant auth login` ก่อน
- `ai_summary` — `true`/`false` เปิด-ปิดสรุปด้วย AI (ดีฟอลต์ `true` เมื่อมี key/token)
- `mention_user_id` — Discord user id ของคุณ เพื่อ **แท็ก @ (มือถือเด้งแรง)** ตอน event สำคัญ
- `mention_events` — เลือกว่าจะแท็กตอนไหน (ดีฟอลต์ `["stop","error","ask","plan","notification","permission"]` = ทุก event) · หมายเหตุ: `stop` ยิงทุกครั้งที่ Claude ตอบจบ ตอนนั่งทำงานอยู่จะ ping ทุกเทิร์น — ถ้ารำคาญเอา `stop` ออกได้ (แต่ใน Teams ที่ตั้ง channel = Off ต้องมี `stop` ไม่งั้นงานเสร็จแล้วเงียบ)
- `sender_name` — ชื่อ/ตัวระบุผู้ส่ง โชว์ช่อง **👤 From** ในการ์ด (ห้องรวมหลายคนจะได้รู้ว่าอันไหนของใคร; เว้นว่าง = ไม่โชว์)
- `teams_webhook_url` — ส่งเข้า **Microsoft Teams** ด้วย (ตั้งพร้อม Discord หรือใช้อย่างเดียวก็ได้) → วิธีเอา URL ดู [ส่งเข้า Microsoft Teams](#5-ออปชัน-ส่งเข้า-microsoft-teams)
- `teams_language` — ภาษาของการ์ดที่ส่งเข้า **Teams**: `"en"` (ดีฟอลต์) หรือ `"th"` (หัวข้อ/ป้าย/สรุปเป็นภาษาที่เลือก; ตอนงานเสร็จ AI สรุปให้ตามภาษานั้น). เฉพาะ Teams — Discord ยังเป็นไทยเสมอ

> `notify_config.json` ถูก `.gitignore` (มี webhook + key ลับ) — ห้าม commit

### 3) ทดสอบ
รันในเทอร์มินัลที่โฟลเดอร์นี้:
```powershell
python notify.py --test
```
ถ้าเห็น embed `🧪 ทดสอบการเชื่อมต่อ Discord สำเร็จ` เด้งเข้าห้อง Discord = เสร็จเรียบร้อย 🎉

### 4) ติดตั้ง hook (แจ้งเตือนอัตโนมัติ)
**ดับเบิลคลิก [`setup_hook.bat`](setup_hook.bat)** (หรือรัน `python notify.py --install-hooks`)
สคริปต์จะเพิ่ม hook `Stop` + `Notification` + `PermissionRequest` + `PreToolUse` ลง **user-level settings** (`%USERPROFILE%\.claude\settings.json`)
โดย merge กับ hook เดิมที่มีอยู่ ไม่ทับของเก่า แล้ว **รีสตาร์ต Claude Code** หนึ่งครั้ง

> ถอนออกเมื่อไรก็ได้ด้วย `python notify.py --uninstall-hooks`

### 5) (ออปชัน) ส่งเข้า Microsoft Teams
Teams รองรับผ่าน **Workflows** (connector "Incoming Webhook" แบบเก่า Microsoft ยกเลิกแล้ว):
1. ในห้อง Teams → **⋯ ข้างชื่อห้อง → Workflows** → เทมเพลต **"Post to a channel when a webhook request is received"**
2. เลือก Team + Channel → **Add workflow** → **ก็อป URL** ที่ได้
3. วางลง `teams_webhook_url` ใน `notify_config.json` (ตั้งคู่กับ Discord ได้ — ส่งทั้งสองที่)
```powershell
python notify.py --test   # ทดสอบทุกช่องทางที่ตั้งไว้
```
> ใช้รูปแบบ **Adaptive Card** · บาง org ปิดการสร้าง Workflow — ถ้าสร้างไม่ได้ต้องให้ admin เปิดให้

**เลือกภาษา (ไทย/อังกฤษ):** การ์ด Teams **ดีฟอลต์เป็นอังกฤษ** (`"teams_language": "en"`) — หัวข้อ/ป้าย/บทสรุปเป็นอังกฤษ (ตอนงานเสร็จ AI สรุปเป็นอังกฤษให้เลย) เหมาะกับห้องทีมนานาชาติ. อยากได้ไทยตั้ง `"th"`. ตั้งเฉพาะ Teams — ช่อง Discord ยังเป็นไทยเสมอ จึงส่งไทยเข้า Discord + อังกฤษเข้า Teams พร้อมกันได้

**แท็ก @ เฉพาะคุณ (ไม่รบกวนทั้งทีม):** ใน Teams การโพสต์ลง channel เฉย ๆ **ไม่เด้งเตือนสมาชิก** (นอกจากตั้ง "All activity" เอง) ส่วน **@mention ตรงตัวเด้งเฉพาะคนนั้น** แม้ mute channel ไว้ ตั้งได้ที่:
- `teams_mention_id` — email/UPN (หรือ AAD object id) ของคุณ
- `teams_mention_name` — ชื่อที่โชว์ในแท็ก
- แท็กตอน event ใน `mention_events` เดียวกับ Discord
- ปิดเสียง channel: ห้อง → **⋯ → Channel notifications → Off** (personal @mention ยังเด้ง)
> ⚠️ mention ผ่าน Workflow บาง template อาจโชว์เป็นข้อความเฉย ๆ ไม่เด้ง — ถ้าเป็นงั้นต้องแต่ง flow เพิ่ม action **"Get an @mention token for a user"**

---

## การแจ้งเตือนอัตโนมัติ (Hooks)
ติดตั้งที่ **ระดับ user** (`%USERPROFILE%\.claude\settings.json`) จึงทำงาน **ทุกโปรเจกต์** ไม่ใช่แค่โฟลเดอร์นี้:

| เหตุการณ์ | Hook (matcher) | Embed |
|-----------|------|-------|
| Claude ตอบจบ / งานเสร็จ | `Stop` | 🟢 ✅ + 📝 สรุปไทย (Haiku ถ้ามี key) |
| Claude ขอ permission | `PermissionRequest` | 🟠 🔐 + tool และคำสั่ง/ไฟล์ที่ขอ |
| Claude ถามคำถาม | `PreToolUse` (`AskUserQuestion`) | 🟠 ❓ + คำถาม |
| Claude เสนอแผน | `PreToolUse` (`ExitPlanMode`) | 🟣 📋 + แผน |
| Claude รออินพุต / idle (เฉพาะ CLI) | `Notification` | 🟡 🔔 + ข้อความ |

> **ทำไมต้อง `PreToolUse`?** hook `Notification` ของ Claude Code **ไม่ยิงตอน AskUserQuestion/ExitPlanMode** (เป็นข้อจำกัดที่รู้กัน — [#59908](https://github.com/anthropics/claude-code/issues/59908)) เลยต้องดักที่ `PreToolUse` แทน; เป็น passive (exit 0) ไม่บล็อกการทำงานของ Claude
>
> **ทำไมต้อง `PermissionRequest`?** hook `Notification` **ไม่ยิงเลยใน desktop app / VS Code extension** ([#35541](https://github.com/anthropics/claude-code/issues/35541), [#11156](https://github.com/anthropics/claude-code/issues/11156)) — ยิงเฉพาะ CLI ในเทอร์มินัล การแจ้ง "ขอ permission" จึงใช้ hook `PermissionRequest` (มีตั้งแต่ Claude Code ~2.1) ซึ่งยิงจาก engine ตรงจุดที่ permission dialog ขึ้น จึงเด้งครบทุกหน้าจอ และได้รายละเอียดดีกว่า (รู้ว่า tool ไหนจะรันคำสั่ง/แก้ไฟล์อะไร) · ใน CLI ที่ทั้งสอง hook ยิงพร้อมกัน สคริปต์จะ**ข้ามใบ `Notification` ที่เป็นเรื่อง permission ให้อัตโนมัติ** (กันเด้งซ้ำ) เหลือ `Notification` ไว้จับตอน idle รออินพุต
>
> **สรุปมาจากไหน?** ปกติดึงข้อความล่าสุดของ Claude มาตัด markdown ย่อสั้น (≤ 200 ตัว, ไทยอยู่แล้ว → สรุปเป็นไทย, อังกฤษล้วน → เติมสถานะไทยนำหน้า). ตอน `Stop` ถ้ามี `anthropic_api_key` จะให้ **Claude Haiku สรุปเป็นไทย 1-2 ประโยค** ที่ตรงประเด็นกว่า (~$0.001–0.003/ครั้ง; มี fallback อัตโนมัติถ้า API ล่ม/ช้าเกิน 6 วิ)

> ⚠️ ต้องรีสตาร์ต Claude Code (หรือเปิดเมนู `/hooks` หนึ่งครั้ง) หลังติดตั้ง hook ครั้งแรก เพื่อให้มีผล

### ย้ายไปใช้เครื่องอื่น
1. ก็อปโฟลเดอร์นี้ไปเครื่องใหม่ 2. ใส่ webhook ใน `notify_config.json` 3. ดับเบิลคลิก `setup_hook.bat`
`setup_hook.bat` จะอ้าง path ของ `notify.py` ตามเครื่องนั้น ๆ ให้เองอัตโนมัติ

---

## เรียกเองด้วยมือ (manual)
```powershell
python notify.py --text "ข้อความอะไรก็ได้"
python notify.py --event error --text "เกิดปัญหา: build ล้มเหลว"
```

## ไฟล์ในโปรเจกต์
| ไฟล์ | หน้าที่ |
|------|---------|
| `notify.py` | ส่ง Discord/Teams + สรุป (heuristic/AI) + ติดตั้ง/ถอน hook |
| `setup_hook.bat` | ดับเบิลคลิกติดตั้ง hook ระดับ user |
| `notify_config.example.json` | ตัวอย่างคีย์ config ทั้งหมด (ไม่มีความลับ) |
| `notify_config.json` | webhook + API key จริง (ถูก `.gitignore`) |
| `test_notify.py` | เทสต์ (unittest, ไม่ต้องลง lib เพิ่ม) |
| `notify.log` | log การส่ง (ไว้ดีบั๊ก) |

> hook ถูกตั้งที่ `%USERPROFILE%\.claude\settings.json` (ระดับ user) — `.claude/settings.json` ในโปรเจกต์นี้ว่างไว้

## เทสต์
```powershell
python -m unittest test_notify -v
```

## แก้ปัญหา
- **ไม่มีข้อความเข้า Discord** → เช็ก `notify.log`, ตรวจว่า webhook URL ถูกต้องและห้องยังอยู่
- **HTTP 401/404** → webhook ถูกลบหรือ URL ผิด → สร้าง webhook ใหม่แล้ววาง URL ใหม่
- **HTTP 429** → ส่งถี่เกินไป (rate limit) เดี๋ยวก็หาย
- ส่งเข้า Discord ฟรีไม่จำกัดจำนวน (ต่างจากโควตา push ของ LINE)
