from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import auth, database, crud, schemas, models, scheduler
from app.routers import auth as auth_router

router = APIRouter(
    prefix="/operator",
    tags=["Operator"],
    dependencies=[Depends(auth.require_roles(models.Role.OPERATOR))],
)
templates = Jinja2Templates(directory="app/templates")

OPEN_TICKET_STATUSES = (models.TicketStatus.OPEN, models.TicketStatus.ASSIGNED,
                        models.TicketStatus.IN_PROGRESS, models.TicketStatus.CANNOT_FIX)


def back_to_console(request: Request, message: str):
    request.session["flash"] = message
    return RedirectResponse(url="/operator", status_code=303)


def send_sms_warnings(db: Session, alert: models.Alert, operator: models.UserAccount) -> int:
    """sendSMSWarning(): notify every consumer fed by the affected substation.

    There is no SMS gateway wired up yet (it is an external component in the deployment
    diagram), so each message is written to the audit log instead of being sent.
    """
    if not alert.subStationID:
        return 0
    consumers = db.query(models.Consumer).filter(models.Consumer.subStationID == alert.subStationID).all()
    for consumer in consumers:
        print(f"[SMS stub] {consumer.contactNo}: Grid alert active at your substation.")
    crud.log_action(
        db, "SMS_WARNING_SENT",
        f"{operator.username} sent grid warnings to {len(consumers)} consumer(s) for alert #{alert.alertID}",
        operator.userID,
    )
    return len(consumers)


