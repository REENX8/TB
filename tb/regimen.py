"""Medication regimen calculation per Thai TB Guidelines."""
from __future__ import annotations


def parse_count(value: str):
    """Parse tablet count; returns int for whole numbers, float for halves (e.g. 1.5)."""
    v = float(value)
    return int(v) if v == int(v) else v


def calculate_regimen(weight: float) -> dict:
    """Return medication regimen with tablet counts per Thai TB guidelines (Table 6.1).

    Format: {"drug_name (mg)": count, ...}
    """
    if weight < 30:
        return {
            "INH 100mg": max(1, round(weight * 5 / 100)),
            "Rifampicin 300mg": max(1, round(weight * 10 / 300)),
            "PZA 500mg": max(1, round(weight * 25 / 500)),
            "EMB 400mg": max(1, round(weight * 17.5 / 400)),
        }
    elif weight < 35:
        return {
            "INH 100mg": 2,
            "Rifampicin 300mg": 1,
            "PZA 500mg": 1.5,
            "EMB 500mg": 1,
        }
    elif weight < 50:
        return {
            "INH 100mg": 3,
            "Rifampicin 450mg": 1,
            "PZA 500mg": 2,
            "EMB 400mg": 2,
        }
    elif weight < 70:
        return {
            "INH 100mg": 3,
            "Rifampicin 300mg": 2,
            "PZA 500mg": 3,
            "EMB 500mg": 2,
        }
    else:
        return {
            "INH 100mg": 3,
            "Rifampicin 300mg": 2,
            "PZA 500mg": 4,
            "EMB 400mg": 3,
        }
