# TB Medication Tracker

ระบบติดตามการกินยาวัณโรค (TB) สำหรับเจ้าหน้าที่พยาบาลและเภสัชกร  
ผู้ป่วยสแกน QR Code เพื่อยืนยันการกินยาแต่ละวัน

---

# PREVIEW WEBSITE
https://reenx8.github.io/TB/index.html

---
## Features

- **จัดการผู้ป่วย** — เพิ่ม, แก้ไขข้อมูล, เก็บประวัติ (soft delete), คืนสถานะ
- **คำนวณยาอัตโนมัติ** — ตามน้ำหนักตัวตาม Thai TB Guidelines (Table 6.1)
- **QR Code** — 1 QR ต่อผู้ป่วย ผู้ป่วยสแกนแล้วกดยืนยันกินยา
- **Visual Drug Picker** — เลือกยาจาก 6 รูปยามาตรฐาน พร้อมระบุจำนวนเม็ด (รองรับ 0.5 เม็ด)
- **ปฏิทินการกินยา** — ดูสถานะรายเดือน (กินแล้ว / รอกิน / ค้าง)
- **สถิติ Adherence** — % การกินยาสม่ำเสมอ
- **แก้ไขตารางยา** — เภสัชกรแก้ไขยาแต่ละวัน, เพิ่มวัน, เปลี่ยนยาสำหรับวันที่เหลือ
- **อัปเดตน้ำหนัก** — คำนวณยาใหม่อัตโนมัติสำหรับวันที่ยังไม่ได้กิน
- **Export CSV** — ดาวน์โหลดประวัติการกินยา (รองรับ Excel ภาษาไทย)
- **พิมพ์ตารางยา** — หน้า print-friendly รายเดือน สำหรับติดหัวเตียง
- **Multi-staff login** — รองรับหลาย account ผ่าน environment variables
- **Session timeout** — 8 ชั่วโมง

---

## Local Setup

```bash
# 1. สร้าง virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. ติดตั้ง dependencies
pip install -r requirements.txt

# 3. รัน migration (สร้าง / อัปเกรด schema)
flask --app wsgi:app db upgrade

# 4. รัน dev server
python app.py
# เปิด http://localhost:5000
```

### การรัน tests

```bash
pytest --cov=tb
```

---

## Environment Variables

| Variable | ค่าตัวอย่าง | คำอธิบาย |
|---|---|---|
| `SECRET_KEY` | `your-random-secret` | Flask session key (สำคัญมาก) |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL URL (ถ้าไม่ตั้งใช้ SQLite) |
| `STAFF_USER` | `ABCD` | username account หลัก |
| `STAFF_PASS_HASH` | `scrypt:...` | password hash account หลัก |
| `STAFF_USER_2` | `DEFG` | username account ที่ 2 (optional) |
| `STAFF_PASS_HASH_2` | `scrypt:...` | password hash account ที่ 2 |
| `STAFF_USER_3` | `...` | เพิ่ม account ต่อไปได้เรื่อย ๆ |
| `LINE_CHANNEL_ACCESS_TOKEN` | `...` | (optional) LINE Messaging API — แจ้งอาการไปหาเภสัชกร |
| `LINE_CHANNEL_SECRET` | `...` | (optional) ใช้ตรวจ signature ของ webhook |
| `LINE_REGISTER_CODE` | `JOIN-TB` | (optional) รหัสที่เภสัชกรพิมพ์ใน LINE เพื่อลงทะเบียน |

### LINE แจ้งเตือนอาการไม่พึงประสงค์ (optional)

เมื่อตั้งค่า LINE ครบ ระบบจะส่งการแจ้งอาการของผู้ป่วยไปหาเภสัชกรผ่าน LINE:

