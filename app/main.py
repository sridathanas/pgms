from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import models, database, crud
from app.routers import admin  # Must import the admin router module

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="AI-Enabled Smart Power Grid Management System")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Register the admin router
app.include_router(admin.router)

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(
        request, 
        "base.html", 
        {"title": "PGMS Dashboard"}
    )

@app.get("/api/infrastructure/substations")
def get_substations(db: Session = Depends(database.get_db)):
    return crud.get_substations(db)