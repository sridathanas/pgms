"""Fill the database with realistic demo data for every table.

Run from the project root:
    python -m app.seed_demo            # add demo data (refuses if grid data already exists)
    python -m app.seed_demo --add      # add it alongside whatever is already there
    python -m app.seed_demo --reset    # wipe grid data first, then add it again

User accounts are created by app.seed and are never deleted by --reset.
"""
import random
import sys
from datetime import datetime, timedelta

from app import crud, models, schemas, seed
from app.database import SessionLocal, engine

random.seed(7)

# Extra staff so the operator has someone to dispatch
EXTRA_USERS = [
    schemas.UserAccountCreate(
        username="meera.nair", password="Operator@123", role=models.Role.OPERATOR,
        name="Meera Nair", email="meera.nair@pgms.local", phone="9447010234",
    ),
    schemas.UserAccountCreate(
        username="anand.pillai", password="Tech@123", role=models.Role.TECHNICIAN,
        name="Anand Pillai", email="anand.pillai@pgms.local", phone="9447010235",
        skillLevel="SENIOR", availabilityStatus="AVAILABLE", currentLocation="Kottayam",
    ),
    schemas.UserAccountCreate(
        username="rahul.das", password="Tech@123", role=models.Role.TECHNICIAN,
        name="Rahul Das", email="rahul.das@pgms.local", phone="9447010236",
        skillLevel="JUNIOR", availabilityStatus="BUSY", currentLocation="Pala",
    ),
]

POWER_STATIONS = [
    # name, location, max capacity MW, status
    ("Idukki Hydroelectric Station", "Idukki", 780.0, "ACTIVE"),
    ("Sabarigiri Hydel Station", "Pathanamthitta", 340.0, "ACTIVE"),
    ("Kayamkulam Thermal Plant", "Alappuzha", 360.0, "MAINTENANCE"),
]

# name, parent station index, latitude, longitude, max load MW, status
SUBSTATIONS = [
    ("Kottayam Main 220kV", 0, 9.5916, 76.5222, 95.0, "ACTIVE"),
    ("Pala 110kV", 0, 9.7131, 76.6836, 60.0, "ACTIVE"),
    ("Ettumanoor 110kV", 0, 9.6700, 76.5560, 45.0, "ACTIVE"),
    ("Changanassery 66kV", 1, 9.4430, 76.5370, 38.0, "ACTIVE"),
    ("Vaikom 66kV", 1, 9.7480, 76.3960, 32.0, "ACTIVE"),
    ("Erattupetta 66kV", 2, 9.6870, 76.7780, 28.0, "MAINTENANCE"),
]

# name, substation index, address, contact, status, average daily kWh
CONSUMERS = [
    ("Rajesh Menon", 0, "24 TB Road, Kottayam", "9447110001", "ACTIVE", 14.0),
    ("Lakshmi Varma", 0, "8 Thirunakkara, Kottayam", "9447110002", "ACTIVE", 9.5),
    ("St. Mary's Hospital", 0, "MC Road, Kottayam", "9447110003", "ACTIVE", 180.0),
    ("Joseph Thomas", 1, "12 Church Street, Pala", "9447110004", "ACTIVE", 11.0),
    ("Pala Rubber Works", 1, "Industrial Estate, Pala", "9447110005", "ACTIVE", 240.0),
    ("Anita George", 2, "5 Market Road, Ettumanoor", "9447110006", "ACTIVE", 8.0),
    ("Suresh Kumar", 2, "31 Temple Lane, Ettumanoor", "9447110007", "ACTIVE", 12.5),
    ("Fathima Beevi", 3, "17 Bazaar Road, Changanassery", "9447110008", "ACTIVE", 10.0),
    ("Vaikom Rice Mill", 4, "Backwater Road, Vaikom", "9447110009", "ACTIVE", 160.0),
    ("Philip Mathew", 5, "3 Hill View, Erattupetta", "9447110010", "DISCONNECTED", 7.0),
]

USAGE_DAYS = 30
TELEMETRY_CYCLES = 12  # hourly history per substation

