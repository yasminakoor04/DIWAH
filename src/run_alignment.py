import sys
from pathlib import Path
import logging

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.backend.alignment import AlignmentPipeline
from src.config import DATA_ROOT, OUTPUT_ROOT, EXCLUDED_SUBJECTS

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Alignment Pipeline...")
    logger.info(f"Data Source: {DATA_ROOT}")
    logger.info(f"Output: {OUTPUT_ROOT}/aligned")
    
    pipeline = AlignmentPipeline(DATA_ROOT, OUTPUT_ROOT / "aligned")
    
    # Derive subjects from Actigraph RAW files
    actigraph_dir = DATA_ROOT / "Actigraph (research device accelerometry)"
    if not actigraph_dir.exists():
        logger.error(f"Actigraph directory not found: {actigraph_dir}")
        return

    subjects = []
    for f in actigraph_dir.glob("*RAW.csv"):
        # Filename format: "2002 (2024-05-14)RAW.csv" -> "2002"
        # Split by space or just take first part
        sid = f.name.split(' ')[0]
        if sid not in subjects:
            subjects.append(sid)
            
    subjects.sort()
    logger.info(f"Found {len(subjects)} subjects: {subjects}")
    
    count = 0
    for subject in subjects:
        if subject in EXCLUDED_SUBJECTS:
            continue
            
        logger.info(f"Processing subject: {subject}")
        pipeline.process_subject(subject)
        count += 1
        
    logger.info(f"Alignment complete. Processed {count} subjects.")

if __name__ == "__main__":
    main()
