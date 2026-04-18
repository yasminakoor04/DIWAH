#!/usr/bin/env python3
"""
DIWAH Machine Learning Evaluation
=================================
Trains and evaluates regression models to predict exercise intensity (METs)
using the 5-second FLIRT features extracted from ActiGraph, Bangle.js, and EmotiBit.

This script separates the feature matrix dynamically by device, handles missing values,
scales features, and evaluates models (Multiple Linear Regression, Random Forest).
Outputs a formatted table of MAE, RMSE, and R-squared for direct use in the thesis.
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

# Paths
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
DEFAULT_FEATURE_MATRIX = _PROJECT_ROOT / "data" / "flirt_feature_matrix_ready.csv"

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

def train_and_evaluate(X_train, X_test, y_train, y_test):
    """
    Trains MLR and Random Forest, returning a dictionary of metrics.
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
    
    return metrics

def print_beautiful_summary(results: dict):
    """
    Prints a clean, thesis-ready ASCII table comparing the results.
    """
    print("\n" + "="*80)
    print(" MACHINE LEARNING EVALUATION SUMMARY: ACTIVITY INTENSITY (METs) PREDICTION")
    print("="*80)
    print(f"{'Device Scenario':<15} | {'Model':<25} | {'MAE':<10} | {'RMSE':<10} | {'R-squared (R²)':<12}")
    print("-" * 80)
    
    devices = ["ActiGraph", "EmotiBit", "Bangle"]
    
    for device in devices:
        res = results.get(device.lower())
        if not res:
            continue
            
        print(f"{device:<15} | {'Multiple Linear Regression':<25} | "
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
    
    devices = ["actigraph", "emotibit", "bangle"]
    results = {}
    
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
        
        # 2. Impute NaNs (Forward fill was used earlier, but 
        # FLIRT might return NaN/Inf if a window was mostly empty).
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
        metrics = train_and_evaluate(X_train_scaled, X_test_scaled, y_train, y_test)
        
        results[device] = metrics
        
    # 6. Output Table
    print_beautiful_summary(results)

if __name__ == "__main__":
    main()
