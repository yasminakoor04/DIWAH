#!/usr/bin/env python3
"""
Entry point for running the DIWAH Analytics Dashboard.
"""
import sys
import os
from pathlib import Path

# Add project root to path so we can resolve 'src' imports
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

from src.analytics_dashboard import run_server

if __name__ == '__main__':
    # Get debug mode from env
    debug = os.getenv('DASHBOARD_DEBUG', 'False').lower() == 'true'
    
    # Run the server
    run_server(debug=debug)
