from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base  # Explicit app import
from datetime import datetime


class UserAccount(Base):
    __tablename__ = "user_accounts"
    userID = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    passwordHash = Column(String)
    role = Column(String)  # admin, operator, technician; no "consumer"
    isActive = Column(Boolean, default=True)

class PowerStation(Base):
    __tablename__ = "power_stations"
    powerStationID = Column(Integer, primary_key=True, index=True)
    stationName = Column(String, index=True)
    location = Column(String)
    maxCapacityMW = Column(Float)
    status = Column(String)

    substations = relationship("Substation", back_populates="power_station")

class Substation(Base):
    __tablename__ = "substations"
    subStationID = Column(Integer, primary_key=True, index=True)
    powerStationID = Column(Integer, ForeignKey("power_stations.powerStationID"))
    subStationName = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    maxLoadCapacityMW = Column(Float)
    stationStatus = Column(String)

    power_station = relationship("PowerStation", back_populates="substations")
    consumers = relationship("Consumer", back_populates="substation")

class Consumer(Base):
    __tablename__ = "consumers"
    consumerID = Column(Integer, primary_key=True, index=True)
    subStationID = Column(Integer, ForeignKey("substations.subStationID"))
    name = Column(String, index=True)
    address = Column(String)
    contactNo = Column(String)
    connectionStatus = Column(String)

    substation = relationship("Substation", back_populates="consumers")
    usage_logs = relationship("UsageLog", back_populates="consumer")

class UsageLog(Base):
    __tablename__ = "usage_logs"
    usageLogID = Column(Integer, primary_key=True, index=True)
    consumerID = Column(Integer, ForeignKey("consumers.consumerID"))
    timeStamp = Column(DateTime, default=datetime.utcnow)
    consumptionKWH = Column(Float)

    consumer = relationship("Consumer", back_populates="usage_logs")

class Alert(Base):
    __tablename__ = "alerts"
    alertID = Column(Integer, primary_key=True, index=True)
    subStationID = Column(Integer, ForeignKey("substations.subStationID"), nullable=True)
    consumerID = Column(Integer, ForeignKey("consumers.consumerID"), nullable=True)
    alertType = Column(String)
    severity = Column(String)
    timeStamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String)

    maintenance_tickets = relationship("MaintenanceTicket", back_populates="alert")

class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"
    ticketID = Column(Integer, primary_key=True, index=True)
    alertID = Column(Integer, ForeignKey("alerts.alertID"))
    assignedTechnicianID = Column(Integer, ForeignKey("user_accounts.userID"), nullable=True)
    createdDate = Column(DateTime, default=datetime.utcnow)
    ticketStatus = Column(String)
    resolutionNotes = Column(String, nullable=True)

    alert = relationship("Alert", back_populates="maintenance_tickets")
