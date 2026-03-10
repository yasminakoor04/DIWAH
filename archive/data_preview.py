import pandas as pd
from pathlib import Path
from src.config import ACTIGRAPH_PATH, BANGLE_PATH, EMOTIBIT_PATH, CALORIMETRY_PATH

def preview_file(file_path, name, n_lines=15):
    print(f"\n{'='*80}")
    print(f"{name}")
    print(f"   Path: {file_path}")
    print(f"   Size: {file_path.stat().st_size / (1024*1024):.2f} MB")
    print(f"{'='*80}\n")
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if i >= n_lines:
                    break
                print(f"{i+1:3d}: {line.rstrip()}")
        print(f"\n(First {n_lines} lines)")
    except Exception as e:
        print(f"Error reading file: {e}")

def preview_csv_with_pandas(file_path, name):
    """Try to read as CSV with pandas"""
    print(f"\n{'='*80}")
    print(f"{name} - Pandas Preview")
    print(f"{'='*80}\n")
    
    try:
        # Try reading without headers first
        df = pd.read_csv(file_path, nrows=10)
        print("DataFrame Info:")
        print(df.info())
        print("\nFirst 10 rows:")
        print(df.head(10))
        print(f"\nShape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
    except Exception as e:
        print(f"Error reading with pandas: {e}")

def main():
    """Preview sample files from each device"""
    
    print("DIWAH Data Preview Tool")
    print("="*80)
    
    # 1. Actigraph - Preview RAW and 5sec files
    print("\n\n" + "*"*40)
    print("ACTIGRAPH DATA")
    print("*"*40)
    
    actigraph_files = list(ACTIGRAPH_PATH.glob("*.csv"))
    if actigraph_files:
        # Preview a RAW file
        raw_file = [f for f in actigraph_files if 'RAW' in f.name and f.stat().st_size < 10*1024*1024]
        if raw_file:
            preview_file(raw_file[0], "Actigraph RAW")
            preview_csv_with_pandas(raw_file[0], "Actigraph RAW")
        
        # Preview a 5sec file
        sec5_file = [f for f in actigraph_files if '5sec' in f.name]
        if sec5_file:
            preview_file(sec5_file[0], "Actigraph 5sec")
            preview_csv_with_pandas(sec5_file[0], "Actigraph 5sec")
    
    # 2. Bangle - Preview activity and rest files
    print("\n\n" + "*"*40)
    print("BANGLE DATA")
    print("*"*40)
    
    bangle_files = list(BANGLE_PATH.glob("*.csv"))
    if bangle_files:
        # Preview activity file
        activity_file = [f for f in bangle_files if 'activity' in f.name]
        if activity_file:
            preview_file(activity_file[0], "Bangle Activity")
            preview_csv_with_pandas(activity_file[0], "Bangle Activity")
    
    # 3. Emotibit - Preview CSV and JSON
    print("\n\n" + "*"*40)
    print("EMOTIBIT DATA")
    print("*"*40)
    
    emotibit_dirs = [d for d in EMOTIBIT_PATH.iterdir() if d.is_dir()]
    if emotibit_dirs:
        sample_dir = emotibit_dirs[0]
        csv_files = list(sample_dir.glob("*.csv"))
        json_files = list(sample_dir.glob("*.json"))
        
        if csv_files:
            preview_file(csv_files[0], f"Emotibit CSV - {sample_dir.name}", n_lines=30)
            # Emotibit has complex format, manual preview is better first
        
        if json_files:
            preview_file(json_files[0], f"Emotibit JSON - {sample_dir.name}")
    
    # 4. Calorimetry - Preview XLS file
    print("\n\n" + "*"*40)
    print("CALORIMETRY DATA (Ground Truth)")
    print("*"*40)
    
    calor_files = list(CALORIMETRY_PATH.glob("*.xls"))
    if calor_files:
        print(f"\n {calor_files[0].name}")
        print("Note: XLS files need special handling with xlrd or openpyxl")
        try:
            df = pd.read_excel(calor_files[0])
            print("\nDataFrame Info:")
            print(df.info())
            print("\nFirst 10 rows:")
            print(df.head(10))
        except Exception as e:
            print(f"Error reading XLS: {e}")
            print("Tip: Install xlrd with: pip install xlrd")
    
    print("\n\n" + "="*80)
    print("Preview complete!")
    print("="*80)

if __name__ == "__main__":
    main()
