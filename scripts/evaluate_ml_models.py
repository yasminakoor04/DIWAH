#!/usr/bin/env python3
"""
DIWAH — Machine Learning Evaluation Script (Redesigned)
========================================================
Evaluates three prediction scenarios for METs prediction:

  1. REFERENCE   — ActiGraph accelerometer + Polar HR stat features
                   (clinical upper bound — "best possible prediction")
  2. EMOTIBIT    — EmotiBit accelerometer features only
                   (open-source wearable test 1)
  3. BANGLE.JS   — Bangle.js accelerometer features only
                   (open-source wearable test 2)

Target variable: METs from Vyntus indirect calorimetry (ground truth).

Outputs a formatted table of MAE, RMSE, and R-squared for direct use in the thesis.

Enhanced exports:
  - ml_metrics.json           — MAE/RMSE/R² per scenario and model
  - ml_predictions.csv        — True vs Predicted METs per sample (local backup)
  - INFLUXDB                  — Pushes time-series predictions to 'ml_predictions' measurement
  - ml_feature_importance.json — Top-20 RF feature importances per scenario
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
        print("Please run scripts/extract_flirt_features.py first.")
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


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------
# Each scenario defines WHICH columns from the feature matrix are used as
# input features. The target is always 'mets' (Vyntus ground truth).
#
# Reference = ActiGraph accel + ActiGraph VM stats + Polar HR stats
# EmotiBit  = EmotiBit accel + EmotiBit VM stats
# Bangle.js = Bangle.js accel + Bangle.js VM stats
# ---------------------------------------------------------------------------

SCENARIOS = {
    "reference": {
        "label": "Reference (ActiGraph + Polar HR)",
        "prefixes": ["actigraph_", "hr_polar_stat_"],
        "description": "Clinical upper bound: research-grade accelerometer + chest-strap heart rate",
    },
    "emotibit": {
        "label": "EmotiBit (Open-Source)",
        "prefixes": ["emotibit_"],
        "description": "Open-source biometric sensor array (accelerometer only)",
    },
    "bangle": {
        "label": "Bangle.js (Open-Source)",
        "prefixes": ["bangle_"],
        "description": "Open-source programmable smartwatch (accelerometer only)",
    },
}


def get_scenario_columns(df: pd.DataFrame, prefixes: list) -> list:
    """Dynamically identifies columns belonging to a scenario by prefix match."""
    cols = []
    for prefix in prefixes:
        cols.extend([col for col in df.columns if col.startswith(prefix)])
    return cols


def train_and_evaluate(X_train, X_test, y_train, y_test, feature_names=None):
    """
    Trains Ridge Regression and Random Forest, returning metrics, predictions,
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
    print(f"{'Scenario':<35} | {'Model':<25} | {'MAE':<10} | {'RMSE':<10} | {'R²':<10}")
    print("-" * 80)
    
    scenario_order = ["reference", "emotibit", "bangle"]
    
    for scenario_key in scenario_order:
        res = results.get(scenario_key)
        if not res:
            continue
            
        label = SCENARIOS[scenario_key]["label"]
            
        print(f"{label:<35} | {'Ridge Linear Regression':<25} | "
              f"{res['MLR']['MAE']:<10.3f} | {res['MLR']['RMSE']:<10.3f} | {res['MLR']['R2']:<10.3f}")
        print(f"{'':<35} | {'Random Forest Regressor':<25} | "
              f"{res['RF']['MAE']:<10.3f} | {res['RF']['RMSE']:<10.3f} | {res['RF']['R2']:<10.3f}")
        print("-" * 80)
        
    print("="*80)
    print("Note: MAE (Mean Absolute Error) and RMSE (Root Mean Square Error) are in METs.")
    print("      R² closer to 1.0 indicates better explained variance.")
    print("      Reference scenario includes Polar HR features (clinical upper bound).")
    print("      Open-source devices use accelerometer features only.\n")


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
    
    # ── Per-scenario evaluation ────────────────────────────────────────────
    results = {}
    all_predictions = []
    all_feature_importances = {}
    all_intensity_breakdowns = {}
    
    for scenario_key, scenario_cfg in SCENARIOS.items():
        label = scenario_cfg["label"]
        prefixes = scenario_cfg["prefixes"]
        desc = scenario_cfg["description"]
        
        print(f"\n{'='*60}")
        print(f"Scenario: {label}")
        print(f"  {desc}")
        print(f"{'='*60}")
        
        # 1. Identify feature columns for this scenario
        features = get_scenario_columns(df, prefixes)
        if not features:
            print(f"  [WARNING] No features found for {scenario_key}. Skipping.")
            continue
            
        print(f"  Found {len(features)} features.")
        X = df[features]
        
        X = X.replace([np.inf, -np.inf], np.nan)
        
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
        
        print("  Training Ridge Regression and Random Forest models...")
        metrics, preds_payload, importance_data = train_and_evaluate(
            X_train_scaled, X_test_scaled, y_train, y_test, feature_names=features
        )
        
        results[scenario_key] = metrics
        all_feature_importances[scenario_key] = importance_data[:20]
        
        # Intensity breakdown
        intensity_bd = compute_intensity_breakdown(y_test, preds_payload)
        all_intensity_breakdowns[scenario_key] = intensity_bd
        
        # Accumulate time-series predictions
        test_timestamps = df['datetime'].iloc[idx_test].values
        test_subjects = df['subject_id'].iloc[idx_test].values
        
        for model_name, preds_arr in preds_payload.items():
            for t_idx, (t_val, p_val) in enumerate(zip(y_test, preds_arr)):
                all_predictions.append({
                    "timestamp": test_timestamps[t_idx],
                    "subject": test_subjects[t_idx],
                    "Device": label,
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
    
    print(f"\n[SUCCESS] Exported metrics to {OUTPUT_DIR / 'ml_metrics.json'}")
    print(f"[SUCCESS] Exported local predictions backup to {OUTPUT_DIR / 'ml_predictions.csv'}")
    print(f"[SUCCESS] Exported feature importances to {OUTPUT_DIR / 'ml_feature_importance.json'}")
    print(f"[SUCCESS] Exported intensity breakdown to {OUTPUT_DIR / 'ml_intensity_breakdown.json'}")

    # 5. Push to InfluxDB
    if not args.no_influx:
        push_predictions_to_influx(pred_df)


if __name__ == "__main__":
    main()
