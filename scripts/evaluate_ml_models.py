#!/usr/bin/env python3
"""
DIWAH Machine Learning Evaluation
=================================
Trains and evaluates regression models to predict exercise intensity (METs)
using the 5-second FLIRT features extracted from ActiGraph, Bangle.js, and EmotiBit.

This script separates the feature matrix dynamically by device, handles missing values,
scales features, and evaluates models (Multiple Linear Regression, Random Forest).
Outputs a formatted table of MAE, RMSE, and R-squared for direct use in the thesis.

Enhanced exports:
  - ml_metrics.json           — MAE/RMSE/R² per device and model
  - ml_predictions.csv        — True vs Predicted METs per sample (local backup)
  - INFLUXDB                  — Pushes time-series predictions to 'ml_predictions' measurement
  - ml_feature_importance.json — Top-20 RF feature importances per device
  - ml_intensity_breakdown.json — MAE/RMSE broken down by intensity zone
"""

import sys
import argparse
from pathlib import Path

# Data Manipulation
import pandas as pd
import numpy as np

# Scikit-learn
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import json

# InfluxDB
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS

# Project paths & config
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

DEFAULT_FEATURE_MATRIX = _SCRIPT_DIR / "Acc_pipe" / "data" / "processed" / "flirt_feature_matrix_ready.csv"
OUTPUT_DIR = _SCRIPT_DIR / "Acc_pipe" / "data" / "processed"


# ---------------------------------------------------------------------------
# MET-based intensity zones (standard clinical thresholds)
# ---------------------------------------------------------------------------
def classify_intensity(mets_value: float) -> str:
    """Classify a MET value into standard intensity zones."""
    if mets_value < 3.0:
        return "Light"
    elif mets_value < 6.0:
        return "Moderate"
    else:
        return "Vigorous"


def load_and_prep_data(csv_path: Path) -> pd.DataFrame:
    """Loads the FLIRT feature matrix and performs basic checks."""
    if not csv_path.exists():
        print(f"[ERROR] Feature matrix not found at {csv_path}")
        print("Please run scripts/extract_flirt_features.py --all-subjects first.")
        sys.exit(1)
        
    df = pd.read_csv(csv_path)
    
    if "mets" not in df.columns:
        print("[ERROR] Target variable 'mets' not found in the dataset.")
        sys.exit(1)
        
    if "datetime" not in df.columns or "subject_id" not in df.columns:
        print("[ERROR] Missing required metadata columns (datetime, subject_id).")
        sys.exit(1)
        
    # Drop rows where 'mets' (target variable) is NaN. 
    df = df.dropna(subset=["mets"])
    
    # Ensure datetime is parsed
    df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce', utc=True)
    df = df.dropna(subset=['datetime'])
    
    return df

def get_device_columns(df: pd.DataFrame, device: str) -> list:
    """
    Dynamically identifies columns belonging to a specific device.
    """
    return [col for col in df.columns if col.startswith(f"{device}_")]


def train_and_evaluate(X_train, X_test, y_train, y_test, feature_names=None):
    """
    Trains MLR and Random Forest, returning metrics, predictions,
    and feature importances from the Random Forest.
    """
    metrics = {}
    
    # 1. Regularized Linear Regression (Ridge, alpha=1.0)
    # Ridge prevents coefficient explosion when n_features ≈ n_samples
    mlr = Ridge(alpha=1.0)
    mlr.fit(X_train, y_train)
    mlr_preds = mlr.predict(X_test)
    
    metrics["MLR"] = {
        "MAE": mean_absolute_error(y_test, mlr_preds),
        "RMSE": np.sqrt(mean_squared_error(y_test, mlr_preds)),
        "R2": r2_score(y_test, mlr_preds)
    }
    
    # 2. Random Forest Regressor (Non-linear complex patterns)
    rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)
    rf_preds = rf.predict(X_test)
    
    metrics["RF"] = {
        "MAE": mean_absolute_error(y_test, rf_preds),
        "RMSE": np.sqrt(mean_squared_error(y_test, rf_preds)),
        "R2": r2_score(y_test, rf_preds)
    }
    
    # 3. Extract feature importances from Random Forest
    importance_data = []
    if feature_names is not None:
        importances = rf.feature_importances_
        for name, imp in zip(feature_names, importances):
            importance_data.append({"feature": name, "importance": float(imp)})
        # Sort by importance descending
        importance_data.sort(key=lambda x: x["importance"], reverse=True)
    
    # Return metrics, predictions payload, and feature importances
    preds_payload = {
        "Multiple Linear Regression": mlr_preds.tolist(),
        "Random Forest": rf_preds.tolist()
    }
    
    return metrics, preds_payload, importance_data


