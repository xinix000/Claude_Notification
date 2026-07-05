# Discord Notify สำหรับ Claude Code

แจ้งเตือนเข้า **Discord** อัตโนมัติเมื่อ Claude Code:
- ✅ ทำงานเสร็จ (hook: `Stop`) — embed สีเขียว
- 🔔 ต้องการให้คุณตอบ/ยืนยัน (hook: `Notification`) — embed สีเหลือง
- ⛔ เกิด error (Claude เรียกสคริปต์เองตอนพบข้อผิดพลาด) — embed สีแดง

> แต่ละการแจ้งเตือนเป็น **📝 สรุปสั้น ๆ ภาษาไทยแค่ 1 ย่อหน้า** (≤ 200 ตัว) อ่านปราดเดียวรู้ว่าสรุปเป็นยังไง — ไม่ดั๊มพ์ข้อความเต็มให้รก

> เดิมตั้งใจใช้ LINE แต่ LINE Notify ปิดตัวแล้ว (มี.ค. 2025) และ Messaging API ต้องสร้าง Official Account + ยืนยัน SMS จึงเปลี่ยนมาใช้ Discord webhook ที่ตั้งค่าง่ายกว่ามาก

---

## ขั้นตอนตั้งค่า (ทำครั้งเดียว ~2 นาที)

### 1) สร้าง Discord Webhook
1. เปิด Discord (แอปหรือเว็บ) → เข้า **เซิร์ฟเวอร์ของคุณ** (ถ้ายังไม่มี กด `+` สร้างเซิร์ฟเวอร์ส่วนตัวฟรีก่อน)
2. เลือกห้อง (channel) ที่อยากให้แจ้งเตือนเข้า → กด **ไอคอนฟันเฟือง (Edit Channel)** ข้างชื่อห้อง
3. เมนูซ้าย → **Integrations** → **Webhooks** → **New Webhook**
4. (ตั้งชื่อ/รูปตามใจ เช่น `Claude Code`) → กด **Copy Webhook URL**

### 2) ใส่ URL ลงไฟล์ config
เปิดไฟล์ [`notify_config.json`](notify_config.json) แล้ววาง URL ที่ copy มา:
```json
{
  "webhook_url": "https://discord.com/api/webhooks/xxxx/yyyy"
}
```

### 3) ทดสอบ
รันในเทอร์มินัลที่โฟลเดอร์นี้:
```powershell
python notify.py --test
```
ถ้าเห็น embed `🧪 ทดสอบการเชื่อมต่อ Discord สำเร็จ` เด้งเข้าห้อง Discord = เสร็จเรียบร้อย 🎉

### 4) ติดตั้ง hook (แจ้งเตือนอัตโนมัติ)
**ดับเบิลคลิก [`setup_hook.bat`](setup_hook.bat)** (หรือรัน `python notify.py --install-hooks`)
สคริปต์จะเพิ่ม hook `Stop` + `Notification` ลง **user-level settings** (`%USERPROFILE%\.claude\settings.json`)
โดย merge กับ hook เดิมที่มีอยู่ ไม่ทับของเก่า แล้ว **รีสตาร์ต Claude Code** หนึ่งครั้ง

> ถอนออกเมื่อไรก็ได้ด้วย `python notify.py --uninstall-hooks`

---

## การแจ้งเตือนอัตโนมัติ (Hooks)
ติดตั้งที่ **ระดับ user** (`%USERPROFILE%\.claude\settings.json`) จึงทำงาน **ทุกโปรเจกต์** ไม่ใช่แค่โฟลเดอร์นี้:

| เหตุการณ์ | Hook | Embed |
|-----------|------|-------|
| Claude ตอบจบ / งานเสร็จ | `Stop` | 🟢 ✅ + 📝 สรุปไทยสั้น ๆ 1 ย่อหน้า |
| Claude ขอสิทธิ์ / รออินพุต | `Notification` | 🟡 🔔 + 📝 สรุปไทยสั้น ๆ 1 ย่อหน้า |

> **สรุปมาจากไหน?** ดึงข้อความล่าสุดของ Claude มาตัด markdown แล้วย่อให้สั้น (≤ 200 ตัว) — ปกติ Claude ตอบเป็นไทยอยู่แล้ว สรุปก็จะเป็นไทย ถ้าบังเอิญเป็นอังกฤษล้วนจะเติมสถานะไทยนำหน้าให้ (เช่น `งานเสร็จแล้ว: ...`)

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
| `notify.py` | สคริปต์ส่ง Discord + ตัวจัดการ hook + ติดตั้ง/ถอน hook |
| `setup_hook.bat` | ดับเบิลคลิกเพื่อติดตั้ง hook ระดับ user (เรียก `notify.py --install-hooks`) |
| `notify_config.json` | เก็บ webhook URL (ถูก `.gitignore` ไว้) |
| `notify.log` | log การส่ง (ไว้ดีบั๊ก) |

> hook ถูกตั้งที่ `%USERPROFILE%\.claude\settings.json` (ระดับ user) — `.claude/settings.json` ในโปรเจกต์นี้ว่างไว้แล้ว

## แก้ปัญหา
- **ไม่มีข้อความเข้า Discord** → เช็ก `notify.log`, ตรวจว่า webhook URL ถูกต้องและห้องยังอยู่
- **HTTP 401/404** → webhook ถูกลบหรือ URL ผิด → สร้าง webhook ใหม่แล้ววาง URL ใหม่
- **HTTP 429** → ส่งถี่เกินไป (rate limit) เดี๋ยวก็หาย
- ส่งเข้า Discord ฟรีไม่จำกัดจำนวน (ต่างจากโควตา push ของ LINE)
