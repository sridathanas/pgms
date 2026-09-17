from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import auth, database, models

router = APIRouter(
    prefix="/technician",
    tags=["Technician"],
    dependencies=[Depends(auth.require_roles(models.Role.TECHNICIAN))],
)
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def technician_dashboard(
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    tickets = (
        db.query(models.MaintenanceTicket)
        .filter(models.MaintenanceTicket.assignedTechnicianID == user.userID)
        .order_by(models.MaintenanceTicket.createdDate.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "technician.html",
        {"title": "My Jobs", "tickets": tickets}
    )
