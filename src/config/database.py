"""
InfluxDB database configuration for DIWAH Dashboard.

All settings are read from environment variables with development defaults.
In production, ensure all variables are explicitly set.
"""

import os
import warnings

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# InfluxDB connection settings
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_ORG = os.getenv("INFLUX_ORG", "diwah")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "wearables")

# Token handling - warn if using default
_default_token = "dev-token"
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", _default_token)

if INFLUX_TOKEN == _default_token:
    warnings.warn(
        "Using default INFLUX_TOKEN. Set INFLUX_TOKEN environment variable for production.",
        UserWarning
    )

# Connection settings
INFLUX_TIMEOUT_MS = int(os.getenv("INFLUX_TIMEOUT_MS", "60000"))
