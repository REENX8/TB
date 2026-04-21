"""TB Medication Tracker — application package."""
from __future__ import annotations

import os

from flask import Flask

from tb.extensions import csrf, db, migrate

ENDPOINT_ALIASES = {
    "index": "patient.index",
    "new_patient": "patient.new_patient",
    "view_patient": "patient.view_patient",
    "edit_patient": "patient.edit_patient",
    "archive_patient": "patient.archive_patient",
    "restore_patient": "patient.restore_patient",
    "delete_patient": "patient.delete_patient",
    "extend_schedule": "patient.extend_schedule",
    "update_weight": "patient.update_weight",
    "regenerate_token": "patient.regenerate_token",
    "export_csv": "patient.export_csv",
    "print_schedule": "patient.print_schedule",
    "mark_dose": "dose.mark_dose",
    "unmark_dose": "dose.unmark_dose",
    "edit_dose": "dose.edit_dose",
    "qr_code_patient": "scan.qr_code_patient",
    "qr_code_page": "scan.qr_code_page",
    "scan_patient": "scan.scan_patient",
    "staff_login": "auth.staff_login",
    "staff_logout": "auth.staff_logout",
    "dashboard": "report.dashboard",
    "report": "report.report",
    "report_export": "report.report_export",
    "report_export_xlsx": "report.report_export_xlsx",
    "ping": "report.ping",
    "audit_log": "audit.audit_log",
}


def _register_aliases(app: Flask) -> None:
    """Register flat endpoint aliases so existing templates keep working."""
    for alias, target in ENDPOINT_ALIASES.items():
        view_func = app.view_functions.get(target)
        if view_func is None:
            continue
        target_rules = [r for r in app.url_map.iter_rules() if r.endpoint == target]
        for rule in target_rules:
            app.add_url_rule(
                rule.rule,
                endpoint=alias,
                view_func=view_func,
                methods=(rule.methods or set()) - {"HEAD", "OPTIONS"},
            )


def create_app(config_object: str | None = None) -> Flask:
    """Application factory."""
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    if config_object is None:
        config_object = os.environ.get("TB_CONFIG", "tb.config.ProdConfig")
    app.config.from_object(config_object)

    db.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    from tb.audit_bp.routes import bp as audit_bp
    from tb.auth.routes import bp as auth_bp
    from tb.dose.routes import bp as dose_bp
    from tb.patient.routes import bp as patient_bp
    from tb.report.routes import bp as report_bp
    from tb.scan.routes import bp as scan_bp

    for bp in (auth_bp, patient_bp, dose_bp, scan_bp, report_bp, audit_bp):
        app.register_blueprint(bp)

    from tb.template_helpers import register as register_template_helpers

    register_template_helpers(app)

    _register_aliases(app)

    return app
