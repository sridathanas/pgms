from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import auth, crud, database, models, uploads

router = APIRouter(
    prefix="/technician",
    tags=["Technician"],
    dependencies=[Depends(auth.require_roles(models.Role.TECHNICIAN))],
)
templates = Jinja2Templates(directory="app/templates")

ACTIVE_STATUSES = (models.TicketStatus.ASSIGNED, models.TicketStatus.IN_PROGRESS)
FINISHED_STATUSES = (models.TicketStatus.RESOLVED, models.TicketStatus.CLOSED,
                     models.TicketStatus.CANNOT_FIX)


def back_to_jobs(request: Request, message: str):
    request.session["flash"] = message
    return RedirectResponse(url="/technician/", status_code=303)


def own_open_ticket(db: Session, ticket_id: int, technician: models.UserAccount):
    """The technician's own ticket, if it is still workable. None otherwise."""
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None or ticket.assignedTechnicianID != technician.userID:
        return None
    if ticket.ticketStatus not in ACTIVE_STATUSES:
        return None
    return ticket


@router.get("/")
def technician_dashboard(
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """viewAvailableJobs(): jobs dispatched to me, plus anything waiting in the queue."""
    return templates.TemplateResponse(
        request,
        "technician.html",
        {
            "title": "My Jobs",
            "my_jobs": crud.get_tickets(db, statuses=ACTIVE_STATUSES, technician_id=user.userID),
            "queue": crud.get_tickets(db, statuses=(models.TicketStatus.OPEN,), unassigned=True),
            "history": crud.get_tickets(db, statuses=FINISHED_STATUSES, technician_id=user.userID),
            "availability": user.availabilityStatus or models.Availability.AVAILABLE,
            "flash": request.session.pop("flash", None),
        }
    )


@router.post("/jobs/{ticket_id}/accept")
def accept_job(
    ticket_id: int,
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """acceptJob(): take the job, mark it in progress and show as busy."""
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None:
        return back_to_jobs(request, "That job no longer exists.")

    claimable = ticket.assignedTechnicianID is None and ticket.ticketStatus == models.TicketStatus.OPEN
    mine = ticket.assignedTechnicianID == user.userID and ticket.ticketStatus == models.TicketStatus.ASSIGNED
    if not (claimable or mine):
        return back_to_jobs(request, "That job has already been taken by someone else.")

    crud.save_ticket(
        db, ticket,
        assignedTechnicianID=user.userID,
        ticketStatus=models.TicketStatus.IN_PROGRESS,
        assignedDate=ticket.assignedDate or datetime.utcnow(),
    )
    crud.set_technician_availability(db, user, models.Availability.BUSY)
    if ticket.alert is not None and ticket.alert.status != models.AlertStatus.CLOSED:
        crud.set_alert_status(db, ticket.alert, models.AlertStatus.IN_PROGRESS)
    crud.log_action(db, "TICKET_ACCEPTED", f"{user.username} accepted ticket #{ticket.ticketID}", user.userID)
    return back_to_jobs(request, f"Job #{ticket.ticketID} accepted. You are now marked busy.")


@router.post("/jobs/{ticket_id}/proof")
def upload_proof(
    ticket_id: int,
    request: Request,
    photo: UploadFile = File(None),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """uploadProofPhoto(): attach a site photo to the ticket."""
    ticket = own_open_ticket(db, ticket_id, user)
    if ticket is None:
        return back_to_jobs(request, "You can only add photos to a job you have accepted.")

    try:
        path = uploads.save_proof_photo(photo, ticket.ticketID)
    except uploads.UploadError as e:
        return back_to_jobs(request, str(e))

    crud.save_ticket(db, ticket, proofPhotoPath=path)
    crud.log_action(db, "TICKET_PROOF_UPLOADED",
                    f"{user.username} uploaded proof for ticket #{ticket.ticketID}", user.userID)
    return back_to_jobs(request, f"Photo added to job #{ticket.ticketID}.")


@router.post("/jobs/{ticket_id}/status")
def update_ticket_status(
    ticket_id: int,
    request: Request,
    outcome: str = Form(...),
    notes: str = Form(""),
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """updateTicketStatus(): finish the job, or hand it back when it cannot be fixed."""
    ticket = own_open_ticket(db, ticket_id, user)
    if ticket is None:
        return back_to_jobs(request, "You can only update a job you have accepted.")

    notes = notes.strip()
    if outcome == "RESOLVED":
        if not ticket.proofPhotoPath:
            return back_to_jobs(request, "Upload a proof photo before marking the job resolved.")
        crud.save_ticket(
            db, ticket,
            ticketStatus=models.TicketStatus.RESOLVED,
            resolvedDate=datetime.utcnow(),
            resolutionNotes=notes or ticket.resolutionNotes,
        )
        crud.set_technician_availability(db, user, models.Availability.AVAILABLE)
        crud.log_action(db, "TICKET_RESOLVED",
                        f"{user.username} resolved ticket #{ticket.ticketID}; awaiting operator review",
                        user.userID)
        return back_to_jobs(request, f"Job #{ticket.ticketID} marked resolved. The operator will review it.")

    if outcome == "CANNOT_FIX":
        if not notes:
            return back_to_jobs(request, "Explain what blocked the repair before handing the job back.")
        crud.save_ticket(
            db, ticket,
            ticketStatus=models.TicketStatus.CANNOT_FIX,
            assignedTechnicianID=None,  # back to the queue so the operator can redispatch
            resolutionNotes=notes,
        )
        crud.set_technician_availability(db, user, models.Availability.AVAILABLE)
        if ticket.alert is not None:
            ticket.alert.severity = "HIGH"  # escalate, per Activity Diagram 3
            crud.set_alert_status(db, ticket.alert, models.AlertStatus.VERIFIED_HIGH_SEVERITY)
        crud.log_action(db, "TICKET_CANNOT_FIX",
                        f"{user.username} could not fix ticket #{ticket.ticketID}: {notes[:120]}", user.userID)
        return back_to_jobs(request, f"Job #{ticket.ticketID} sent back to the operator and escalated.")

    return back_to_jobs(request, "Choose either Resolved or Cannot fix.")
