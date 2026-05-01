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
  - ml_predictions.csv        — True vs Predicted METs per sample
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
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import json

# Paths
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
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
        
    # Drop rows where 'mets' (target variable) is NaN. 
    # (The FLIRT script does this, but good to be safe)
    df = df.dropna(subset=["mets"])
    
    return df

def get_device_columns(df: pd.DataFrame, device: str) -> list:
    """
    Dynamically identifies columns belonging to a specific device.
    Matches the naming conventions from the FLIRT extraction pipeline:
    e.g., 'actigraph_acc_x_mean', 'bangle_vm_stat_mean', etc.
    """
    return [col for col in df.columns if col.startswith(f"{device}_")]


def train_and_evaluate(X_train, X_test, y_train, y_test, feature_names=None):
    """
    Trains MLR and Random Forest, returning metrics, predictions,
    and feature importances from the Random Forest.
    """
    metrics = {}
    
    # 1. Multiple Linear Regression (Baseline)
    mlr = LinearRegression()
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
        "MLR": mlr_preds.tolist(),
        "RF": rf_preds.tolist()
    }
    
    return metrics, preds_payload, importance_data


def compute_intensity_breakdown(y_test, preds_dict):
    """
    Compute MAE and RMSE broken down by intensity zone.
    
    Args:
        y_test: array of true MET values
        preds_dict: dict with model_name -> predictions array
    
    Returns:
        dict of {model_name: {zone: {MAE, RMSE, N}}}
    """
    zones = [classify_intensity(m) for m in y_test]
    zone_labels = ["Light", "Moderate", "Vigorous"]
    
    breakdown = {}
    for model_name, preds in preds_dict.items():
        breakdown[model_name] = {}
        for zone in zone_labels:
            mask = [z == zone for z in zones]
            y_zone = y_test[mask]
            p_zone = np.array(preds)[mask]
            
            if len(y_zone) == 0:
                breakdown[model_name][zone] = {"MAE": None, "RMSE": None, "N": 0}
                continue
                
            breakdown[model_name][zone] = {
                "MAE": float(mean_absolute_error(y_zone, p_zone)),
                "RMSE": float(np.sqrt(mean_squared_error(y_zone, p_zone))),
                "N": int(len(y_zone))
            }
    
    return breakdown


def print_beautiful_summary(results: dict):
    """
    Prints a clean, thesis-ready ASCII table comparing the results.
    """
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
        
        # Replace Any Infinities with NaNs so the Imputer can handle them.
        X = X.replace([np.inf, -np.inf], np.nan)
        
        # Store for fusion later
        all_device_features[device] = X
        
        # 2. Impute NaNs
        imputer = SimpleImputer(strategy='median')
        X_imputed = imputer.fit_transform(X)
        
        # 3. Train/Test Split (80/20)
        # Using a fixed random state for reproducible thesis results.
        X_train, X_test, y_train, y_test = train_test_split(
            X_imputed, y, test_size=0.20, random_state=42
        )
        print(f"  Training set: {X_train.shape[0]} windows. Testing set: {X_test.shape[0]} windows.")
        
        # 4. Scale features (Fit on train, transform test to prevent data leakage)
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # 5. Train & Evaluate
        print("  Training MLR and Random Forest models...")
        metrics, preds_payload, importance_data = train_and_evaluate(
            X_train_scaled, X_test_scaled, y_train, y_test, feature_names=features
        )
        
        results[device] = metrics
        
        # Store feature importances (top 20)
        all_feature_importances[device] = importance_data[:20]
        
        # Compute intensity breakdown
        intensity_bd = compute_intensity_breakdown(
            y_test,
            {"MLR": preds_payload["MLR"], "RF": preds_payload["RF"]}
        )
        all_intensity_breakdowns[device] = intensity_bd
        
        # Accumulate predictions for Dashboard Interactive Scatter Plot
        for model_name, preds_arr in preds_payload.items():
            model_label = "Multiple Linear Regression" if model_name == "MLR" else "Random Forest"
            dev_label = "Bangle.js" if device == "bangle" else ("ActiGraph" if device == "actigraph" else "EmotiBit")
            for t_val, p_val in zip(y_test, preds_arr):
                all_predictions.append({
                    "Device": dev_label,
                    "Model": model_label,
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
        
        X_train, X_test, y_train, y_test = train_test_split(
            X_fused_imputed, y, test_size=0.20, random_state=42
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
        
        # Intensity breakdown for fused
        intensity_bd = compute_intensity_breakdown(
            y_test,
            {"MLR": preds_payload["MLR"], "RF": preds_payload["RF"]}
        )
        all_intensity_breakdowns["fused"] = intensity_bd
        
        # Add predictions
        for model_name, preds_arr in preds_payload.items():
            model_label = "Multiple Linear Regression" if model_name == "MLR" else "Random Forest"
            for t_val, p_val in zip(y_test, preds_arr):
                all_predictions.append({
                    "Device": "Sensor Fusion",
                    "Model": model_label,
                    "True_METs": t_val,
                    "Pred_METs": p_val
                })
    
    # ── Output ─────────────────────────────────────────────────────────────
    print_beautiful_summary(results)
    
    # Save all payloads for the Dashboard UI
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Core metrics
    with open(OUTPUT_DIR / "ml_metrics.json", "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Predictions CSV
    pd.DataFrame(all_predictions).to_csv(OUTPUT_DIR / "ml_predictions.csv", index=False)
    
    # 3. Feature importances
    with open(OUTPUT_DIR / "ml_feature_importance.json", "w") as f:
        json.dump(all_feature_importances, f, indent=4)
    
    # 4. Intensity breakdown
    with open(OUTPUT_DIR / "ml_intensity_breakdown.json", "w") as f:
        json.dump(all_intensity_breakdowns, f, indent=4)
    
    print(f"\n[SUCCESS] Exported metrics to {OUTPUT_DIR}\\ml_metrics.json")
    print(f"[SUCCESS] Exported predictions to {OUTPUT_DIR}\\ml_predictions.csv")
    print(f"[SUCCESS] Exported feature importances to {OUTPUT_DIR}\\ml_feature_importance.json")
    print(f"[SUCCESS] Exported intensity breakdown to {OUTPUT_DIR}\\ml_intensity_breakdown.json")

if __name__ == "__main__":
    main()
