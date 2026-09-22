import numpy as np
import pandas as pd
from   sklearn.ensemble import RandomForestClassifier
import joblib
import os


def generate_and_train():
    np.random.seed(42)
    n_samples = 5000

    temperature = np.random.uniform(10, 48, n_samples)
    wind_speed = np.random.uniform(0, 120, n_samples)
    humidity = np.random.uniform(20, 100, n_samples)
    load_percentage = np.random.uniform(0.3, 1.0, n_samples)

    failure = np.zeros(n_samples, dtype=int)
    
    for i in range(n_samples):
        risk_score = 0.0

        if load_percentage[i] > 0.92:
            risk_score += 0.50
            
        if temperature[i] > 38.0:
            risk_score += 0.30
            
        if wind_speed[i] > 80.0:
            risk_score += 0.20
            
        if humidity[i] > 90.0:
            risk_score += 0.10
            
        if risk_score + np.random.uniform(-0.1, 0.2) >= 0.75:
            failure[i] = 1

    df = pd.DataFrame({
        'temperature': temperature,
        'wind_speed': wind_speed,
        'humidity': humidity,
        'load_percentage': load_percentage,

        'failure': failure
    })

    X = df[['temperature', 'wind_speed', 'humidity', 'load_percentage']]
    y = df['failure']

    model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
    model.fit(X, y)

    export_path = os.path.join(os.path.dirname(__file__), 'outage_model.joblib')
    joblib.dump(model, export_path)

if __name__ == "__main__":
    generate_and_train()