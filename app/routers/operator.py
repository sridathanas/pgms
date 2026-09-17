from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import auth, database, crud, schemas, models

router = APIRouter(
    prefix="/operator",
    tags=["Operator"],
    dependencies=[Depends(auth.require_roles(models.Role.OPERATOR))],
)
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def operator_dashboard(request: Request, db: Session = Depends(database.get_db)):
    substations = crud.get_substations(db)
    consumers = crud.get_consumers(db)
    alerts = db.query(models.Alert).all()
    technicians = db.query(models.UserAccount).filter(models.UserAccount.role == models.Role.TECHNICIAN).all()
    tickets = db.query(models.MaintenanceTicket).all()
   
    return templates.TemplateResponse(
        request,
        "operator.html",
        {
            "title": "Operator Dashboard",
            "substations": substations,
            "consumers": consumers,
            "alerts": alerts,
            "technicians": technicians,
            "tickets": tickets
        }
    )

@router.post("/consumer")
def register_consumer(
    name: str = Form(...),
    address: str = Form(...),
    contactNo: str = Form(...),
    subStationID: int = Form(...),
    connectionStatus: str = Form("ACTIVE"),
    db: Session = Depends(database.get_db)
):
    consumer_data = schemas.ConsumerCreate(
        name=name,
        address=address,
        contactNo=contactNo,
        subStationID=subStationID,
        connectionStatus=connectionStatus
    )
    crud.create_consumer(db, consumer_data)
    return RedirectResponse(url="/operator", status_code=303)

@router.post("/ticket")
def create_ticket(
    alertID: int = Form(...),
    assignedTechnicianID: int = Form(...),
    ticketStatus: str = Form("ASSIGNED"),
    resolutionNotes: str = Form(None),
    db: Session = Depends(database.get_db)
):
    ticket_data = schemas.MaintenanceTicketCreate(
        alertID=alertID,
        assignedTechnicianID=assignedTechnicianID,
        ticketStatus=ticketStatus,
        resolutionNotes=resolutionNotes
    )
    crud.create_maintenance_ticket(db, ticket_data)
    return RedirectResponse(url="/operator", status_code=303)

@router.post("/alert/verify/{alert_id}")
def verify_alert(
    alert_id: int,
    action: str = Form(...),
    db: Session = Depends(database.get_db)
):
    alert = db.query(models.Alert).filter(models.Alert.alertID == alert_id).first()
    if alert:
        if action == "VERIFY":
            alert.status = "VERIFIED_HIGH_SEVERITY"
            if alert.subStationID:
                consumers = db.query(models.Consumer).filter(models.Consumer.subStationID == alert.subStationID).all()
                for consumer in consumers:
                    print(f"Sending SMS Warning to {consumer.contactNo}: Grid alert active at your substation.")
        else:
            alert.status = "DISMISSED"
        db.commit()
    return RedirectResponse(url="/operator", status_code=303)