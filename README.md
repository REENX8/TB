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
| GET | `/ping` | Health check (uptime monitoring) | - |

---

## Deploy to Render

1. Push repo ขึ้น GitHub
2. สร้าง Web Service ใหม่บน Render → เลือก repo
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn wsgi:app`
5. เพิ่ม Environment Variables ตามตารางด้านบน
6. เพิ่ม PostgreSQL database → copy URL ใส่ `DATABASE_URL`

### Migration rollout (เฉพาะครั้งแรกที่อัปเกรดจาก schema เดิม)

สำหรับ production DB ที่สร้างโดย `db.create_all()` + ALTER TABLE เดิม:

```bash
# ครั้งเดียว — mark DB ที่ baseline โดยไม่รัน DDL ซ้ำ
flask --app wsgi:app db stamp head
```

หลังจากนั้น deploy ได้ปกติ — `Procfile` จะรัน `flask db upgrade` ให้โดยอัตโนมัติ

---

## License
MIT License © 2026 Chakireen Asae

If you use or reference this project, a mention or credit is appreciated.
