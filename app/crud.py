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

def get_users(db: Session):
    return db.query(models.UserAccount).order_by(models.UserAccount.role, models.UserAccount.username).all()

def set_user_active(db: Session, user: models.UserAccount, is_active: bool):
    user.isActive = is_active
    db.commit()
    db.refresh(user)
    return user

def get_technicians(db: Session, only_available: bool = False):
    query = db.query(models.UserAccount).filter(
        models.UserAccount.role == models.Role.TECHNICIAN,
        models.UserAccount.isActive.is_(True),
    )
    if only_available:
        # Anything other than BUSY counts as free, including accounts with no status yet
        query = query.filter((models.UserAccount.availabilityStatus != models.Availability.BUSY)
                             | models.UserAccount.availabilityStatus.is_(None))
    return query.order_by(models.UserAccount.username).all()

def set_technician_availability(db: Session, technician: models.UserAccount, status: str):
    technician.availabilityStatus = status
    db.commit()
    return technician

# System Settings (adjustAIThresholds)
DEFAULT_SETTINGS = {
    "alert_threshold": "0.80",
    "medium_risk_threshold": "0.50",
    "variance_threshold": "0.50",  # theft detection: how far usage may drift from the baseline
}

def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    row = db.query(models.SystemSetting).filter(models.SystemSetting.settingKey == key).first()
    if row is not None:
        return row.settingValue
    return default if default is not None else DEFAULT_SETTINGS.get(key)

def get_float_setting(db: Session, key: str) -> float:
    try:
        return float(get_setting(db, key))
    except (TypeError, ValueError):
        return float(DEFAULT_SETTINGS[key])

def set_setting(db: Session, key: str, value: str, user_id: int | None = None):
    from datetime import datetime
    row = db.query(models.SystemSetting).filter(models.SystemSetting.settingKey == key).first()
    if row is None:
        row = models.SystemSetting(settingKey=key)
        db.add(row)
    row.settingValue = value
    row.updatedAt = datetime.utcnow()
    row.updatedByUserID = user_id
    db.commit()
    return row

def get_system_logs(db: Session, limit: int = 100, action_type: str | None = None):
    query = db.query(models.SystemLog)
    if action_type:
        query = query.filter(models.SystemLog.actionType == action_type)
    return query.order_by(models.SystemLog.logID.desc()).limit(limit).all()

def get_log_action_types(db: Session):
    return [r[0] for r in db.query(models.SystemLog.actionType).distinct().order_by(models.SystemLog.actionType)]

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

def get_power_station(db: Session, station_id: int):
    return db.query(models.PowerStation).filter(models.PowerStation.powerStationID == station_id).first()

def power_station_name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    """F3: two stations must not share a name."""
    query = db.query(models.PowerStation.powerStationID).filter(models.PowerStation.stationName == name)
    if exclude_id is not None:
        query = query.filter(models.PowerStation.powerStationID != exclude_id)
    return query.first() is not None

def update_power_station(db: Session, station: models.PowerStation, **fields):
    for key, value in fields.items():
        setattr(station, key, value)
    db.commit()
    db.refresh(station)
    return station

def delete_power_station(db: Session, station: models.PowerStation):
    db.delete(station)
    db.commit()

# Substation Operations
def get_substations(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Substation).offset(skip).limit(limit).all()

def create_substation(db: Session, substation: schemas.SubstationCreate):
    db_substation = models.Substation(**substation.model_dump())
    db.add(db_substation)
    db.commit()
    db.refresh(db_substation)
    return db_substation

def get_substation(db: Session, substation_id: int):
    return db.query(models.Substation).filter(models.Substation.subStationID == substation_id).first()

def substation_name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = db.query(models.Substation.subStationID).filter(models.Substation.subStationName == name)
    if exclude_id is not None:
        query = query.filter(models.Substation.subStationID != exclude_id)
    return query.first() is not None

def update_substation(db: Session, substation: models.Substation, **fields):
    for key, value in fields.items():
        setattr(substation, key, value)
    db.commit()
    db.refresh(substation)
    return substation

def delete_substation(db: Session, substation: models.Substation):
    """Remove a substation and the telemetry rows that belong to it."""
    sub_id = substation.subStationID
    for model in (models.OutagePrediction, models.WeatherData, models.SubstationSensorLog):
        db.query(model).filter(model.subStationID == sub_id).delete(synchronize_session=False)
    db.delete(substation)
    db.commit()

def count_substations_of(db: Session, station_id: int) -> int:
    return db.query(models.Substation).filter(models.Substation.powerStationID == station_id).count()

def count_consumers_of(db: Session, substation_id: int) -> int:
    return db.query(models.Consumer).filter(models.Consumer.subStationID == substation_id).count()

