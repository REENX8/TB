"""Backwards-compatible entrypoint — delegates to the tb package.

Historical deployments used `gunicorn app:app`. New deployments should use
`gunicorn wsgi:app`. Both continue to work.
"""
from tb import create_app

app = create_app()
