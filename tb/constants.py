"""Static configuration-like constants."""

DRUG_IMAGES = {
    "INH 100mg": "drugs/inh_100mg.jpg",
    "Rifampicin 300mg": "drugs/rifampicin_300mg.jpg",
    "Rifampicin 450mg": "drugs/rifampicin_450mg.jpg",
    "PZA 500mg": "drugs/pza_500mg.jpg",
    "EMB 400mg": "drugs/emb_400mg.jpg",
    "EMB 500mg": "drugs/emb_500mg.jpg",
    "Levofloxacin 500mg": "drugs/Levofloxacin 500 mg.jpg",
    "Amikacin 500mg/2ml": "drugs/Amikacin 500 mg per 2 ml(vial).jpg",
    "Streptomycin 1g/vial": "drugs/Streptomycin 1 g per vial.jpg",
}

INJECTABLE_DRUGS = frozenset({"Amikacin 500mg/2ml", "Streptomycin 1g/vial"})

THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

STAFF_ROLES = {
    "admin": "ผู้ดูแลระบบ",
    "pharmacist": "เภสัชกร",
    "nurse": "พยาบาล",
}

# Patient-reported adverse symptom categories with automatic Thai guidance.
# "severe": True categories prepend SYMPTOM_SEVERE_WARNING to the advice.
SYMPTOM_SEVERE_WARNING = (
    "⚠️ อาการนี้อาจรุนแรง กรุณาหยุดยาและติดต่อคลินิกวัณโรค/โรงพยาบาลทันที"
)

SYMPTOM_CATEGORIES = {
    "nausea": {
        "label": "คลื่นไส้ อาเจียน",
        "severe": False,
        "advice": (
            "ลองกินยาพร้อมอาหารหรือก่อนนอน ดื่มน้ำมากๆ "
            "หากอาเจียนมากจนกินยาไม่ได้ หรือมีอาการปวดท้องร่วมด้วย "
            "กรุณาติดต่อคลินิก"
        ),
    },
    "rash": {
        "label": "ผื่นคัน",
        "severe": False,
        "advice": (
            "หลีกเลี่ยงการเกา หากผื่นเล็กน้อยให้สังเกตอาการต่อ "
            "หากผื่นลามทั่วตัว มีไข้ หรือเยื่อบุปาก/ตาอักเสบ "
            "ให้หยุดยาและมาพบแพทย์ทันที"
        ),
    },
    "jaundice": {
        "label": "ตัวเหลือง ตาเหลือง",
        "severe": True,
        "advice": (
            "อาจเป็นสัญญาณของตับอักเสบจากยา "
            "สังเกตปัสสาวะสีเข้ม เบื่ออาหาร คลื่นไส้ร่วมด้วย"
        ),
    },
    "numbness": {
        "label": "ชาปลายมือปลายเท้า",
        "severe": False,
        "advice": (
            "อาจเกิดจากยา INH แจ้งเจ้าหน้าที่ในนัดครั้งถัดไป "
            "แพทย์อาจพิจารณาเพิ่มวิตามิน B6"
        ),
    },
    "blurred_vision": {
        "label": "ตามัว มองเห็นผิดปกติ",
        "severe": True,
        "advice": (
            "อาจเกิดจากยา Ethambutol "
            "สังเกตการแยกสีเขียว-แดงผิดปกติร่วมด้วย"
        ),
    },
    "joint_pain": {
        "label": "ปวดข้อ",
        "severe": False,
        "advice": (
            "อาจเกิดจากยา PZA ดื่มน้ำมากๆ หลีกเลี่ยงอาหารยอดผัก เครื่องในสัตว์ "
            "หากปวดมากจนเดินลำบาก กรุณาติดต่อคลินิก"
        ),
    },
    "other": {
        "label": "อาการอื่นๆ",
        "severe": False,
        "advice": (
            "เจ้าหน้าที่จะตรวจสอบและติดต่อกลับ "
            "หากอาการรุนแรงกรุณาติดต่อคลินิกหรือโรงพยาบาลโดยตรง"
        ),
    },
}

SYMPTOM_STATUS_LABELS = {
    "new": "ใหม่",
    "replied": "ตอบแล้ว",
    "resolved": "ปิดเรื่อง",
}

OUTCOME_LABELS = {
    "": "กำลังรักษา",
    "cured": "หาย (Cured)",
    "completed": "รักษาครบ (Completed)",
    "failed": "รักษาไม่สำเร็จ (Failed)",
    "defaulted": "ขาดยา (Defaulted)",
    "died": "เสียชีวิต (Died)",
    "transferred_out": "ส่งต่อ (Transferred out)",
}
