from fastapi import APIRouter, Depends, Request, Form
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import database, models

router = APIRouter(
    prefix="/portal",
    tags=["Consumer Portal"]
)

templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def consumer_portal_lookup(request: Request):
    """Renders the initial lookup form for the Consumer Portal."""
    return templates.TemplateResponse(
        request,
        "consumer.html",
        {"title": "Consumer Portal - PGMS"}
    )

@router.post("/")
def consumer_dashboard(
    request: Request,
    consumer_id: int = Form(..., alias="consumerID"),
    db: Session = Depends(database.get_db)
):
    """Fetches consumer connection status and historical usage logs (Requirement F6)."""
    consumer = db.query(models.Consumer).filter(models.Consumer.consumerID == consumer_id).first()
    
    if not consumer:
        return templates.TemplateResponse(
            request,
            "consumer.html",
            {
                "title": "Consumer Portal - PGMS",
                "error": "Consumer ID not found. Please contact the regional operator."
            }
        )

    # Retrieve up to 30 days of historical consumption data
    usage_logs = (
        db.query(models.UsageLog)
        .filter(models.UsageLog.consumerID == consumer_id)
        .order_by(models.UsageLog.timeStamp.desc())
        .limit(30)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "consumer.html",
        {
            "title": f"My Grid Usage - {consumer.name}",
            "consumer": consumer,
            "usage_logs": usage_logs
        }
    )