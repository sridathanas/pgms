from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
from datetime import datetime


# User Accounts
class UserAccountBase(BaseModel):
    username: str
    role: Literal["ADMIN", "OPERATOR", "TECHNICIAN"]
    isActive: bool = True
    approvalStatus: Literal["APPROVED", "PENDING", "REJECTED"] = "APPROVED"
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skillLevel: Optional[str] = None
    availabilityStatus: Optional[str] = None
    currentLocation: Optional[str] = None

class UserAccountCreate(UserAccountBase):
    password: str  # plain text in, hashed by crud.create_user before storage

class UserAccount(UserAccountBase):
    userID: int
    model_config = ConfigDict(from_attributes=True)

# Power Stations
class PowerStationBase(BaseModel):
    stationName: str
    location: str
    maxCapacityMW: float
    status: str

class PowerStationCreate(PowerStationBase):
    pass

class PowerStation(PowerStationBase):
    powerStationID: int
    model_config = ConfigDict(from_attributes=True)

# Substations
class SubstationBase(BaseModel):
    subStationName: str
    latitude: float
    longitude: float
    maxLoadCapacityMW: float
    stationStatus: str

class SubstationCreate(SubstationBase):
    powerStationID: int

class Substation(SubstationBase):
    subStationID: int
    powerStationID: int
    model_config = ConfigDict(from_attributes=True)

# Consumers
class ConsumerBase(BaseModel):
    name: str
    address: str
    contactNo: str
    connectionStatus: str

class ConsumerCreate(ConsumerBase):
    subStationID: int

class Consumer(ConsumerBase):
    consumerID: int
    subStationID: int
    model_config = ConfigDict(from_attributes=True)

# Usage Logs
class UsageLogBase(BaseModel):
    consumptionKWH: float

class UsageLogCreate(UsageLogBase):
    consumerID: int

class UsageLog(UsageLogBase):
    usageLogID: int
    consumerID: int
    timeStamp: datetime
    model_config = ConfigDict(from_attributes=True)

# Alerts
class AlertBase(BaseModel):
    alertType: str
    severity: str
    status: str

class AlertCreate(AlertBase):
    subStationID: Optional[int] = None
    consumerID: Optional[int] = None

class Alert(AlertBase):
    alertID: int
    subStationID: Optional[int]
    consumerID: Optional[int]
    timeStamp: datetime
    model_config = ConfigDict(from_attributes=True)

# Maintenance Tickets
class MaintenanceTicketBase(BaseModel):
    ticketStatus: str
    resolutionNotes: Optional[str] = None

class MaintenanceTicketCreate(MaintenanceTicketBase):
    alertID: int
    assignedTechnicianID: Optional[int] = None

class MaintenanceTicket(MaintenanceTicketBase):
    ticketID: int
    alertID: int
    assignedTechnicianID: Optional[int]
    createdDate: datetime
    model_config = ConfigDict(from_attributes=True)