# Latest risk picture: index -> (failure probability, risk level)
LATEST_RISK = {
    0: (0.86, "HIGH"),
    1: (0.58, "MEDIUM"),
    2: (0.21, "LOW"),
    3: (0.12, "LOW"),
    4: (0.34, "LOW"),
    5: (0.07, "LOW"),
}

GRID_TABLES = [models.MaintenanceTicket, models.Alert, models.OutagePrediction,
               models.WeatherData, models.SubstationSensorLog, models.UsageLog,
               models.Consumer, models.Substation, models.PowerStation]


def reset_grid_data(db):
    for model in GRID_TABLES:
        db.query(model).delete()
    db.query(models.SystemLog).filter(
        models.SystemLog.actionType.in_(("AI_ALERT_TRIGGERED", "AI_PREDICTION_RUN", "DEMO_SEED"))
    ).delete(synchronize_session=False)
    db.commit()
    print("removed existing grid data")


def create_users(db):
    for user in EXTRA_USERS:
        if crud.get_user_by_username(db, user.username):
            print(f"skipped  {user.username} (already exists)")
            continue
        crud.create_user(db, user)
        print(f"created  {user.username:<14} role={user.role:<11} password={user.password}")


def create_infrastructure(db):
    stations = []
    for name, location, capacity, status in POWER_STATIONS:
        stations.append(crud.create_power_station(db, schemas.PowerStationCreate(
            stationName=name, location=location, maxCapacityMW=capacity, status=status)))

    substations = []
    for name, parent, lat, lon, load, status in SUBSTATIONS:
        substations.append(crud.create_substation(db, schemas.SubstationCreate(
            subStationName=name, powerStationID=stations[parent].powerStationID,
            latitude=lat, longitude=lon, maxLoadCapacityMW=load, stationStatus=status)))
    return stations, substations


def create_consumers_and_usage(db, substations):
    now = datetime.utcnow()
    consumers = []
    for i, (name, sub_index, address, contact, status, daily_kwh) in enumerate(CONSUMERS):
        consumer = crud.create_consumer(db, schemas.ConsumerCreate(
            name=name, address=address, contactNo=contact, connectionStatus=status,
            subStationID=substations[sub_index].subStationID))
        consumers.append(consumer)

        for day in range(USAGE_DAYS, 0, -1):
            reading = daily_kwh * random.uniform(0.85, 1.15)
            # Consumer 4 drops to almost nothing for the last week while still connected:
            # the pattern the theft detection module will look for later.
            if i == 4 and day <= 7:
                reading = daily_kwh * random.uniform(0.02, 0.06)
            # A disconnected consumer records nothing
            if status == "DISCONNECTED" and day <= 10:
                reading = 0.0
            db.add(models.UsageLog(
                consumerID=consumer.consumerID,
                timeStamp=now - timedelta(days=day),
                consumptionKWH=round(reading, 2),
            ))
    db.commit()
    return consumers


def create_telemetry_history(db, substations):
    """Hourly sensor, weather and prediction rows so the dashboard has history on first load."""
    now = datetime.utcnow()
    for index, sub in enumerate(substations):
        final_score, final_level = LATEST_RISK[index]
        for cycle in range(TELEMETRY_CYCLES, 0, -1):
            stamp = now - timedelta(hours=cycle)
            is_latest = cycle == 1

            if is_latest:
                score, level = final_score, final_level
                load_fraction = 0.60 + 0.35 * score
                temperature = 28.0 + 14.0 * score
                wind = 20.0 + 60.0 * score
                humidity = 65.0 + 25.0 * score
            else:
                score = round(min(0.95, max(0.03, final_score * random.uniform(0.4, 1.1))), 2)
                level = "HIGH" if score >= 0.80 else "MEDIUM" if score >= 0.50 else "LOW"
                load_fraction = random.uniform(0.55, 0.92)
                temperature = random.uniform(24.0, 39.0)
                wind = random.uniform(8.0, 70.0)
                humidity = random.uniform(55.0, 92.0)

            db.add(models.SubstationSensorLog(
                subStationID=sub.subStationID, timeStamp=stamp,
                currentLoadMW=round(sub.maxLoadCapacityMW * load_fraction, 2)))
            db.add(models.WeatherData(
                subStationID=sub.subStationID, timeStamp=stamp,
                temperature=round(temperature, 1), windSpeed=round(wind, 1),
                humidity=round(humidity, 1)))
            db.add(models.OutagePrediction(
                subStationID=sub.subStationID, timeStamp=stamp,
                failureProbScore=score, riskLevel=level))
    db.commit()


