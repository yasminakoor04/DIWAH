import sys
from pathlib import Path
import logging
import pandas as pd

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.backend.calorimetry_parser import CalorimetryParser
from src.config.paths import DATA_ROOT, OUTPUT_ROOT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    aligned_dir = OUTPUT_ROOT / 'aligned'
    calo_dir = DATA_ROOT / 'calorimetry_anonymized'
    
    if not calo_dir.exists():
        logger.error(f"Calorimetry directory not found: {calo_dir}")
        return
        
    for subject_dir in aligned_dir.iterdir():
        if not subject_dir.is_dir():
            continue
            
        subject_id = subject_dir.name
        
        # Look for actigraph 5s to get the reference time block
        acti_file = subject_dir / 'Actigraph_aligned_5s.csv'
        if not acti_file.exists():
            continue
            
        acti_df = pd.read_csv(acti_file)
        start_time = pd.to_datetime(acti_df['timestamp'].iloc[0])
        end_time = pd.to_datetime(acti_df['timestamp'].iloc[-1])
        
        # Look for calorimetry file (focusing on activity session)
        calo_files = list(calo_dir.glob(f"{subject_id}_activity*"))
        if not calo_files:
            continue
            
        calo_file = calo_files[0]
        logger.info(f"Processing Calorimetry for {subject_id}")
        
        try:
            calo_df = CalorimetryParser.parse_file(calo_file)
            if calo_df.empty:
                logger.warning(f"  Failed to parse or empty for {subject_id}")
                continue
                
            calo_df['timestamp'] = pd.Timestamp(start_time) + pd.to_timedelta(calo_df['Time_s'], unit='s')
            c_clipped = calo_df[(calo_df['timestamp'] >= start_time) & (calo_df['timestamp'] <= end_time)].copy()
            
            if c_clipped.empty:
                logger.warning(f"  Empty after clipping for {subject_id}")
                continue
                
            c_clipped.set_index('timestamp', inplace=True)
            resampled = c_clipped[['HR', 'METS']].resample('5s').mean().reset_index()
            
            out_file = subject_dir / "Calorimetry_aligned_5s.csv"
            resampled.to_csv(out_file, index=False)
            logger.info(f"  Saved {out_file.name}")
        except Exception as e:
            logger.error(f"  Error on {subject_id}: {e}")

if __name__ == '__main__':
    main()
