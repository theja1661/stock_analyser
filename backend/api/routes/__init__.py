"""API routers, one module per area."""
from . import documents, results, runs, settings

ROUTERS = [results.router, runs.router, documents.router, settings.router]
