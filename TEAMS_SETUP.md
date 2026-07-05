# ตั้งค่าแจ้งเตือน Claude Code เข้า Microsoft Teams (สำหรับทีม)

คู่มือให้เพื่อนร่วมทีมตั้งค่าให้ **Claude Code ของตัวเอง** ส่งแจ้งเตือนเข้า **ห้อง Teams ร่วม** โดย
**แต่ละคนเด้งเฉพาะของตัวเอง** (การ์ดจะ @mention เจ้าของ) — ไม่รบกวนเพื่อนคนอื่น

## วิธีทำงาน (อ่านก่อน)
- ทุกคนส่งเข้า **ห้อง Teams เดียวกัน** → เห็น activity ของทั้งทีมในที่เดียว
- แต่ละการ์ด **@mention เจ้าของ** (ใครส่งก็แท็กคนนั้น) → **คนนั้นเด้ง คนอื่นไม่เด้ง**
- ทุกคนตั้ง channel notifications = **Off** → เด้งเฉพาะตอนโดนแท็กตรงตัว

## สิ่งที่ต้องมี
- Python 3 — เช็กด้วย `python --version`
- Claude Code
- Git (หรือก็อปโฟลเดอร์มาเองก็ได้)

---

## 1) เอาโปรเจกต์มา
```powershell
git clone https://github.com/xinix000/Claude_Notification
cd Claude_Notification
```

## 2) เอา Azure AD Object ID (GUID) ของคุณ — เลือกวิธีใดวิธีหนึ่ง
> ต้องใช้ **GUID** ไม่ใช่ email เพราะ Teams Workflow ผูก @mention ด้วย object id เท่านั้น

### วิธี A — Azure CLI (ถ้ามี `az` อยู่แล้ว เร็วสุด)
```powershell
az login                                       # ครั้งแรกเด้ง browser ให้ล็อกอิน
az ad signed-in-user show --query id -o tsv    # พิมพ์ GUID ออกมาบรรทัดเดียว
```

### วิธี B — Graph Explorer (ไม่ต้องลงอะไร)
1. เปิด https://developer.microsoft.com/en-us/graph/graph-explorer
2. กด **Sign in** (บัญชีบริษัท)
3. รัน `GET https://graph.microsoft.com/v1.0/me`
4. ในผลลัพธ์ ก็อปค่า **`"id"`** — นั่นคือ GUID (รูปแบบ `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

## 3) ตั้งค่า config
ก็อป `notify_config.example.json` → **`notify_config.json`** แล้วแก้:
```json
{
  "teams_webhook_url": "<ขอ URL ห้องจากหัวหน้าทีม / คนที่ตั้ง Workflow>",
  "teams_mention_id": "<GUID ของคุณจากขั้น 2>",
  "teams_mention_name": "<ชื่อคุณ เช่น Kittana>",
  "sender_name": "<ชื่อคุณ — โชว์ช่อง 'From' ให้รู้ว่าการ์ดไหนของใคร>",
  "mention_events": ["stop", "error", "ask", "plan", "notification"]
}
```
> - `notify_config.json` ถูก `.gitignore` แล้ว — **ห้าม commit** (มี URL ลับ)
> - ไม่อยากส่ง Discord ด้วย → ปล่อย `webhook_url` เป็น `""` (หรือลบทิ้ง)
> - อยากได้ **สรุปด้วย AI** (Haiku) ตอนงานเสร็จ → ใส่ `anthropic_api_key`; ไม่ใส่ก็ใช้สรุปแบบตัดคำ

## 4) ติดตั้ง hook
**ดับเบิลคลิก [`setup_hook.bat`](setup_hook.bat)** (หรือรัน `python notify.py --install-hooks`)
แล้ว **รีสตาร์ต Claude Code** 1 ครั้ง
> hook ติดที่ระดับ user (`%USERPROFILE%\.claude\settings.json`) → ใช้ได้ทุกโปรเจกต์บนเครื่องคุณ

## 5) ปิดเสียง channel ใน Teams — **สำคัญ!**
ห้อง Teams ร่วม → **⋯ (ข้างชื่อห้อง) → Channel notifications → Off**
> ⚠️ **อย่าตั้ง "All activity"** — มันจะเด้ง **ทุกโพสต์รวมของคนอื่นด้วย**
> ตั้ง **Off** แล้ว personal @mention ของคุณ **ยังเด้งอยู่** = เด้งเฉพาะการ์ดที่แท็กคุณ

## 6) ทดสอบ
```powershell
python notify.py --event error --text "ทดสอบ ตั้งค่าเสร็จ"
```
เปิดห้อง Teams → ดูการ์ด **⛔ เกิด error**:
- ✅ มี **@ชื่อคุณ เป็นลิงก์สีน้ำเงิน** + คุณได้เด้งเตือน = **เสร็จเรียบร้อย!**
- ❌ @ชื่อขึ้นเป็นตัวดำ/ไม่เด้ง → `teams_mention_id` ยังไม่ใช่ GUID (ดูขั้น 2 ใหม่)

---

## เด้งตอนไหนบ้าง
| การ์ด | เมื่อไร |
|-------|---------|
| ✅ Claude ทำงานเสร็จแล้ว | Claude ตอบจบ / งานเสร็จ |
| ❓ มีคำถามให้ตอบ | Claude ถามคำถาม (AskUserQuestion) |
| 📋 เสนอแผน รออนุมัติ | Claude เสนอ plan (ExitPlanMode) |
| 🔔 ขอสิทธิ์ / รอ | Claude ขอ permission / idle |
| ⛔ เกิด error | เรียกเอง: `python notify.py --event error --text "..."` |

## (ออปชัน) เอา footer "used a Workflow template" ออก
การ์ดมีบรรทัดท้าย *"...used a Workflow template. Get template"* เพราะ flow โพสต์ในนามคุณ
ลองให้โพสต์เป็น **Flow bot** แทน:
1. เปิด [Power Automate](https://make.powerautomate.com) → เปิด flow → **Edit**
2. หา action โพสต์การ์ด (เช่น *"Post card in a chat or channel"*)
3. ช่อง **"Post as"** เปลี่ยนเป็น **Flow bot** → **Save**
4. ⚠️ **ทดสอบ @mention ซ้ำ** — บาง config พอเป็น Flow bot แล้ว mention ไม่เด้ง ถ้าเจอแบบนั้นเปลี่ยนกลับเป็น **User**

## แก้ปัญหา
| อาการ | สาเหตุ / วิธีแก้ |
|-------|----------------|
| @ชื่อขึ้นเป็นตัวดำ ไม่เด้ง | `teams_mention_id` ต้องเป็น **GUID** ไม่ใช่ email |
| ไม่มีอะไรเข้า Teams | เช็ก `notify.log`; ตรวจ `teams_webhook_url` ถูก/ยังอยู่ไหม |
| ถามคำถามแล้วไม่เด้ง | ต้อง **รีสตาร์ต Claude Code** หลังติดตั้ง hook (โหลด hook ตอนเปิด) |
| โดนเด้งของคนอื่นด้วย | คุณตั้ง channel เป็น **All activity** อยู่ → เปลี่ยนเป็น **Off** |
| JSON error ใน `notify.log` | `notify_config.json` พิมพ์ผิด (มัก **ลืม comma**) → เช็ก syntax |

รายละเอียดเพิ่มเติมทั้งหมดดูที่ [README.md](README.md)