def compute_intensity_breakdown(y_test, preds_dict):
    """
    Compute MAE and RMSE broken down by intensity zone.
    """
    zones = [classify_intensity(m) for m in y_test]
    zone_labels = ["Light", "Moderate", "Vigorous"]
    
    breakdown = {}
    for model_name, preds in preds_dict.items():
        # Map back to short names for json
        short_name = "MLR" if model_name == "Multiple Linear Regression" else "RF"
        breakdown[short_name] = {}
        for zone in zone_labels:
            mask = [z == zone for z in zones]
            y_zone = y_test[mask]
            p_zone = np.array(preds)[mask]
            
            if len(y_zone) == 0:
                breakdown[short_name][zone] = {"MAE": None, "RMSE": None, "N": 0}
                continue
                
            breakdown[short_name][zone] = {
                "MAE": float(mean_absolute_error(y_zone, p_zone)),
                "RMSE": float(np.sqrt(mean_squared_error(y_zone, p_zone))),
                "N": int(len(y_zone))
            }
    
    return breakdown


def push_predictions_to_influx(pred_df: pd.DataFrame):
    """Push the time-series predictions to InfluxDB."""
    print("\nPushing predictions to InfluxDB...")
    
    if pred_df.empty:
        print("  No predictions to push.")
        return
        
    # Prepare dataframe for InfluxDB (needs timestamp index)
    df_influx = pred_df.copy()
    df_influx['timestamp'] = pd.to_datetime(df_influx['timestamp'], utc=True)
    df_influx = df_influx.set_index('timestamp')
    df_influx['subject'] = df_influx['subject'].astype(str)
    
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=120_000) as client:
            write_api = client.write_api(write_options=ASYNCHRONOUS)
            
            # The tags are subject, device, model
            # The fields are True_METs, Pred_METs
            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=df_influx,
                data_frame_measurement_name="ml_predictions",
                data_frame_tag_columns=["subject", "Device", "Model"],
                write_precision=WritePrecision.S,
            )
            write_api.close()
        print(f"  [SUCCESS] Successfully pushed {len(df_influx)} predictions to InfluxDB measurement 'ml_predictions'.")
    except Exception as e:
        print(f"  [ERROR] Failed to push to InfluxDB: {e}")


def print_beautiful_summary(results: dict):
    """Prints a clean, thesis-ready ASCII table comparing the results."""
    print("\n" + "="*80)
    print(" MACHINE LEARNING EVALUATION SUMMARY: ACTIVITY INTENSITY (METs) PREDICTION")
    print("="*80)
    print(f"{'Device Scenario':<15} | {'Model':<25} | {'MAE':<10} | {'RMSE':<10} | {'R-squared (R²)':<12}")
    print("-" * 80)
    
    devices = ["ActiGraph", "EmotiBit", "Bangle", "Fused"]
    
    for device in devices:
        res = results.get(device.lower())
        if not res:
            continue
            
        label = device
        if device == "Fused":
            label = "Sensor Fusion"
            
        print(f"{label:<15} | {'Multiple Linear Regression':<25} | "
              f"{res['MLR']['MAE']:<10.3f} | {res['MLR']['RMSE']:<10.3f} | {res['MLR']['R2']:<10.3f}")
        print(f"{'':<15} | {'Random Forest Regressor':<25} | "
              f"{res['RF']['MAE']:<10.3f} | {res['RF']['RMSE']:<10.3f} | {res['RF']['R2']:<10.3f}")
        print("-" * 80)
        
    print("="*80)
    print("Note: MAE (Mean Absolute Error) and RMSE (Root Mean Square Error) are in METs.")
    print("      R² closer to 1.0 indicates better explained variance.\n")


