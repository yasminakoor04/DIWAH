# Data Explorer - Initial exploration of wearable sensor data
import os
from pathlib import Path
from src.config import ACTIGRAPH_PATH, BANGLE_PATH, EMOTIBIT_PATH, CALORIMETRY_PATH

def explore_directory_structure(base_path, device_name):
    print(f"\n{'='*60}")
    print(f"Exploring {device_name} data")
    print(f"Path: {base_path}")
    print(f"{'='*60}")
    
    if not base_path.exists():
        print(f"Path does not exist!")
        return
    
    print(f"Path exists!")
    
    # List all files
    try:
        files = list(base_path.rglob('*'))
        
        # Separate files and directories
        dirs = [f for f in files if f.is_dir()]
        files = [f for f in files if f.is_file()]
        
        print(f"\nFound {len(dirs)} directories and {len(files)} files")
        
        # Show directory structure
        if dirs:
            print("\nDirectories:")
            for d in sorted(dirs)[:10]:  # Show first 10
                print(f"  {d.relative_to(base_path)}")
            if len(dirs) > 10:
                print(f"  ... and {len(dirs) - 10} more directories")
        
        # Show files by extension
        if files:
            print("\nFiles by extension:")
            extensions = {}
            for f in files:
                ext = f.suffix.lower() or 'no_extension'
                extensions[ext] = extensions.get(ext, 0) + 1
            
            for ext, count in sorted(extensions.items()):
                print(f"  {ext}: {count} files")
            
            # Show sample files
            print(f"\nSample files (first 10):")
            for f in sorted(files)[:10]:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"  📄 {f.relative_to(base_path)} ({size_mb:.2f} MB)")
            
            if len(files) > 10:
                print(f"  ... and {len(files) - 10} more files")
    
    except Exception as e:
        print(f"Error exploring directory: {e}")

def preview_file_content(file_path, lines=10):
    """Preview first few lines of a file"""
    print(f"\n{'='*60}")
    print(f"Preview of: {file_path.name}")
    print(f"{'='*60}")
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if i >= lines:
                    break
                print(line.rstrip())
        print(f"\n(showing first {lines} lines)")
    except Exception as e:
        print(f"Error reading file: {e}")

def main():
    """Main exploration function"""
    print("DIWAH Wearable Data Explorer")
    print("="*60)
    
    # Explore each device's data
    explore_directory_structure(ACTIGRAPH_PATH, "Actigraph")
    explore_directory_structure(BANGLE_PATH, "Bangle")
    explore_directory_structure(EMOTIBIT_PATH, "Emotibit")
    explore_directory_structure(CALORIMETRY_PATH, "Calorimetry")
    
    print("\n" + "="*60)
    print("Exploration complete!")
    print("="*60)
    
    # Offer to preview files
    print("\nNext steps:")
    print("1. Review the file structure above")
    print("2. Run preview on specific files to understand data format")
    print("3. Create parsers for each data type")

if __name__ == "__main__":
    main()
