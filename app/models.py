from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime


class Role:
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    TECHNICIAN = "TECHNICIAN"

class ApprovalStatus:
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"

class UserAccount(Base):
    __tablename__ = "user_accounts"
    userID = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    passwordHash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    isActive = Column(Boolean, default=True)
    approvalStatus = Column(String, nullable=False, default=ApprovalStatus.APPROVED)
    createdAt = Column(DateTime, default=datetime.utcnow)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    skillLevel = Column(String, nullable=True)
    availabilityStatus = Column(String, nullable=True)
    currentLocation = Column(String, nullable=True)

    logs = relationship("SystemLog", back_populates="user")

class SystemLog(Base):
    __tablename__ = "system_logs"
    logID = Column(Integer, primary_key=True, index=True)
    userID = Column(Integer, ForeignKey("user_accounts.userID"), nullable=True)
    actionType = Column(String, index=True)
    timeStamp = Column(DateTime, default=datetime.utcnow)
    description = Column(String)

    user = relationship("UserAccount", back_populates="logs")

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
    sensor_logs = relationship("SubstationSensorLog", back_populates="substation")
    weather_logs = relationship("WeatherData", back_populates="substation")
    outage_predictions = relationship("OutagePrediction", back_populates="substation")

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

class SubstationSensorLog(Base):
    __tablename__ = "substation_sensor_logs"
    sensorLogID = Column(Integer, primary_key=True, index=True)
    subStationID = Column(Integer, ForeignKey("substations.subStationID"), nullable=False)
    timeStamp = Column(DateTime, default=datetime.utcnow)
    currentLoadMW = Column(Float, nullable=False)
    
    substation = relationship("Substation", back_populates="sensor_logs")

class WeatherData(Base):
    __tablename__ = "weather_data"
    weatherID = Column(Integer, primary_key=True, index=True)
    subStationID = Column(Integer, ForeignKey("substations.subStationID"), nullable=False)
    temperature = Column(Float, nullable=False)
    windSpeed = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    timeStamp = Column(DateTime, default=datetime.utcnow)

    substation = relationship("Substation", back_populates="weather_logs")

class OutagePrediction(Base):
    __tablename__ = "outage_predictions"
    predictionID = Column(Integer, primary_key=True, index=True)
    subStationID = Column(Integer, ForeignKey("substations.subStationID"), nullable=False)
    timeStamp = Column(DateTime, default=datetime.utcnow)
    failureProbScore = Column(Float, nullable=False)
    riskLevel = Column(String, nullable=False)

    substation = relationship("Substation", back_populates="outage_predictions")