"""Jinja context processors and filters."""
from __future__ import annotations

from datetime import date

from flask import Flask

from tb.constants import DRUG_IMAGES, INJECTABLE_DRUGS, THAI_MONTHS
from tb.time_utils import today_th


def register(app: Flask) -> None:
    @app.context_processor
    def inject_helpers():
        def format_date(dt):
            return dt.strftime("%Y-%m-%d") if dt else ""

        def format_datetime(dt):
            return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

        return dict(
            format_date=format_date,
            format_datetime=format_datetime,
            date=date,
            today_th=today_th,
            drug_images=DRUG_IMAGES,
            injectable_drugs=INJECTABLE_DRUGS,
        )

    @app.template_filter("thai_month")
    def thai_month_filter(month_num):
        return THAI_MONTHS[month_num] if 1 <= month_num <= 12 else str(month_num)