def main():
    parser = argparse.ArgumentParser(description="Evaluate ML models against METs ground truth.")
    parser.add_argument("--input", type=Path, default=DEFAULT_FEATURE_MATRIX,
                        help="Path to the FLIRT feature matrix CSV.")
    parser.add_argument("--no-influx", action="store_true", help="Skip pushing to InfluxDB")
    args = parser.parse_args()
    
    print(f"Loading data from {args.input}...")
    df = load_and_prep_data(args.input)
    y = df["mets"].values
    
    print(f"Total valid samples: {len(df)}")
    
    # ── Per-device evaluation ──────────────────────────────────────────────
    devices = ["actigraph", "emotibit", "bangle"]
    results = {}
    all_predictions = []
    all_feature_importances = {}
    all_intensity_breakdowns = {}
    all_device_features = {}  # Collect for fusion
    
    for device in devices:
        print(f"\nProcessing {device.capitalize()}...")
        
        # 1. Identify columns
        features = get_device_columns(df, device)
        if not features:
            print(f"  [WARNING] No features found for {device}. Skipping.")
            continue
            
        print(f"  Found {len(features)} {device} features.")
        X = df[features]
        
        X = X.replace([np.inf, -np.inf], np.nan)
        all_device_features[device] = X
        
        imputer = SimpleImputer(strategy='median')
        X_imputed = imputer.fit_transform(X)
        
        indices = np.arange(len(y))
        
        X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
            X_imputed, y, indices, test_size=0.20, random_state=42
        )
        print(f"  Training set: {X_train.shape[0]} windows. Testing set: {X_test.shape[0]} windows.")
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        print("  Training MLR and Random Forest models...")
        metrics, preds_payload, importance_data = train_and_evaluate(
            X_train_scaled, X_test_scaled, y_train, y_test, feature_names=features
        )
        
        results[device] = metrics
        all_feature_importances[device] = importance_data[:20]
        
        # Intensity breakdown
        intensity_bd = compute_intensity_breakdown(y_test, preds_payload)
        all_intensity_breakdowns[device] = intensity_bd
        
        # Accumulate time-series predictions
        test_timestamps = df['datetime'].iloc[idx_test].values
        test_subjects = df['subject_id'].iloc[idx_test].values
        
        dev_label = "Bangle.js" if device == "bangle" else ("ActiGraph" if device == "actigraph" else "EmotiBit")
        
        for model_name, preds_arr in preds_payload.items():
            for t_idx, (t_val, p_val) in enumerate(zip(y_test, preds_arr)):
                all_predictions.append({
                    "timestamp": test_timestamps[t_idx],
                    "subject": test_subjects[t_idx],
                    "Device": dev_label,
                    "Model": model_name,
                    "True_METs": t_val,
                    "Pred_METs": p_val
                })
        
    # ── Sensor Fusion model (all devices combined) ─────────────────────────
    if len(all_device_features) == 3:
        print(f"\nProcessing Sensor Fusion (all devices combined)...")
        
        X_fused = pd.concat(list(all_device_features.values()), axis=1)
        fused_features = list(X_fused.columns)
        X_fused = X_fused.replace([np.inf, -np.inf], np.nan)
        
        print(f"  Combined {len(fused_features)} features from all devices.")
        
        imputer = SimpleImputer(strategy='median')
        X_fused_imputed = imputer.fit_transform(X_fused)
        
        indices = np.arange(len(y))
        X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
            X_fused_imputed, y, indices, test_size=0.20, random_state=42
        )
        print(f"  Training set: {X_train.shape[0]} windows. Testing set: {X_test.shape[0]} windows.")
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        print("  Training MLR and Random Forest models...")
        metrics, preds_payload, importance_data = train_and_evaluate(
            X_train_scaled, X_test_scaled, y_train, y_test, feature_names=fused_features
        )
        
        results["fused"] = metrics
        all_feature_importances["fused"] = importance_data[:20]
        
        intensity_bd = compute_intensity_breakdown(y_test, preds_payload)
        all_intensity_breakdowns["fused"] = intensity_bd
        
        test_timestamps = df['datetime'].iloc[idx_test].values
        test_subjects = df['subject_id'].iloc[idx_test].values
        
        for model_name, preds_arr in preds_payload.items():
            for t_idx, (t_val, p_val) in enumerate(zip(y_test, preds_arr)):
                all_predictions.append({
                    "timestamp": test_timestamps[t_idx],
                    "subject": test_subjects[t_idx],
                    "Device": "Sensor Fusion",
                    "Model": model_name,
                    "True_METs": t_val,
                    "Pred_METs": p_val
                })
    
    # ── Output ─────────────────────────────────────────────────────────────
    print_beautiful_summary(results)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Core metrics
    with open(OUTPUT_DIR / "ml_metrics.json", "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Predictions CSV (Local Backup)
    pred_df = pd.DataFrame(all_predictions)
    pred_df.to_csv(OUTPUT_DIR / "ml_predictions.csv", index=False)
    
    # 3. Feature importances
    with open(OUTPUT_DIR / "ml_feature_importance.json", "w") as f:
        json.dump(all_feature_importances, f, indent=4)
    
    # 4. Intensity breakdown
    with open(OUTPUT_DIR / "ml_intensity_breakdown.json", "w") as f:
        json.dump(all_intensity_breakdowns, f, indent=4)
    
    print(f"\n[SUCCESS] Exported metrics to {OUTPUT_DIR}\\ml_metrics.json")
    print(f"[SUCCESS] Exported local predictions backup to {OUTPUT_DIR}\\ml_predictions.csv")
    print(f"[SUCCESS] Exported feature importances to {OUTPUT_DIR}\\ml_feature_importance.json")
    print(f"[SUCCESS] Exported intensity breakdown to {OUTPUT_DIR}\\ml_intensity_breakdown.json")

    # 5. Push to InfluxDB
    if not args.no_influx:
        push_predictions_to_influx(pred_df)


if __name__ == "__main__":
    main()