def count_open_alerts_of(db: Session, substation_id: int) -> int:
    return db.query(models.Alert).filter(
        models.Alert.subStationID == substation_id,
        models.Alert.status.in_((models.AlertStatus.OPEN, models.AlertStatus.VERIFIED_HIGH_SEVERITY,
                                 models.AlertStatus.IN_PROGRESS)),
    ).count()

# Consumer Operations
def get_consumers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Consumer).offset(skip).limit(limit).all()

def create_consumer(db: Session, consumer: schemas.ConsumerCreate):
    db_consumer = models.Consumer(**consumer.model_dump())
    db.add(db_consumer)
    db.commit()
    db.refresh(db_consumer)
    return db_consumer

def get_consumer(db: Session, consumer_id: int):
    return db.query(models.Consumer).filter(models.Consumer.consumerID == consumer_id).first()

def get_portal_login(db: Session, consumer_id: int):
    """The portal account tied to this consumer, if an operator has issued one."""
    return db.query(models.UserAccount).filter(
        models.UserAccount.role == models.Role.CONSUMER,
        models.UserAccount.consumerID == consumer_id,
    ).first()

def get_portal_logins(db: Session) -> dict:
    """consumerID -> portal account, for the operator's consumer table."""
    rows = db.query(models.UserAccount).filter(models.UserAccount.role == models.Role.CONSUMER).all()
    return {row.consumerID: row for row in rows if row.consumerID}

def update_consumer(db: Session, consumer: models.Consumer, **fields):
    for key, value in fields.items():
        setattr(consumer, key, value)
    db.commit()
    db.refresh(consumer)
    return consumer

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

def get_alert(db: Session, alert_id: int):
    return db.query(models.Alert).filter(models.Alert.alertID == alert_id).first()

def get_alerts(db: Session):
    return db.query(models.Alert).order_by(models.Alert.alertID.desc()).all()

def get_ticket(db: Session, ticket_id: int):
    return db.query(models.MaintenanceTicket).filter(models.MaintenanceTicket.ticketID == ticket_id).first()

def get_tickets(db: Session, statuses: tuple[str, ...] | None = None, technician_id: int | None = None,
                unassigned: bool = False):
    query = db.query(models.MaintenanceTicket)
    if statuses:
        query = query.filter(models.MaintenanceTicket.ticketStatus.in_(statuses))
    if technician_id is not None:
        query = query.filter(models.MaintenanceTicket.assignedTechnicianID == technician_id)
    if unassigned:
        query = query.filter(models.MaintenanceTicket.assignedTechnicianID.is_(None))
    return query.order_by(models.MaintenanceTicket.ticketID.desc()).all()

def save_ticket(db: Session, ticket: models.MaintenanceTicket, **fields):
    for key, value in fields.items():
        setattr(ticket, key, value)
    db.commit()
    db.refresh(ticket)
    return ticket

def set_alert_status(db: Session, alert: models.Alert, status: str):
    alert.status = status
    db.commit()
    return alert

# Reporting (F16 Grid Health Report)
def build_grid_health_report(db: Session):
    """Totals an administrator needs for the daily grid health summary."""
    from datetime import datetime, timedelta

    risk_rows = get_grid_risk_overview(db)
    total_load = sum(row["sensor"].currentLoadMW for row in risk_rows if row["sensor"])
    total_capacity = sum(row["substation"].maxLoadCapacityMW or 0 for row in risk_rows)
    day_ago = datetime.utcnow() - timedelta(days=1)

    alerts = get_alerts(db)
    active_statuses = (models.AlertStatus.OPEN, models.AlertStatus.VERIFIED_HIGH_SEVERITY,
                       models.AlertStatus.IN_PROGRESS)
    tickets = db.query(models.MaintenanceTicket).all()

    return {
        "generated_at": datetime.utcnow(),
        "substation_count": len(risk_rows),
        "power_station_count": db.query(models.PowerStation).count(),
        "consumer_count": db.query(models.Consumer).count(),
        "total_load_mw": total_load,
        "total_capacity_mw": total_capacity,
        "load_percentage": (total_load / total_capacity * 100) if total_capacity else 0.0,
        "high_risk": [r for r in risk_rows if r["prediction"] and r["prediction"].riskLevel == "HIGH"],
        "active_alerts": [a for a in alerts if a.status in active_statuses],
        "alerts_last_24h": [a for a in alerts if a.timeStamp and a.timeStamp >= day_ago],
        "tickets_open": [t for t in tickets if t.ticketStatus in
                         (models.TicketStatus.OPEN, models.TicketStatus.ASSIGNED,
                          models.TicketStatus.IN_PROGRESS, models.TicketStatus.CANNOT_FIX)],
        "tickets_awaiting_review": [t for t in tickets if t.ticketStatus == models.TicketStatus.RESOLVED],
        "tickets_closed_24h": [t for t in tickets if t.ticketStatus == models.TicketStatus.CLOSED
                               and t.resolvedDate and t.resolvedDate >= day_ago],
        "risk_rows": risk_rows,
    }