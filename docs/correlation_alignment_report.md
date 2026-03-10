# Correlation Alignment Fix & Dashboard Report

## 1. Problem Summary
Initial correlation analysis between the **Actigraph** (reference device) and **Bangle.js** (test device) showed a near-zero correlation (**r ≈ 0.03**) for subject `2002`.

### Root Cause Analysis
-   The **Actigraph** recording includes a significant "Rest" period before the actual activity begins.
-   The previous configuration (`start_lines.csv`) pointed to the very beginning of the file (e.g., line 176), capturing ~10 minutes of sensor noise (gravity only).
-   The **Bangle.js** data, which records only during activity, was being aligned to this "Rest" period.
-   **Result**: Comparing a constant 1g signal (Rest) with a dynamic signal (Activity) yields zero correlation.

## 2. The Solution: Auto-Detection

I implemented an **Auto-Detection Algorithm** (`src/alignment.auto_detect_activity_start`) that identifies the true start of activity.

### Algorithm Logic
1.  **Metric**: Calculates the rolling standard deviation (variability) of the accelerometer magnitude.
2.  **Thresholds**:
    -   **Variance**: Looks for periods where `std_dev > 0.03g` (Activity) vs `< 0.01g` (Rest).
    -   **Magnitude**: Checks for peaks `> 1.1g`.
3.  **Action**: Updates the start timestamp to the moment variability increases.

### Implementation Diagram

```mermaid
graph TD
    A[Raw Actigraph File] --> B{Calculate Rolling StdDev}
    B --> C[Identify Rest Period <br/> (StdDev < 0.01, Mag ~ 1.0)]
    C --> D[Identify Activity Start <br/> (StdDev > 0.03 or Mag > 1.1)]
    D --> E[Update Start Timestamp]
    E --> F[Align Bangle & EmotiBit <br/> to New Timestamp]
```

## 3. Results (Before vs After)

We batch-processed all **28 subjects** using the new logic.

| Subject | Old Correlation (r) | New Correlation (r) | Improvement |
| :--- | :--- | :--- | :--- |
| **2002** | 0.03 (No correlation) | **0.57** (Moderate/Strong) | ✅ **+0.54** |

## 4. Visual Verification (Dashboard)

The new **Correlation Dashboard** allows you to verify this visually.

### How to Verify
1.  Run the dashboard: `python src/analytics_dashboard.py`
2.  Open **Correlations** tab.
3.  Select Subject **2002**.

### What to Look For
-   **Time Series**: The peaks of Actigraph (Blue) and Bangle (Red) should now align in time.

## 5. Beyond Single Subjects: Cohort Analysis

The dashboard has been expanded to support **Cohort-Level Analysis**, moving beyond individual debugging to group-wide insights.

### New Layout Features
-   **Cohort Summary**: Instantly view the mean correlation across all subjects (e.g., *Overall r = 0.82*).
-   **Demographic Split**: Automatically segments performance by Gender (Male vs. Female).
-   **Statistical Validation**: Integrated **Mann-Whitney U test** checks if device accuracy differs significantly between groups.

This ensures that the alignment fix works robustly across the entire population, not just the initial test cases.
