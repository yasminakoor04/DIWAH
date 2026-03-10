"""
InfluxDB connection management for DIWAH Dashboard.

Provides:
- Lazy initialization (connect on first query, not at import)
- Proper connection cleanup via context manager
- Health check functionality
- Centralized query execution with error handling

Usage:
    from database import get_query_api, tag_values, health_check
    
    # For queries:
    query_api = get_query_api()
    results = query_api.query(flux_query)
    
    # For health checks:
    if health_check():
        print("Database is healthy")
"""

import logging
import atexit
from typing import Optional, List, Generator
from contextlib import contextmanager

from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi

from ..config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

logger = logging.getLogger(__name__)

# Connection timeout in milliseconds
# Increased to 60s to prevent Read Tiemouts on heavy queries
INFLUX_TIMEOUT_MS = 60_000 

# Global client instance (lazy initialized)
_client: Optional[InfluxDBClient] = None
_query_api: Optional[QueryApi] = None


def _get_client(timeout: int = INFLUX_TIMEOUT_MS) -> InfluxDBClient:
    """
    Get or create the InfluxDB client.
    
    Args:
        timeout: Timeout in milliseconds (default: global setting)
    
    Returns:
        InfluxDBClient instance
    """
    global _client
    
    # If client exists and timeout is same, return it.
    # If timeout different (health check), create temp client if needed, or just return new one.
    # Actually, simpler: _client is the global singleton with standard timeout.
    # For custom timeout, we create a new temporary instance.
    
    if timeout != INFLUX_TIMEOUT_MS:
         logger.debug(f"Creating temp InfluxDB client with timeout={timeout}ms")
         return InfluxDBClient(
            url=INFLUX_URL,
            token=INFLUX_TOKEN,
            org=INFLUX_ORG,
            timeout=timeout
        )

    if _client is None:
        logger.debug(f"Initializing global InfluxDB client: {INFLUX_URL}")
        _client = InfluxDBClient(
            url=INFLUX_URL,
            token=INFLUX_TOKEN,
            org=INFLUX_ORG,
            timeout=INFLUX_TIMEOUT_MS
        )
    
    return _client


def get_query_api() -> QueryApi:
    """
    Get the query API for executing Flux queries.
    
    Returns:
        QueryApi instance
    """
    global _query_api
    
    if _query_api is None:
        client = _get_client()
        _query_api = client.query_api()
    
    return _query_api


def close_connection() -> None:
    """
    Close the database connection and cleanup resources.
    
    Should be called when the application shuts down.
    """
    global _client, _query_api
    
    if _client is not None:
        logger.debug("Closing InfluxDB connection")
        _client.close()
        _client = None
        _query_api = None


@contextmanager
def get_client_context() -> Generator[InfluxDBClient, None, None]:
    """
    Context manager for database operations that need explicit cleanup.
    
    Usage:
        with get_client_context() as client:
            write_api = client.write_api()
            # ... do work ...
    """
    client = _get_client()
    try:
        yield client
    finally:
        # Don't close the shared client, just yield it
        pass


def health_check() -> bool:
    """
    Check if the database connection is healthy and fast.
    Uses a short timeout (1s) to avoid hanging in offline mode.
    
    Returns:
        True if database is reachable, False otherwise
    """
    try:
        # Use a 5000ms timeout for health check
        # enough for localhost, prevents false offline warnings on fast restarts
        client = _get_client(timeout=5000)
        
        # Ping returns bool in this client version usually, or verified reachable
        is_ok = client.ping()
        
        # If we created a temp client, close it
        if client != _client:
            client.close()
            
        return is_ok
    except Exception as e:
        # catch everything - connection errors, timeouts, etc.
        return False


def tag_values(tag: str, subject: Optional[str] = None) -> List[str]:
    """
    Query distinct tag values from InfluxDB.
    
    Args:
        tag: Tag name to query (e.g., 'subject', 'session', 'device')
        subject: Optional subject filter
    
    Returns:
        Sorted list of unique tag values
    """
    vals = set()
    
    try:
        if health_check():
            query_api = get_query_api()
            
            # Build filter predicate
            predicate = 'r._measurement == "accelerometer"'
            if subject:
                safe_subject = str(subject).replace('"', '\\"')
                predicate += f' and r.subject == "{safe_subject}"'
            
            # Method 1: Try schema.tagValues first (fast, but unreliable on some Docker deployments)
            try:
                flux = f'''import "influxdata/influxdb/schema"
                schema.tagValues(
                    bucket: "{INFLUX_BUCKET}", 
                    tag: "{tag}", 
                    predicate: (r) => {predicate}, 
                    start: -100y, 
                    stop: now()
                )'''
                
                for table in query_api.query(flux):
                    for rec in table.records:
                        v = rec.get_value()
                        if v:
                            vals.add(v)
            except Exception:
                pass
            
            # Method 2: Fallback using keep/distinct (works on all InfluxDB 2.x)
            if not vals:
                logger.info(f"schema.tagValues returned empty for '{tag}', using fallback query")
                flux_fallback = f'''from(bucket: "{INFLUX_BUCKET}")
                    |> range(start: 0)
                    |> filter(fn: (r) => {predicate})
                    |> keep(columns: ["{tag}"])
                    |> distinct(column: "{tag}")'''
                
                for table in query_api.query(flux_fallback):
                    for rec in table.records:
                        v = rec.get_value()
                        if v:
                            vals.add(v)
                            
    except Exception as e:
        logger.warning(f"InfluxDB query failed for '{tag}': {e}")

    return sorted(list(vals))


def get_bucket() -> str:
    """Get the configured bucket name."""
    return INFLUX_BUCKET


# Register cleanup on application exit
atexit.register(close_connection)
