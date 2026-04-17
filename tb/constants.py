"""Static configuration-like constants."""

DRUG_IMAGES = {
    "INH 100mg": "drugs/inh_100mg.jpg",
    "Rifampicin 300mg": "drugs/rifampicin_300mg.jpg",
    "Rifampicin 450mg": "drugs/rifampicin_450mg.jpg",
    "PZA 500mg": "drugs/pza_500mg.jpg",
    "EMB 400mg": "drugs/emb_400mg.jpg",
    "EMB 500mg": "drugs/emb_500mg.jpg",
}

THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

OUTCOME_LABELS = {
    "": "กำลังรักษา",
    "cured": "หาย (Cured)",
    "completed": "รักษาครบ (Completed)",
    "failed": "รักษาไม่สำเร็จ (Failed)",
    "defaulted": "ขาดยา (Defaulted)",
    "died": "เสียชีวิต (Died)",
    "transferred_out": "ส่งต่อ (Transferred out)",
}
