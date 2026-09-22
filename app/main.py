import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from app import models, database, crud, auth
from app.routers import admin, operator, technician
from app.routers import auth as auth_router
from app.scheduler import start_scheduler, stop_scheduler

models.Base.metadata.create_all(bind=database.engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run the AI outage prediction loop in the background
    print("Initializing AI background scheduler...")
    start_scheduler()
    yield
    # Shutdown: stop the loop, otherwise its thread holds up restarts and reloads
    stop_scheduler()
    print("Shutting down Power Grid Management System...")


app = FastAPI(
    title="AI-Enabled Smart Power Grid Management System",
    description="Centralized platform for grid operations and AI predictive maintenance.",
    version="1.0",
    lifespan=lifespan,
)

# Signs the session cookie. Set PGMS_SECRET_KEY outside local development.
SECRET_KEY = os.environ.get("PGMS_SECRET_KEY", "pgms-dev-only-secret-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="pgms_session",
    max_age=8 * 60 * 60,  # one work shift
    same_site="lax",
    https_only=os.environ.get("PGMS_HTTPS_ONLY") == "1",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router.router)
app.include_router(admin.router)
app.include_router(operator.router)
app.include_router(technician.router)


@app.exception_handler(auth.LoginRequired)
def redirect_to_login(request: Request, exc: auth.LoginRequired):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    url = "/login"
    if exc.next_url:
        url += "?next=" + quote(exc.next_url, safe="")
    return RedirectResponse(url=url, status_code=303)


@app.exception_handler(auth.RoleForbidden)
def forbidden_page(request: Request, exc: auth.RoleForbidden):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    return templates.TemplateResponse(
        request,
        "403.html",
        {"title": "Access denied", "dashboard_url": auth.dashboard_for(exc.user)},
        status_code=403,
    )


@app.get("/")
def read_root(user=Depends(auth.get_current_user)):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url=auth.dashboard_for(user), status_code=303)

@app.get("/api/infrastructure/substations")
def get_substations(db: Session = Depends(database.get_db), user=Depends(auth.require_login)):
    return crud.get_substations(db)
