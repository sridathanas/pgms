from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import database, crud, schemas

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def admin_dashboard(request: Request, db: Session = Depends(database.get_db)):
    power_stations = crud.get_power_stations(db)
    substations = crud.get_substations(db)
    return templates.TemplateResponse(
        request, 
        "admin.html", 
        {
            "title": "Admin Dashboard", 
            "power_stations": power_stations, 
            "substations": substations
        }
    )

@router.post("/power-station")
def add_power_station(
    stationName: str = Form(...),
    location: str = Form(...),
    maxCapacityMW: float = Form(...),
    status: str = Form("ACTIVE"),
    db: Session = Depends(database.get_db)
):
    station_data = schemas.PowerStationCreate(
        stationName=stationName,
        location=location,
        maxCapacityMW=maxCapacityMW,
        status=status
    )
    crud.create_power_station(db, station_data)
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/substation")
def add_substation(
    subStationName: str = Form(...),
    powerStationID: int = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    maxLoadCapacityMW: float = Form(...),
    stationStatus: str = Form("ACTIVE"),
    db: Session = Depends(database.get_db)
):
    sub_data = schemas.SubstationCreate(
        subStationName=subStationName,
        powerStationID=powerStationID,
        latitude=latitude,
        longitude=longitude,
        maxLoadCapacityMW=maxLoadCapacityMW,
        stationStatus=stationStatus
    )
    crud.create_substation(db, sub_data)
    return RedirectResponse(url="/admin", status_code=303)