1. สร้าง **Messaging API channel** ใน [LINE Developers Console](https://developers.line.biz/)
   คัดลอก **Channel access token** และ **Channel secret** มาใส่ env vars
2. ตั้ง **Webhook URL** ใน console เป็น `https://<your-domain>/line/webhook` แล้วเปิด Use webhook
3. ตั้ง `LINE_REGISTER_CODE` เป็นรหัสลับสำหรับลงทะเบียน
4. **เภสัชกรลงทะเบียน**: แอด LINE Official Account เป็นเพื่อน แล้วพิมพ์รหัส (`LINE_REGISTER_CODE`) ในแชต
5. เมื่อผู้ป่วยแจ้งอาการในเว็บ เภสัชกรที่ลงทะเบียนจะได้รับข้อความ: ชื่อ, HN, อาการ, และ **เลขรับคำตอบ** (เช่น `A01`)
6. เภสัชกรตอบกลับใน LINE: พิมพ์ `A01+ข้อความถึงผู้ป่วย` ระบบจะนำคำตอบไปแสดงในหน้าสแกนของผู้ป่วย (ไม่แสดงเลขรับคำตอบ)
7. พิมพ์ `ยกเลิก` เพื่อเลิกรับการแจ้งเตือน

> ถ้าไม่ตั้งค่า LINE ระบบทำงานปกติทุกอย่าง เพียงแต่ไม่ส่ง LINE — `/line/webhook` จะคืน 404

### วิธี Generate Password Hash

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))"
```

---

## Routes

| Method | Path | คำอธิบาย | Auth |
|---|---|---|---|
| GET | `/` | รายชื่อผู้ป่วย | ✓ |
| GET | `/login` | หน้า login | - |
| GET | `/logout` | ออกจากระบบ | - |
| GET | `/dashboard` | Dashboard สรุป | ✓ |
| GET/POST | `/patient/new` | เพิ่มผู้ป่วย | ✓ |
| GET | `/patient/<id>` | ดูข้อมูลผู้ป่วย | ✓ |
| GET/POST | `/patient/<id>/edit` | แก้ไขข้อมูลผู้ป่วย | ✓ |
| POST | `/patient/<id>/archive` | เก็บประวัติ (soft delete) | ✓ |
| POST | `/patient/<id>/restore` | คืนสถานะจาก archive | ✓ |
| POST | `/patient/<id>/mark/<dose_id>` | บันทึกกินยา | ✓ |
| POST | `/patient/<id>/unmark/<dose_id>` | ยกเลิกการกินยา | ✓ |
| POST | `/patient/<id>/update_weight` | อัปเดตน้ำหนัก + คำนวณยาใหม่ | ✓ |
| GET/POST | `/patient/<id>/edit_dose/<dose_id>` | แก้ไขยาแต่ละวัน | ✓ |
| GET/POST | `/patient/<id>/extend` | เพิ่มวัน / เปลี่ยนยาที่เหลือ | ✓ |
| GET | `/patient/<id>/export_csv` | Export CSV | ✓ |
| GET | `/patient/<id>/print` | พิมพ์ตารางยา | ✓ |
| GET | `/qr_page/<id>` | หน้า QR Code | ✓ |
| GET | `/qr/patient/<id>.png` | รูป QR Code | ✓ |
| GET/POST | `/scan/<token>` | หน้าสแกน QR (ผู้ป่วย) | - |
| POST | `/scan/<token>/report` | ผู้ป่วยแจ้งอาการไม่พึงประสงค์ | - |
| GET | `/symptoms` | รายการแจ้งอาการ (เจ้าหน้าที่) | ✓ |
| POST | `/symptoms/<id>/reply` | เภสัชกร/admin ตอบกลับ | ✓ |
| GET | `/staff` | จัดการบัญชีเจ้าหน้าที่ | ✓ (admin) |
| POST | `/line/webhook` | LINE webhook (ลงทะเบียน + ตอบอาการ) | LINE signature |
| GET | `/ping` | Health check (uptime monitoring) | - |

---

## Deploy to Render

1. Push repo ขึ้น GitHub
2. สร้าง Web Service ใหม่บน Render → เลือก repo
3. Build Command: `pip install -r requirements.txt`
4. **Pre-Deploy Command**: `flask --app wsgi:app db upgrade` ← สำคัญ! รัน migration ทุกครั้งก่อน deploy
5. Start Command: `gunicorn wsgi:app --workers 2 --threads 2 --timeout 60 --access-logfile -`
6. เพิ่ม Environment Variables ตามตารางด้านบน
7. เพิ่ม PostgreSQL database → copy URL ใส่ `DATABASE_URL`

> ⚠️ Render **ไม่อ่าน Procfile** (`release:` เป็นรูปแบบของ Heroku)
> ต้องตั้ง Pre-Deploy Command ใน Render dashboard (Settings → Build & Deploy)
> ไม่เช่นนั้น migration จะไม่ถูกรันและตารางใหม่จะไม่ถูกสร้าง

> 💡 **ถ้าใช้ Supabase เป็น database**: migration ควรรันผ่าน connection string
> แบบ **Session (port 5432)** — Transaction Pooler (port 6543) อาจมีปัญหากับ DDL
> หรือจะรัน SQL สร้างตารางเองใน Supabase SQL Editor ก็ได้
> (แล้ว stamp เวอร์ชันด้วย `INSERT INTO alembic_version ...`)

### Migration rollout (เฉพาะครั้งแรกที่อัปเกรดจาก schema เดิม)

สำหรับ production DB ที่สร้างโดย `db.create_all()` + ALTER TABLE เดิม:

```bash
# ครั้งเดียว — mark DB ที่ baseline โดยไม่รัน DDL ซ้ำ
flask --app wsgi:app db stamp 6b70a0d2414e
flask --app wsgi:app db upgrade
```

หลังจากนั้น deploy ได้ปกติ — Pre-Deploy Command จะรัน `flask db upgrade` ให้ทุกครั้ง

---

## License
MIT License © 2026 Chakireen Asae

If you use or reference this project, a mention or credit is appreciated.
