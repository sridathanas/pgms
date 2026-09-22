from sqlalchemy.orm import Session
from app import models, schemas, security  # Explicit app import

# User Account Operations
def get_user(db: Session, user_id: int):
    return db.query(models.UserAccount).filter(models.UserAccount.userID == user_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.UserAccount).filter(models.UserAccount.username == username).first()

def create_user(db: Session, user: schemas.UserAccountCreate):
    db_user = models.UserAccount(
        **user.model_dump(exclude={"password"}),
        passwordHash=security.hash_password(user.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def has_approved_admin(db: Session) -> bool:
    return db.query(models.UserAccount.userID).filter(
        models.UserAccount.role == models.Role.ADMIN,
        models.UserAccount.approvalStatus == models.ApprovalStatus.APPROVED,
        models.UserAccount.isActive.is_(True),
    ).first() is not None

def get_pending_admins(db: Session):
    return db.query(models.UserAccount).filter(
        models.UserAccount.role == models.Role.ADMIN,
        models.UserAccount.approvalStatus == models.ApprovalStatus.PENDING,
    ).order_by(models.UserAccount.createdAt).all()

def set_approval_status(db: Session, user: models.UserAccount, status: str):
    user.approvalStatus = status
    db.commit()
    db.refresh(user)
    return user

# System Log Operations
def log_action(db: Session, action_type: str, description: str, user_id: int | None = None):
    db_log = models.SystemLog(userID=user_id, actionType=action_type, description=description)
    db.add(db_log)
    db.commit()
    return db_log

# Power Station Operations
def get_power_stations(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.PowerStation).offset(skip).limit(limit).all()

def create_power_station(db: Session, station: schemas.PowerStationCreate):
    db_station = models.PowerStation(**station.model_dump())
    db.add(db_station)
    db.commit()
    db.refresh(db_station)
    return db_station


# Substation Operations
def get_substations(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Substation).offset(skip).limit(limit).all()

def create_substation(db: Session, substation: schemas.SubstationCreate):
    db_substation = models.Substation(**substation.model_dump())
    db.add(db_substation)
    db.commit()
    db.refresh(db_substation)
    return db_substation

# Consumer Operations
def get_consumers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Consumer).offset(skip).limit(limit).all()

def create_consumer(db: Session, consumer: schemas.ConsumerCreate):
    db_consumer = models.Consumer(**consumer.model_dump())
    db.add(db_consumer)
    db.commit()
    db.refresh(db_consumer)
    return db_consumer

# AI Prediction & Telemetry Operations
def _latest_by_substation(db: Session, model):
    """Newest row per substation, keyed by subStationID."""
    rows = db.query(model).order_by(model.timeStamp.desc()).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.subStationID, row)
    return latest

def get_alert_risk_context(db: Session, alerts):
    """For each substation alert: the risk score when it was raised, and the score right now.

    Alerts are only closed by a person, so an alert can outlive the conditions that caused it.
    Pairing both scores lets the operator spot one that no longer matches the grid.
    Keyed by alertID; alerts not tied to a substation (e.g. theft) are left out.
    """
    latest = _latest_by_substation(db, models.OutagePrediction)
    context = {}
    for alert in alerts:
        if not alert.subStationID:
            continue
        raised = (
            db.query(models.OutagePrediction)
            .filter(
                models.OutagePrediction.subStationID == alert.subStationID,
                models.OutagePrediction.timeStamp <= alert.timeStamp,
            )
            .order_by(models.OutagePrediction.timeStamp.desc())
            .first()
        )
        context[alert.alertID] = {"raised": raised, "current": latest.get(alert.subStationID)}
    return context

def get_grid_risk_overview(db: Session):
    """Each substation with its most recent AI prediction and telemetry, for the dashboards."""
    predictions = _latest_by_substation(db, models.OutagePrediction)
    sensors = _latest_by_substation(db, models.SubstationSensorLog)
    weather = _latest_by_substation(db, models.WeatherData)
    return [
        {
            "substation": sub,
            "prediction": predictions.get(sub.subStationID),
            "sensor": sensors.get(sub.subStationID),
            "weather": weather.get(sub.subStationID),
        }
        for sub in get_substations(db)
    ]

# Alert & Maintenance Operations
def create_alert(db: Session, alert: schemas.AlertCreate):
    db_alert = models.Alert(**alert.model_dump())
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

def create_maintenance_ticket(db: Session, ticket: schemas.MaintenanceTicketCreate):
    db_ticket = models.MaintenanceTicket(**ticket.model_dump())
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket