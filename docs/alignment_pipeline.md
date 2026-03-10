# Timestamp Alignment Pipeline

This project includes a robust pipeline for aligning accelerometer data from Actigraph, Bangle.js, and EmotiBit devices to a common time window.

## Overview

The alignment logic is implemented in `src/alignment.py`. It addresses the following challenges:
1.  **Actigraph**: Uses absolute timestamps but starts recording at inconsistent line indices (header length varies by subject or configuration).
2.  **Bangle.js**: Uses relative timestamps (milliseconds since start) and needs to be synchronized to a reference time.
3.  **EmotiBit**: Uses its own timestamping mechanism and needs to be aligned to the reference.
4.  **End Time**: Devices are often removed at different times. The pipeline detects when activity ceases (magnitude drop) to trim the data.

## Configuration

The pipeline uses a configuration file to determine the true start line for each Actigraph file:
-   `src/config/start_lines.csv`: Maps `Subject` ID to `AccelerometerStart` line index.

## Pipeline Steps

1.  **Load Actigraph**: Reads the Actigraph RAW file and extracts the "Reference Start Time" using the line index from the config file.
2.  **Align Devices**:
    -   **Bangle**: Shifts the cumulative millisecond timestamps so `0` aligns with the Reference Start Time.
    -   **EmotiBit**: Aligns the start of the recording to the Reference Start Time.
    -   *Note*: Handles typo variations in filenames (e.g., `activitet`).
3.  **Detect End Time**:
    -   Scans backwards from the end of the file.
    -   detects the last "Active" period (where rolling standard deviation > threshold).
    -   Trims all data to the earliest detected end time (or intersection of valid windows).
4.  **Output**:
    -   Saves aligned CSV files to `output/aligned/{SubjectID}/`.
    -   Generates 5-second windowed aggregates for analysis.

## 5. Correlation Analysis

The pipeline's output is consumed by `src/correlation.py` to perform:
-   **Subject-level Correlation**: Pearson correlation coefficients for Bangle.js vs Actigraph and EmotiBit vs Actigraph.
-   **Cohort Analysis**: Aggregates results across all subjects, linked with demographic data (e.g., Gender).
-   **Subgroup Comparison**: Statistical tests (Mann-Whitney U) to compare model performance across demographic groups.

## Usage

### Run for a Single Subject

You can run the pipeline for specific subjects using the runner script:

```bash
# Run for specific subjects
python -m src.run_alignment
```

*Note: Update the list of subjects in `src/run_alignment.py` to process different users.*

### Programmatic Usage

```python
from src.alignment import AlignmentPipeline

# Initialize
pipeline = AlignmentPipeline(data_dir="path/to/diwah-anonymized")

# Run alignment
aligned_dfs = pipeline.align_subject("2002")

# Save results
pipeline.save_aligned_data(aligned_dfs, "2002", output_dir="output/aligned")
```
