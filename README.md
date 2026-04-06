# TB Medication Tracker

ระบบติดตามการกินยาวัณโรค (Tuberculosis Medication Adherence Tracker)

## Features
- ลงทะเบียนผู้ป่วยและสร้างตารางยาอัตโนมัติตามน้ำหนัก
- QR Code สแกนยืนยันกินยาผ่านมือถือ
- ปฏิทินแสดงสถานะการกินยารายเดือน
- Dashboard สำหรับเจ้าหน้าที่ดูภาพรวมความสม่ำเสมอ
- แสดงโดสค้าง/เลยกำหนด

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Deploy to Render

1. Push this repo to GitHub
2. Go to https://render.com → New Web Service
3. Connect your GitHub repo
4. Settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
5. Deploy