@router.get("/")
def operator_dashboard(
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    alerts = crud.get_alerts(db)
    return templates.TemplateResponse(
        request,
        "operator.html",
        {
            "title": "Operator Dashboard",
            "substations": crud.get_substations(db),
            "consumers": crud.get_consumers(db),
            "portal_logins": crud.get_portal_logins(db),
            "alerts": alerts,
            "technicians": crud.get_technicians(db),
            "available_technicians": crud.get_technicians(db, only_available=True),
            "tickets": crud.get_tickets(db),
            "tickets_awaiting_review": crud.get_tickets(db, statuses=(models.TicketStatus.RESOLVED,)),
            "open_tickets": crud.get_tickets(db, statuses=OPEN_TICKET_STATUSES),
            "grid_risk": crud.get_grid_risk_overview(db),
            "prediction_interval_label": scheduler.interval_label(),
            "alert_risk": crud.get_alert_risk_context(db, alerts),
            "alert_threshold": crud.get_float_setting(db, "alert_threshold"),
            "unresolved_statuses": scheduler.UNRESOLVED_ALERT_STATUSES,
            "flash": request.session.pop("flash", None),
        }
    )


@router.post("/consumer")
def register_consumer(
    request: Request,
    name: str = Form(...),
    address: str = Form(...),
    contactNo: str = Form(...),
    subStationID: int = Form(...),
    connectionStatus: str = Form("ACTIVE"),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    consumer = crud.create_consumer(db, schemas.ConsumerCreate(
        name=name.strip(),
        address=address.strip(),
        contactNo=contactNo.strip(),
        subStationID=subStationID,
        connectionStatus=connectionStatus
    ))
    crud.log_action(db, "CONSUMER_REGISTERED",
                    f"{user.username} registered consumer '{consumer.name}' on substation {subStationID}",
                    user.userID)
    return back_to_console(request, f"Registered {consumer.name}.")


@router.post("/consumer/{consumer_id}/status")
def update_connection_status(
    consumer_id: int,
    request: Request,
    connectionStatus: str = Form(...),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """Verify Consumer Details: switch a connection between active and disconnected."""
    consumer = crud.get_consumer(db, consumer_id)
    if consumer is None:
        return back_to_console(request, "That consumer no longer exists.")
    if connectionStatus not in ("ACTIVE", "DISCONNECTED"):
        return back_to_console(request, "Unknown connection status.")

    crud.update_consumer(db, consumer, connectionStatus=connectionStatus)
    crud.log_action(db, "CONSUMER_STATUS_CHANGED",
                    f"{user.username} set {consumer.name} to {connectionStatus}", user.userID)
    return back_to_console(request, f"{consumer.name} is now {connectionStatus}.")


@router.post("/consumer/{consumer_id}/portal-access")
def create_portal_login(
    consumer_id: int,
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """Issue a portal login for one consumer, so they can see their own usage and nobody else's."""
    consumer = crud.get_consumer(db, consumer_id)
    if consumer is None:
        return back_to_console(request, "That consumer no longer exists.")
    if crud.get_portal_login(db, consumer_id) is not None:
        return back_to_console(request, f"{consumer.name} already has portal access.")

    username = username.strip().lower()
    if not auth_router.USERNAME_PATTERN.fullmatch(username):
        return back_to_console(request, "Username must be 3-30 characters: letters, numbers, dots, "
                                        "underscores or hyphens.")
    if crud.get_user_by_username(db, username):
        return back_to_console(request, "That username is already taken.")
    if auth_router.weak_password(password):
        return back_to_console(request, "The portal password needs at least 8 characters, with a letter "
                                        "and a number.")

    crud.create_user(db, schemas.UserAccountCreate(
        username=username,
        password=password,
        role=models.Role.CONSUMER,
        name=consumer.name,
        phone=consumer.contactNo,
        consumerID=consumer.consumerID,
    ))
    crud.log_action(db, "PORTAL_ACCESS_CREATED",
                    f"{user.username} issued portal login '{username}' for consumer {consumer_id}", user.userID)
    return back_to_console(request, f"Portal access created for {consumer.name} (username {username}).")


@router.post("/ticket")
def create_ticket(
    request: Request,
    alertID: int = Form(...),
    assignedTechnicianID: str = Form(""),
    resolutionNotes: str = Form(""),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """createMaintenanceTicket() + assignTechnician() (UC-05).

    With no technician chosen, or none free, the ticket is queued instead of being dropped.
    """
    alert = crud.get_alert(db, alertID)
    if alert is None:
        return back_to_console(request, "That alert no longer exists.")

    technician = None
    if assignedTechnicianID:
        technician = crud.get_user(db, int(assignedTechnicianID))
        if technician is None or technician.role != models.Role.TECHNICIAN or not technician.isActive:
            return back_to_console(request, "That technician is not available.")
        if technician.availabilityStatus == models.Availability.BUSY:
            return back_to_console(request, f"{technician.name or technician.username} is busy on another job.")

    ticket = crud.create_maintenance_ticket(db, schemas.MaintenanceTicketCreate(
        alertID=alertID,
        assignedTechnicianID=technician.userID if technician else None,
        ticketStatus=models.TicketStatus.ASSIGNED if technician else models.TicketStatus.OPEN,
        resolutionNotes=resolutionNotes.strip() or None,
    ))
    crud.save_ticket(db, ticket, operatorID=user.userID,
                     assignedDate=datetime.utcnow() if technician else None)

    if technician:
        crud.set_alert_status(db, alert, models.AlertStatus.IN_PROGRESS)
        crud.log_action(db, "TICKET_ASSIGNED",
                        f"{user.username} assigned ticket #{ticket.ticketID} to {technician.username}",
                        user.userID)
        return back_to_console(
            request, f"Ticket #{ticket.ticketID} dispatched to {technician.name or technician.username}.")

    crud.log_action(db, "TICKET_QUEUED",
                    f"{user.username} queued ticket #{ticket.ticketID}: no field unit available", user.userID)
    return back_to_console(
        request, f"No field units available. Ticket #{ticket.ticketID} is queued for the next free technician.")


@router.post("/ticket/{ticket_id}/assign")
def assign_ticket(
    ticket_id: int,
    request: Request,
    assignedTechnicianID: int = Form(...),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """Dispatch a queued ticket, or redispatch one a technician handed back."""
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None or ticket.ticketStatus not in (models.TicketStatus.OPEN, models.TicketStatus.CANNOT_FIX):
        return back_to_console(request, "That ticket cannot be assigned right now.")

    technician = crud.get_user(db, assignedTechnicianID)
    if technician is None or technician.role != models.Role.TECHNICIAN or not technician.isActive:
        return back_to_console(request, "That technician is not available.")
    if technician.availabilityStatus == models.Availability.BUSY:
        return back_to_console(request, f"{technician.name or technician.username} is busy on another job.")

    crud.save_ticket(db, ticket, assignedTechnicianID=technician.userID,
                     ticketStatus=models.TicketStatus.ASSIGNED, assignedDate=datetime.utcnow())
    if ticket.alert is not None:
        crud.set_alert_status(db, ticket.alert, models.AlertStatus.IN_PROGRESS)
    crud.log_action(db, "TICKET_ASSIGNED",
                    f"{user.username} assigned ticket #{ticket.ticketID} to {technician.username}", user.userID)
    return back_to_console(request, f"Ticket #{ticket.ticketID} sent to {technician.name or technician.username}.")


@router.post("/ticket/{ticket_id}/close")
def close_ticket(
    ticket_id: int,
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """Operator confirms the technician's repair: close the ticket, the alert and restore the substation."""
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None or ticket.ticketStatus != models.TicketStatus.RESOLVED:
        return back_to_console(request, "Only a resolved ticket can be closed.")

    crud.save_ticket(db, ticket, ticketStatus=models.TicketStatus.CLOSED)
    alert = ticket.alert
    if alert is not None:
        crud.set_alert_status(db, alert, models.AlertStatus.CLOSED)
        if alert.substation is not None:
            crud.update_substation(db, alert.substation, stationStatus=models.StationStatus.ACTIVE)
    crud.log_action(db, "TICKET_CLOSED",
                    f"{user.username} verified and closed ticket #{ticket.ticketID}", user.userID)
    return back_to_console(request, f"Ticket #{ticket.ticketID} closed and the alert cleared.")


@router.post("/ticket/{ticket_id}/reopen")
def reopen_ticket(
    ticket_id: int,
    request: Request,
    reason: str = Form(""),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """Operator is not satisfied: send the job back to the technician."""
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None or ticket.ticketStatus != models.TicketStatus.RESOLVED:
        return back_to_console(request, "Only a resolved ticket can be sent back.")

    reason = reason.strip()
    notes = f"{ticket.resolutionNotes or ''}\nReturned by operator: {reason}".strip() if reason \
        else ticket.resolutionNotes
    crud.save_ticket(
        db, ticket,
        ticketStatus=models.TicketStatus.ASSIGNED if ticket.assignedTechnicianID else models.TicketStatus.OPEN,
        resolvedDate=None,
        resolutionNotes=notes,
    )
    if ticket.alert is not None:
        crud.set_alert_status(db, ticket.alert, models.AlertStatus.IN_PROGRESS)
    crud.log_action(db, "TICKET_REOPENED",
                    f"{user.username} sent ticket #{ticket.ticketID} back to the technician", user.userID)
    return back_to_console(request, f"Ticket #{ticket.ticketID} sent back for more work.")


@router.post("/alert/verify/{alert_id}")
def verify_alert(
    alert_id: int,
    request: Request,
    action: str = Form(...),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """verifyAlert(): confirm a real fault and warn consumers, or dismiss a false alarm."""
    alert = crud.get_alert(db, alert_id)
    if alert is None:
        return back_to_console(request, "That alert no longer exists.")

    if action == "VERIFY":
        crud.set_alert_status(db, alert, models.AlertStatus.VERIFIED_HIGH_SEVERITY)
        warned = send_sms_warnings(db, alert, user)
        crud.log_action(db, "ALERT_VERIFIED", f"{user.username} verified alert #{alert.alertID}", user.userID)
        return back_to_console(request, f"Alert #{alert.alertID} verified. {warned} consumer(s) warned.")

    crud.set_alert_status(db, alert, models.AlertStatus.DISMISSED)
    crud.log_action(db, "ALERT_DISMISSED", f"{user.username} dismissed alert #{alert.alertID}", user.userID)
    return back_to_console(request, f"Alert #{alert.alertID} dismissed.")
