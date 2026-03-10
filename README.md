# DIWAH Intelligent Wearable Dashboard

**Analytics dashboard for validating wearable sensor data against indirect calorimetry ground truth.**

Compares accelerometer data from consumer devices (Bangle.js, EmotiBit) against research-grade Actigraph and metabolic measurements.

![Dashboard Main Page](docs/pictures/main_page.png)


## Prerequisites

- **Python 3.9+** ([Download](https://www.python.org/downloads/))
- **Docker** ([Download](https://www.docker.com/products/docker-desktop/))

## Quick Start

### 1. Clone and Setup
```bash
git clone <repository-url>
cd diwah-intelligent-wearable-dashboard

# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```

Default `.env` works for local development:
```
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=<your-token>
INFLUX_ORG=diwah
INFLUX_BUCKET=wearables
```

### 3. Start InfluxDB
```bash
docker-compose up -d influxdb
```

### 4. Load Data

**Option A: Import from backup**
```bash
python scripts/import_influx_data.py <backup-folder>
```

**Option B: Ingest from aligned CSV files**
```bash
# Ingest pre-aligned data from output/aligned/
python scripts/ingest_aligned_data.py

# Verify
python scripts/verify_influx.py
```

### 5. Run Dashboard
```bash
python run_dashboard.py
```
Open: [http://127.0.0.1:8050](http://127.0.0.1:8050)

---

## Data Management

### Import Data
```bash
python scripts/import_influx_data.py <backup-folder>
```

### Verify Database
```bash
python scripts/verify_influx.py
```

---

## Project Structure

```
├── src/
│   ├── analytics_dashboard.py   # Main Dash application
│   ├── backend/                 # Data loaders, parsers, correlation
│   ├── frontend/                # UI components, visualizations
│   └── config.py                # Configuration
├── scripts/
│   ├── ingest_aligned_data.py   # Ingest pre-aligned CSVs to InfluxDB
│   ├── export_influx_data.py    # Export to Line Protocol backup
│   ├── import_influx_data.py    # Import from backup
│   ├── verify_influx.py         # Database verification
│   └── reset_influxdb.py        # Wipe and recreate bucket
├── output/aligned/              # Pre-processed aligned data (5s epochs)
├── diwah-anonymized/            # Raw sensor data (not in git)
├── influxdb-backups/            # Data backups
└── docs/                        # Documentation
```

## Data Pipeline

1. **Raw Data** (`diwah-anonymized/`) → Actigraph, Bangle, EmotiBit, Calorimetry files
2. **Alignment** (`src/backend/alignment.py`) → Synchronize timestamps, 5s resampling
3. **Output** (`output/aligned/`) → Pre-aligned CSVs per subject/device
4. **Ingestion** → Load to InfluxDB with subject/device/session tags
5. **Dashboard** → Query InfluxDB, visualize correlations

## Documentation

- [Participant Mapping](docs/participants.md) — ID reference
- [Alignment Pipeline](docs/alignment_pipeline.md) — Synchronization logic
- [Correlation Report](docs/correlation_alignment_report.md) — Validation results