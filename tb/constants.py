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

OUTCOME_LABELS = {
    "": "กำลังรักษา",
    "cured": "หาย (Cured)",
    "completed": "รักษาครบ (Completed)",
    "failed": "รักษาไม่สำเร็จ (Failed)",
    "defaulted": "ขาดยา (Defaulted)",
    "died": "เสียชีวิต (Died)",
    "transferred_out": "ส่งต่อ (Transferred out)",
}
