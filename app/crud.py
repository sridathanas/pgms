from sqlalchemy.orm import Session
from app import models, schemas  # Explicit app import

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