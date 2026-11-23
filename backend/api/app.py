"""FastAPI application: JSON API under /api, the frontend folder served at /."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from analyzer.common import FRONTEND_DIR

from .routes import ROUTERS


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Analyzer", docs_url=None, redoc_url=None, openapi_url=None)
    for r in ROUTERS:
        app.include_router(r)

    @app.middleware("http")
    async def no_stale_frontend(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        # No build step means no hashed filenames, so make browsers revalidate
        # app files instead of running yesterday's JavaScript.
        if not request.url.path.startswith("/api") and "/vendor/" not in request.url.path:
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Must be mounted last: it catches every path the API routes didn't.
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
