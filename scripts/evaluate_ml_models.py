#!/usr/bin/env python3
"""
DIWAH — Machine Learning Evaluation Script (Redesigned)
========================================================
Evaluates three prediction scenarios for METs prediction using Leave-One-Subject-Out CV:
  1. REFERENCE   — ActiGraph accelerometer + Polar HR stat features
  2. EMOTIBIT    — EmotiBit accelerometer features only
  3. BANGLE.JS   — Bangle.js accelerometer features only

Outputs a formatted table of MAE, RMSE, and R-squared for direct use in the thesis.

Methodology
  - Imputer leakage fix: SimpleImputer + StandardScaler wrapped in sklearn.Pipeline
  - Bad subject exclusion: 6 participants with hardware failures excluded
  - Ridge alpha tuning: nested GroupKFold CV over [0.1, 1, 10, 100, 1000]

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
import json

# Data Manipulation
import pandas as pd
import numpy as np

# Scikit-learn
from sklearn.model_selection import LeaveOneGroupOut, GroupKFold, GridSearchCV
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# InfluxDB
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS

# Project paths & config
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

OUTPUT_DIR = _SCRIPT_DIR / "Acc_pipe" / "data" / "processed"

SCENARIOS = {
    "reference": {
        "label": "Reference (ActiGraph + Polar HR)",
        "path": OUTPUT_DIR / "flirt_reference.csv"
    },
    "emotibit": {
        "label": "EmotiBit (Open-Source)",
        "path": OUTPUT_DIR / "flirt_emotibit.csv"
    },
    "bangle": {
        "label": "Bangle.js (Open-Source)",
        "path": OUTPUT_DIR / "flirt_bangle.csv"
    }
}

# Participants excluded due to known hardware failures during data collection
# (consistent with validate_synchronization.ipynb)
BAD_SUBJECTS = [2004, 2005, 2008, 2014, 2019, 2032]

# Ridge alpha search space (supervisor suggestion)
RIDGE_ALPHAS = [0.1, 1, 10, 100, 1000]


def classify_intensity(mets_value: float) -> str:
    """Classify a MET value into standard intensity zones."""
    if mets_value < 3.0:
        return "Light"
    elif mets_value < 6.0:
        return "Moderate"
    else:
        return "Vigorous"


def compute_intensity_breakdown(y_test_all, preds_dict_all):
    """
    Compute MAE and RMSE broken down by intensity zone.
    """
    zones = [classify_intensity(m) for m in y_test_all]
    zone_labels = ["Light", "Moderate", "Vigorous"]
    
    breakdown = {}
    for model_name, preds in preds_dict_all.items():
        short_name = "MLR" if model_name == "Multiple Linear Regression" else "RF"
        breakdown[short_name] = {}
        for zone in zone_labels:
            mask = [z == zone for z in zones]
            y_zone = np.array(y_test_all)[mask]
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
        
    df_influx = pred_df.copy()
    df_influx['timestamp'] = pd.to_datetime(df_influx['timestamp'], errors='coerce', utc=True)
    df_influx = df_influx.dropna(subset=['timestamp'])
    df_influx = df_influx.set_index('timestamp')
    df_influx['subject'] = df_influx['subject'].astype(str)
    
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=120_000) as client:
            write_api = client.write_api(write_options=ASYNCHRONOUS)
            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=df_influx,
                data_frame_measurement_name="ml_predictions",
                data_frame_tag_columns=["subject", "Device", "Model"],
                write_precision=WritePrecision.S,
            )
            write_api.close()
        print(f"  [SUCCESS] Successfully pushed {len(df_influx)} predictions to InfluxDB.")
    except Exception as e:
        print(f"  [ERROR] Failed to push to InfluxDB: {e}")


def print_beautiful_summary(results: dict):
    """Prints a clean, thesis-ready ASCII table comparing the results."""
    print("\n" + "="*80)
    print(" MACHINE LEARNING EVALUATION SUMMARY: LOSO CROSS-VALIDATION")
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-influx", action="store_true", help="Skip pushing to InfluxDB")
    args = parser.parse_args()
    
    results = {}
    all_predictions = []
    all_feature_importances = {}
    all_intensity_breakdowns = {}
    
    for scenario_key, scenario_cfg in SCENARIOS.items():
        print(f"\n{'='*60}\nScenario: {scenario_cfg['label']}\n{'='*60}")
        csv_path = scenario_cfg['path']
        if not csv_path.exists():
            print(f"  [ERROR] File not found: {csv_path}")
            continue
            
        df = pd.read_csv(csv_path)
        
        # We might have an 'Unnamed: 0' if we saved with index. Let's rename it to timestamp if it looks like one
        if 'Unnamed: 0' in df.columns:
            df = df.rename(columns={'Unnamed: 0': 'timestamp'})
            
        df = df.dropna(subset=["mets", "subject_id"])

        # Exclude participants with known data quality issues
        # (consistent with validate_synchronization.ipynb)
        df = df[~df["subject_id"].isin(BAD_SUBJECTS)]
        print(f"  Loaded {len(df)} epochs (after excluding {len(BAD_SUBJECTS)} bad subjects).")
        
        y = df['mets'].values
        groups = df['subject_id'].astype(str).values
        
        # Isolate features
        cols_to_drop = ['timestamp', 'mets', 'subject_id', 'datetime']
        cols_to_drop = [c for c in cols_to_drop if c in df.columns]
        X_raw = df.drop(columns=cols_to_drop)
        X = X_raw.select_dtypes(include=[np.number])
        X = X.replace([np.inf, -np.inf], np.nan)
        feature_names = X.columns.tolist()
        
        # Fit global RF on full dataset for feature importances (impute+scale first)
        imp_global = SimpleImputer(strategy='median')
        X_imputed_global = imp_global.fit_transform(X)
        sc_global = StandardScaler()
        X_global_scaled = sc_global.fit_transform(X_imputed_global)
        rf_global = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        rf_global.fit(X_global_scaled, y)
        importances = rf_global.feature_importances_
        importance_data = [{"feature": name, "importance": float(imp)} for name, imp in zip(feature_names, importances)]
        importance_data.sort(key=lambda x: x["importance"], reverse=True)
        all_feature_importances[scenario_key] = importance_data[:20]
        
        # LOSO Cross-Validation using Pipelines (no leakage)
        logo = LeaveOneGroupOut()
        rf_true_all, rf_pred_all = [], []
        ridge_true_all, ridge_pred_all = [], []
        test_timestamps_all = []
        test_subjects_all = []
        
        rf_pipeline = Pipeline([
            ('imp', SimpleImputer(strategy='median')),
            ('sc', StandardScaler()),
            ('mdl', RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1))
        ])
        
        ts_col = df['timestamp'].values if 'timestamp' in df.columns else df['datetime'].values
        
        print("  Running Leave-One-Subject-Out Cross-Validation...")
        for train_index, test_index in logo.split(X, y, groups):
            X_train, X_test = X.iloc[train_index], X.iloc[test_index]
            y_train, y_test = y[train_index], y[test_index]
            groups_train = groups[train_index]
            
            # Random Forest (Pipeline prevents leakage)
            rf_pipeline.fit(X_train, y_train)
            rf_pred = rf_pipeline.predict(X_test)
            rf_true_all.extend(y_test)
            rf_pred_all.extend(rf_pred)
            
            # Ridge with nested alpha tuning (GroupKFold)
            ridge_pipe = Pipeline([
                ('imp', SimpleImputer(strategy='median')),
                ('sc', StandardScaler()),
                ('mdl', Ridge())
            ])
            n_inner = min(5, len(np.unique(groups_train)))
            grid = GridSearchCV(
                ridge_pipe,
                param_grid={'mdl__alpha': RIDGE_ALPHAS},
                cv=GroupKFold(n_splits=n_inner),
                scoring='neg_mean_absolute_error',
                n_jobs=-1
            )
            grid.fit(X_train, y_train, groups=groups_train)
            ridge_pred = grid.predict(X_test)
            ridge_true_all.extend(y_test)
            ridge_pred_all.extend(ridge_pred)
            
            test_timestamps_all.extend(ts_col[test_index])
            test_subjects_all.extend(groups[test_index])
            
        metrics = {
            "MLR": {
                "MAE": mean_absolute_error(ridge_true_all, ridge_pred_all),
                "RMSE": np.sqrt(mean_squared_error(ridge_true_all, ridge_pred_all)),
                "R2": r2_score(ridge_true_all, ridge_pred_all)
            },
            "RF": {
                "MAE": mean_absolute_error(rf_true_all, rf_pred_all),
                "RMSE": np.sqrt(mean_squared_error(rf_true_all, rf_pred_all)),
                "R2": r2_score(rf_true_all, rf_pred_all)
            }
        }
        results[scenario_key] = metrics
        
        preds_payload = {
            "Multiple Linear Regression": ridge_pred_all,
            "Random Forest": rf_pred_all
        }
        all_intensity_breakdowns[scenario_key] = compute_intensity_breakdown(rf_true_all, preds_payload)
        
        for t_idx, (t_val, p_mlr, p_rf) in enumerate(zip(rf_true_all, ridge_pred_all, rf_pred_all)):
            all_predictions.append({
                "timestamp": test_timestamps_all[t_idx],
                "subject": test_subjects_all[t_idx],
                "Device": scenario_cfg["label"],
                "Model": "Multiple Linear Regression",
                "True_METs": t_val,
                "Pred_METs": p_mlr
            })
            all_predictions.append({
                "timestamp": test_timestamps_all[t_idx],
                "subject": test_subjects_all[t_idx],
                "Device": scenario_cfg["label"],
                "Model": "Random Forest",
                "True_METs": t_val,
                "Pred_METs": p_rf
            })

    print_beautiful_summary(results)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(OUTPUT_DIR / "ml_metrics.json", "w") as f:
        json.dump(results, f, indent=4)
        
    pred_df = pd.DataFrame(all_predictions)
    pred_df.to_csv(OUTPUT_DIR / "ml_predictions.csv", index=False)
    
    with open(OUTPUT_DIR / "ml_feature_importance.json", "w") as f:
        json.dump(all_feature_importances, f, indent=4)
    
    with open(OUTPUT_DIR / "ml_intensity_breakdown.json", "w") as f:
        json.dump(all_intensity_breakdowns, f, indent=4)
    
    print("\n[SUCCESS] Exported JSON metrics and predictions backup.")

    if not args.no_influx:
        push_predictions_to_influx(pred_df)


if __name__ == "__main__":
    main()