def create_alerts_and_tickets(db, substations, consumers):
    now = datetime.utcnow()
    technicians = db.query(models.UserAccount).filter(
        models.UserAccount.role == models.Role.TECHNICIAN).order_by(models.UserAccount.userID).all()

    overload_open = models.Alert(
        subStationID=substations[0].subStationID, alertType="OverloadRisk", severity="HIGH",
        status="OPEN", timeStamp=now - timedelta(minutes=12))
    overload_verified = models.Alert(
        subStationID=substations[1].subStationID, alertType="OverloadRisk", severity="MEDIUM",
        status="VERIFIED_HIGH_SEVERITY", timeStamp=now - timedelta(hours=5))
    theft_alert = models.Alert(
        consumerID=consumers[4].consumerID, alertType="TheftSuspected", severity="HIGH",
        status="OPEN", timeStamp=now - timedelta(hours=2))
    weather_alert = models.Alert(
        subStationID=substations[4].subStationID, alertType="WeatherRisk", severity="LOW",
        status="DISMISSED", timeStamp=now - timedelta(days=1))
    db.add_all([overload_open, overload_verified, theft_alert, weather_alert])
    db.commit()

    tickets = [
        models.MaintenanceTicket(
            alertID=overload_verified.alertID,
            assignedTechnicianID=technicians[0].userID if technicians else None,
            createdDate=now - timedelta(hours=4), ticketStatus="IN_PROGRESS",
            resolutionNotes="Inspect transformer cooling fans at Pala 110kV."),
        models.MaintenanceTicket(
            alertID=theft_alert.alertID,
            assignedTechnicianID=technicians[-1].userID if technicians else None,
            createdDate=now - timedelta(hours=1), ticketStatus="ASSIGNED",
            resolutionNotes="Verify meter seal at Pala Rubber Works."),
        models.MaintenanceTicket(
            alertID=weather_alert.alertID,
            assignedTechnicianID=technicians[0].userID if technicians else None,
            createdDate=now - timedelta(days=1), ticketStatus="RESOLVED",
            resolutionNotes="Cleared fallen branch from the 66kV feeder. Line restored."),
    ]
    db.add_all(tickets)

    db.add_all([
        models.SystemLog(actionType="AI_ALERT_TRIGGERED", timeStamp=now - timedelta(minutes=12),
                         description=("AI module predicted 0.86 failure risk for substation "
                                      f"{substations[0].subStationID}. Alert generated.")),
        models.SystemLog(actionType="DEMO_SEED", timeStamp=now,
                         description="Demo grid data loaded by app.seed_demo"),
    ])
    db.commit()


def main():
    reset = "--reset" in sys.argv
    models.Base.metadata.create_all(bind=engine)
    seed.main()  # the three basic accounts

    db = SessionLocal()
    try:
        if reset:
            reset_grid_data(db)
        elif db.query(models.PowerStation).first() is not None and "--add" not in sys.argv:
            print("\nGrid data already exists. Re-run with --add to keep it, or --reset to replace it.")
            return

        create_users(db)
        stations, substations = create_infrastructure(db)
        consumers = create_consumers_and_usage(db, substations)
        create_telemetry_history(db, substations)
        create_alerts_and_tickets(db, substations, consumers)

        print(f"\nadded {len(stations)} power stations, {len(substations)} substations, "
              f"{len(consumers)} consumers")
        print(f"      {db.query(models.UsageLog).count()} usage logs, "
              f"{db.query(models.OutagePrediction).count()} predictions, "
              f"{db.query(models.Alert).count()} alerts, "
              f"{db.query(models.MaintenanceTicket).count()} tickets")
    finally:
        db.close()


if __name__ == "__main__":
    main()
