"""Installed WSGI entrypoint. Application construction remains detector-lazy."""
from app import create_app

application = create_app()
