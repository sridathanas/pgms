from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import auth, crud, database, models

# Consumers sign in like everyone else; the portal only ever shows the record their
# account is tied to. Looking a consumer up by ID alone would expose every household's
# name, address and consumption to anyone who can reach the site.
router = APIRouter(
    prefix="/portal",
    tags=["Consumer Portal"],
    dependencies=[Depends(auth.require_roles(models.Role.CONSUMER))],
)

templates = Jinja2Templates(directory="app/templates")

USAGE_HISTORY_DAYS = 30


@router.get("/")
def consumer_dashboard(
    request: Request,
    user: models.UserAccount = Depends(auth.require_login),
    db: Session = Depends(database.get_db)
):
    """Connection status and recent consumption for the signed-in consumer (F6)."""
    consumer = crud.get_consumer(db, user.consumerID) if user.consumerID else None

    usage_logs = []
    if consumer is not None:
        usage_logs = (
            db.query(models.UsageLog)
            .filter(models.UsageLog.consumerID == consumer.consumerID)
            .order_by(models.UsageLog.timeStamp.desc())
            .limit(USAGE_HISTORY_DAYS)
            .all()
        )

    total = sum(log.consumptionKWH for log in usage_logs)
    return templates.TemplateResponse(
        request,
        "consumer.html",
        {
            "title": "My Grid Usage",
            "consumer": consumer,
            "usage_logs": usage_logs,
            "total_kwh": total,
            "average_kwh": (total / len(usage_logs)) if usage_logs else 0.0,
            "peak_log": max(usage_logs, key=lambda log: log.consumptionKWH) if usage_logs else None,
        }
    )
