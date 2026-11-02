import os
import sys

# Ensure the backend package (backend/app) is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.main import app as api_app

# Same origin the Vite dev server and the dashboard docs use.
HOST = "127.0.0.1"
PORT = 5173

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
dist = os.path.join(PROJECT_ROOT, "frontend", "dist")
index_file = os.path.join(dist, "index.html")
assets_dir = os.path.join(dist, "assets")


class StripApiPrefixMiddleware:
    """The UI calls /api/*; FastAPI routes are mounted at /* (same as Vite and nginx)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if (path == "/api" or path.startswith("/api/")) and not path.startswith("/api/simulation"):
                scope = dict(scope)
                stripped = path[len("/api") :] or "/"
                scope["path"] = stripped
                raw = scope.get("raw_path")
                if isinstance(raw, (bytes, bytearray)) and raw.startswith(b"/api"):
                    scope["raw_path"] = raw[len(b"/api") :] or b"/"
        await self.app(scope, receive, send)


api_app.add_middleware(StripApiPrefixMiddleware)

if os.path.isdir(assets_dir):
    api_app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@api_app.get("/")
async def index():
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    return JSONResponse(
        {
            "service": "HydroFlow V2",
            "status": "api-only",
            "ui": "frontend/dist is not built",
            "hint": "From frontend/, run npm run build, then start this server again.",
        }
    )


@api_app.get("/{path:path}")
async def spa_fallback(path: str):
    if path.startswith(("api/", "assets/", "openapi.json", "docs", "favicon.ico")):
        raise HTTPException(status_code=404)
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="HydroFlow V2 frontend build was not found.")


if __name__ == "__main__":
    uvicorn.run(api_app, host=HOST, port=PORT)
