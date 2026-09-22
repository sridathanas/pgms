from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
from datetime import datetime


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
    password: str

class UserAccount(UserAccountBase):
    userID: int
    model_config = ConfigDict(from_attributes=True)

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

class UsageLogBase(BaseModel):
    consumptionKWH: float

class UsageLogCreate(UsageLogBase):
    consumerID: int

class UsageLog(UsageLogBase):
    usageLogID: int
    consumerID: int
    timeStamp: datetime
    model_config = ConfigDict(from_attributes=True)

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

class SubstationSensorLogBase(BaseModel):
    currentLoadMW: float

class SubstationSensorLogCreate(SubstationSensorLogBase):
    subStationID: int

class SubstationSensorLog(SubstationSensorLogBase):
    sensorLogID: int
    subStationID: int
    timeStamp: datetime
    model_config = ConfigDict(from_attributes=True)

class WeatherDataBase(BaseModel):
    temperature: float
    windSpeed: float
    humidity: float

class WeatherDataCreate(WeatherDataBase):
    subStationID: int

class WeatherData(WeatherDataBase):
    weatherID: int
    subStationID: int
    timeStamp: datetime
    model_config = ConfigDict(from_attributes=True)

class OutagePredictionBase(BaseModel):
    failureProbScore: float
    riskLevel: str

class OutagePredictionCreate(OutagePredictionBase):
    subStationID: int

class OutagePrediction(OutagePredictionBase):
    predictionID: int
    subStationID: int
    timeStamp: datetime
    model_config = ConfigDict(from_attributes=True)