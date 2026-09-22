from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import auth, database, crud, schemas, models, scheduler

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(auth.require_roles(models.Role.ADMIN))],
)
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
            "substations": substations,
            "pending_admins": crud.get_pending_admins(db),
            "grid_risk": crud.get_grid_risk_overview(db),
            "prediction_interval_label": scheduler.interval_label(),
            "can_run_prediction": True,
            "flash": request.session.pop("flash", None)
        }
    )

@router.post("/run-prediction")
def run_prediction_now(
    request: Request,
    admin_user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """Run one AI prediction cycle immediately instead of waiting for the 15-minute loop."""
    result = scheduler.run_prediction_cycle()
    if not result["ok"] and result.get("reason") == "model_missing":
        request.session["flash"] = "Model file not found. Run `python train_model.py` first."
    elif not result["ok"]:
        request.session["flash"] = f"Prediction run failed: {result.get('reason')}"
    else:
        request.session["flash"] = (f"Prediction run complete: scored {result['scored']} substation(s), "
                                    f"raised {result['alerts']} new alert(s).")
        crud.log_action(db, "AI_PREDICTION_RUN",
                        f"{admin_user.username} ran the prediction cycle manually", admin_user.userID)
    return RedirectResponse(url="/admin", status_code=303)

def review_admin_request(request: Request, db: Session, reviewer: models.UserAccount, user_id: int, approve: bool):
    user = crud.get_user(db, user_id)
    if (user is None or user.role != models.Role.ADMIN
            or user.approvalStatus != models.ApprovalStatus.PENDING):
        request.session["flash"] = "That request was already handled or no longer exists."
        return RedirectResponse(url="/admin", status_code=303)

    status = models.ApprovalStatus.APPROVED if approve else models.ApprovalStatus.REJECTED
    crud.set_approval_status(db, user, status)
    verb = "approved" if approve else "rejected"
    crud.log_action(db, f"ADMIN_{status}",
                    f"{reviewer.username} {verb} the administrator request from {user.username}", reviewer.userID)
    request.session["flash"] = f"{verb.capitalize()} the administrator request from {user.name or user.username}."
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/users/{user_id}/approve")
def approve_admin_request(
    user_id: int,
    request: Request,
    reviewer: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    return review_admin_request(request, db, reviewer, user_id, approve=True)

@router.post("/users/{user_id}/reject")
def reject_admin_request(
    user_id: int,
    request: Request,
    reviewer: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    return review_admin_request(request, db, reviewer, user_id, approve=False)

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