"""HTTP API + pages. Run: uvicorn engine.api:app

/        the MarkStrap website (site/, built by `make site`)
/app     the agency app: organizations -> products -> campaigns -> concepts -> assets -> results -> next
/console the engine console (advanced: makers, lineage, dials) for one campaign
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import hub
from .routes import agency as agency_routes
from .routes import campaign as campaign_routes

app = FastAPI(title="MarkStrap")
hub.init()
app.include_router(agency_routes.r)
app.include_router(campaign_routes.r)
app.include_router(campaign_routes.files)

WEB = Path(__file__).resolve().parent.parent / "web"
SITE = WEB / "site"

if (SITE / "assets").exists():  # built by `make site`
    app.mount("/assets", StaticFiles(directory=SITE / "assets"), name="site-assets")
if (SITE / "art").exists():  # halftone artwork shared by the website and the app
    app.mount("/art", StaticFiles(directory=SITE / "art"), name="site-art")


@app.get("/")
def index():
    page = SITE / "index.html"
    if not page.exists():
        raise HTTPException(404, "run `make site` to build the website")
    return FileResponse(page)


@app.get("/favicon.png")
def favicon():
    return FileResponse(WEB / "favicon.png")


@app.get("/mark.png")
def mark():
    return FileResponse(WEB / "mark.png")


@app.get("/app")
def user_app():
    page = SITE / "app.html"
    if not page.exists():
        raise HTTPException(404, "run `make site` to build the app")
    return FileResponse(page)


@app.get("/console")
def console():
    return FileResponse(WEB / "console.html")
