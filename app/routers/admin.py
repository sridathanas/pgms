from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import auth, database, crud, schemas, models, scheduler
import csv
import io
from datetime import datetime
from fastapi.responses import StreamingResponse


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

def back_to_admin(request: Request, message: str, path: str = "/admin"):
    request.session["flash"] = message
    return RedirectResponse(url=path, status_code=303)

@router.post("/power-station")
def add_power_station(
    request: Request,
    stationName: str = Form(...),
    location: str = Form(...),
    maxCapacityMW: float = Form(...),
    status: str = Form("ACTIVE"),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    stationName = stationName.strip()
    if crud.power_station_name_taken(db, stationName):  # F3
        return back_to_admin(request, f"A power station named '{stationName}' already exists.")

    station = crud.create_power_station(db, schemas.PowerStationCreate(
        stationName=stationName,
        location=location.strip(),
        maxCapacityMW=maxCapacityMW,
        status=status
    ))
    crud.log_action(db, "POWER_STATION_ADDED",
                    f"{user.username} added power station '{station.stationName}'", user.userID)
    return back_to_admin(request, f"Added power station '{station.stationName}'.")

@router.post("/power-station/{station_id}/update")
def update_power_station(
    station_id: int,
    request: Request,
    stationName: str = Form(...),
    location: str = Form(...),
    maxCapacityMW: float = Form(...),
    status: str = Form("ACTIVE"),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """F2: keep infrastructure records current as the grid changes."""
    station = crud.get_power_station(db, station_id)
    if station is None:
        return back_to_admin(request, "That power station no longer exists.")
    stationName = stationName.strip()
    if crud.power_station_name_taken(db, stationName, exclude_id=station_id):
        return back_to_admin(request, f"A power station named '{stationName}' already exists.")

    crud.update_power_station(db, station, stationName=stationName, location=location.strip(),
                              maxCapacityMW=maxCapacityMW, status=status)
    crud.log_action(db, "POWER_STATION_UPDATED",
                    f"{user.username} updated power station #{station_id}", user.userID)
    return back_to_admin(request, f"Updated '{station.stationName}'.")

@router.post("/power-station/{station_id}/delete")
def delete_power_station(
    station_id: int,
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """F2: decommission a station, but never orphan the substations under it."""
    station = crud.get_power_station(db, station_id)
    if station is None:
        return back_to_admin(request, "That power station no longer exists.")

    child_count = crud.count_substations_of(db, station_id)
    if child_count:
        return back_to_admin(request, f"'{station.stationName}' still has {child_count} substation(s). "
                                      "Move or delete those first.")

    name = station.stationName
    crud.delete_power_station(db, station)
    crud.log_action(db, "POWER_STATION_DELETED", f"{user.username} deleted power station '{name}'", user.userID)
    return back_to_admin(request, f"Deleted '{name}'.")

@router.post("/substation")
def add_substation(
    request: Request,
    subStationName: str = Form(...),
    powerStationID: int = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    maxLoadCapacityMW: float = Form(...),
    stationStatus: str = Form("ACTIVE"),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    subStationName = subStationName.strip()
    if crud.substation_name_taken(db, subStationName):  # F3
        return back_to_admin(request, f"A substation named '{subStationName}' already exists.")
    if crud.get_power_station(db, powerStationID) is None:
        return back_to_admin(request, "Choose a valid parent power station.")

    substation = crud.create_substation(db, schemas.SubstationCreate(
        subStationName=subStationName,
        powerStationID=powerStationID,
        latitude=latitude,
        longitude=longitude,
        maxLoadCapacityMW=maxLoadCapacityMW,
        stationStatus=stationStatus
    ))
    crud.log_action(db, "SUBSTATION_ADDED",
                    f"{user.username} added substation '{substation.subStationName}'", user.userID)
    return back_to_admin(request, f"Added substation '{substation.subStationName}'.")

@router.post("/substation/{substation_id}/update")
def update_substation(
    substation_id: int,
    request: Request,
    subStationName: str = Form(...),
    maxLoadCapacityMW: float = Form(...),
    stationStatus: str = Form(...),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """updateSubstationData() from Activity Diagram 1."""
    substation = crud.get_substation(db, substation_id)
    if substation is None:
        return back_to_admin(request, "That substation no longer exists.")
    subStationName = subStationName.strip()
    if crud.substation_name_taken(db, subStationName, exclude_id=substation_id):
        return back_to_admin(request, f"A substation named '{subStationName}' already exists.")

    crud.update_substation(db, substation, subStationName=subStationName,
                           maxLoadCapacityMW=maxLoadCapacityMW, stationStatus=stationStatus)
    crud.log_action(db, "SUBSTATION_UPDATED",
                    f"{user.username} updated substation #{substation_id} ({stationStatus})", user.userID)
    return back_to_admin(request, f"Updated '{substation.subStationName}'.")

@router.get("/report.csv")
def export_grid_health_report(
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    report = crud.build_grid_health_report(db)
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["Grid Health Report"])
    writer.writerow(["Generated (UTC)", report["generated_at"].strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])

    writer.writerow(["Summary", "Value"])
    writer.writerow(["Power stations", report["power_station_count"]])
    writer.writerow(["Substations", report["substation_count"]])
    writer.writerow(["Consumers", report["consumer_count"]])
    writer.writerow(["Total load (MW)", f"{report['total_load_mw']:.1f}"])
    writer.writerow(["Total capacity (MW)", f"{report['total_capacity_mw']:.1f}"])
    writer.writerow(["Grid utilisation (%)", f"{report['load_percentage']:.1f}"])
    writer.writerow(["High risk substations", len(report["high_risk"])])
    writer.writerow(["Active alerts", len(report["active_alerts"])])
    writer.writerow(["Alerts raised (24h)", len(report["alerts_last_24h"])])
    writer.writerow(["Tickets open", len(report["tickets_open"])])
    writer.writerow(["Tickets awaiting review", len(report["tickets_awaiting_review"])])
    writer.writerow(["Tickets closed (24h)", len(report["tickets_closed_24h"])])
    writer.writerow([])

    writer.writerow(["Substation", "Station status", "Risk level", "Failure probability (%)",
                     "Current load (MW)", "Max load (MW)", "Temperature (C)", "Wind (km/h)",
                     "Humidity (%)", "Last checked (UTC)"])
    for row in report["risk_rows"]:
        substation, prediction = row["substation"], row["prediction"]
        sensor, weather = row["sensor"], row["weather"]
        writer.writerow([
            substation.subStationName,
            substation.stationStatus,
            prediction.riskLevel if prediction else "NOT SCORED",
            f"{prediction.failureProbScore * 100:.0f}" if prediction else "",
            f"{sensor.currentLoadMW:.1f}" if sensor else "",
            substation.maxLoadCapacityMW,
            f"{weather.temperature:.0f}" if weather else "",
            f"{weather.windSpeed:.0f}" if weather else "",
            f"{weather.humidity:.0f}" if weather else "",
            prediction.timeStamp.strftime("%Y-%m-%d %H:%M") if prediction else "",
        ])

    crud.log_action(db, "REPORT_EXPORTED",
                    f"{user.username} exported the grid health report as CSV", user.userID)

    filename = f"grid-health-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
    # The BOM makes Excel open it as UTF-8 instead of mangling accented names
    return StreamingResponse(
        iter(["\ufeff" + buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/substation/{substation_id}/delete")
def delete_substation(
    substation_id: int,
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    substation = crud.get_substation(db, substation_id)
    if substation is None:
        return back_to_admin(request, "That substation no longer exists.")

    consumers = crud.count_consumers_of(db, substation_id)
    if consumers:
        return back_to_admin(request, f"'{substation.subStationName}' still supplies {consumers} consumer(s). "
                                      "Move them to another substation first.")
    open_alerts = crud.count_open_alerts_of(db, substation_id)
    if open_alerts:
        return back_to_admin(request, f"'{substation.subStationName}' has {open_alerts} unresolved alert(s). "
                                      "Close them before deleting it.")

    name = substation.subStationName
    crud.delete_substation(db, substation)
    crud.log_action(db, "SUBSTATION_DELETED",
                    f"{user.username} deleted substation '{name}' and its telemetry", user.userID)
    return back_to_admin(request, f"Deleted '{name}'.")

# User management (the "Manage Users" branch of the flowchart)
@router.get("/users")
def manage_users(
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "title": "Manage Users",
            "users": crud.get_users(db),
            "current_user_id": user.userID,
            "flash": request.session.pop("flash", None),
        }
    )

@router.post("/users/{user_id}/active")
def set_user_active(
    user_id: int,
    request: Request,
    active: str = Form(...),
    admin_user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    target = crud.get_user(db, user_id)
    if target is None:
        return back_to_admin(request, "That account no longer exists.", "/admin/users")
    if target.userID == admin_user.userID:
        return back_to_admin(request, "You cannot deactivate your own account.", "/admin/users")

    make_active = active == "1"
    crud.set_user_active(db, target, make_active)
    state = "reactivated" if make_active else "deactivated"
    crud.log_action(db, f"USER_{state.upper()}",
                    f"{admin_user.username} {state} {target.username}", admin_user.userID)
    return back_to_admin(request, f"{target.name or target.username} {state}.", "/admin/users")

# Audit log ("View Global Audit Reports" / View System Logs)
@router.get("/logs")
def system_logs(
    request: Request,
    action: str = "",
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    return templates.TemplateResponse(
        request,
        "admin_logs.html",
        {
            "title": "System Logs",
            "logs": crud.get_system_logs(db, limit=200, action_type=action or None),
            "action_types": crud.get_log_action_types(db),
            "selected_action": action,
        }
    )

# adjustAIThresholds()
@router.get("/settings")
def settings_page(
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    return templates.TemplateResponse(
        request,
        "admin_settings.html",
        {
            "title": "System Settings",
            "alert_threshold": crud.get_float_setting(db, "alert_threshold"),
            "medium_threshold": crud.get_float_setting(db, "medium_risk_threshold"),
            "variance_threshold": crud.get_float_setting(db, "variance_threshold"),
            "interval_label": scheduler.interval_label(),
            "flash": request.session.pop("flash", None),
        }
    )

@router.post("/settings")
def save_settings(
    request: Request,
    alert_threshold: float = Form(...),
    medium_risk_threshold: float = Form(...),
    variance_threshold: float = Form(...),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    if not all(0.0 < value <= 1.0 for value in (alert_threshold, medium_risk_threshold, variance_threshold)):
        return back_to_admin(request, "Thresholds must be between 0 and 1.", "/admin/settings")
    if medium_risk_threshold >= alert_threshold:
        return back_to_admin(request, "The medium threshold must be lower than the alert threshold.",
                             "/admin/settings")

    crud.set_setting(db, "alert_threshold", f"{alert_threshold}", user.userID)
    crud.set_setting(db, "medium_risk_threshold", f"{medium_risk_threshold}", user.userID)
    crud.set_setting(db, "variance_threshold", f"{variance_threshold}", user.userID)
    crud.log_action(db, "AI_THRESHOLDS_UPDATED",
                    f"{user.username} set the alert threshold to {alert_threshold:.2f}, the medium "
                    f"threshold to {medium_risk_threshold:.2f} and the theft variance threshold to "
                    f"{variance_threshold:.2f}", user.userID)
    return back_to_admin(request, "AI thresholds updated. The next prediction cycle uses them.",
                         "/admin/settings")

# F16 Grid Health Report
@router.get("/report")
def grid_health_report(
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    return templates.TemplateResponse(
        request,
        "admin_report.html",
        {"title": "Grid Health Report", "report": crud.build_grid_health_report(db)}
    )