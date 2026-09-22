import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models

# Load the serialized Random Forest once, so the scheduled loop does no repeated disk I/O.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "outage_model.joblib")

# Thresholds from the UML activity diagram / SRS (F9)
ALERT_THRESHOLD = 0.80
MEDIUM_RISK_THRESHOLD = 0.50
# Short interval so the demo shows live scoring. Raise it (e.g. 15 * 60) for real use.
PREDICTION_INTERVAL_SECONDS = 10

# An existing alert in one of these states means the substation is already being handled,
# so the cycle must not raise a duplicate for it every 15 minutes.
UNRESOLVED_ALERT_STATUSES = ("OPEN", "VERIFIED_HIGH_SEVERITY", "IN_PROGRESS")

try:
    predictive_model = joblib.load(MODEL_PATH)
except (FileNotFoundError, OSError):
    predictive_model = None
    print(f"WARNING: {MODEL_PATH} not found. Run `python train_model.py` to enable AI predictions.")

_scheduler = None  # module-level so the background thread isn't garbage collected


def interval_label() -> str:
    """How often predictions run, worded for the dashboard."""
    seconds = PREDICTION_INTERVAL_SECONDS
    if seconds < 60:
        return f"{seconds} seconds"
    minutes = seconds // 60
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def risk_level_for(score: float) -> str:
    if score >= ALERT_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_RISK_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def run_prediction_cycle() -> dict:
    """AI Outage Risk Detection (Activity Diagram 4).

    Simulates substation telemetry, stores it with the matching weather reading, scores the
    failure probability, and raises an alert when the score crosses the 0.80 threshold.
    Returns a small summary so the dashboard can report what happened.
    """
    if predictive_model is None:
        return {"ok": False, "reason": "model_missing", "scored": 0, "alerts": 0}

    db: Session = SessionLocal()
    try:
        substations = db.query(models.Substation).all()
        alerts_created = 0

        for sub in substations:
            # 1. Hardware simulation: the SRS assumes simulated sensor data for this version
            temp = float(np.random.uniform(20.0, 45.0))
            wind = float(np.random.uniform(5.0, 95.0))
            humidity = float(np.random.uniform(40.0, 95.0))
            load_percentage = float(np.random.uniform(0.60, 0.98))
            current_load_mw = (sub.maxLoadCapacityMW or 0.0) * load_percentage

            # 2. Record the raw telemetry
            db.add(models.SubstationSensorLog(
                subStationID=sub.subStationID,
                currentLoadMW=current_load_mw,
                timeStamp=datetime.utcnow(),
            ))
            db.add(models.WeatherData(
                subStationID=sub.subStationID,
                temperature=temp,
                windSpeed=wind,
                humidity=humidity,
                timeStamp=datetime.utcnow(),
            ))

            # 3. Inference. Column names and order must match train_model.py.
            feature_vector = pd.DataFrame([{
                "temperature": temp,
                "wind_speed": wind,
                "humidity": humidity,
                "load_percentage": load_percentage,
            }])
            # predict_proba returns (n_samples, n_classes); [0][1] is the failure probability
            probability_score = float(predictive_model.predict_proba(feature_vector)[0][1])

            # 4. Store the prediction
            db.add(models.OutagePrediction(
                subStationID=sub.subStationID,
                failureProbScore=probability_score,
                riskLevel=risk_level_for(probability_score),
                timeStamp=datetime.utcnow(),
            ))

            # 5. Raise an alert, unless this substation already has one waiting to be handled
            if probability_score >= ALERT_THRESHOLD:
                already_open = db.query(models.Alert.alertID).filter(
                    models.Alert.subStationID == sub.subStationID,
                    models.Alert.alertType == "OverloadRisk",
                    models.Alert.status.in_(UNRESOLVED_ALERT_STATUSES),
                ).first()
                if already_open is None:
                    db.add(models.Alert(
                        subStationID=sub.subStationID,
                        alertType="OverloadRisk",
                        severity="HIGH",
                        status="OPEN",
                        timeStamp=datetime.utcnow(),
                    ))
                    db.add(models.SystemLog(
                        actionType="AI_ALERT_TRIGGERED",
                        description=(f"AI module predicted {probability_score:.2f} failure risk for "
                                     f"substation {sub.subStationID}. Alert generated."),
                        timeStamp=datetime.utcnow(),
                    ))
                    alerts_created += 1

        db.commit()
        return {"ok": True, "scored": len(substations), "alerts": alerts_created}

    except Exception as e:
        db.rollback()
        print(f"Prediction cycle failed: {e}")
        return {"ok": False, "reason": str(e), "scored": 0, "alerts": 0}
    finally:
        db.close()


def start_scheduler():
    """Start the background prediction loop. Safe to call once at application startup."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_prediction_cycle,
        "interval",
        seconds=PREDICTION_INTERVAL_SECONDS,
        id="outage_prediction_cycle",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler():
    """Stop the loop so the process (and uvicorn's auto-reload) can exit cleanly."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
