@echo off
REM ========================================================================
REM InfluxDB Backup Script
REM Backs up all data and metadata from local InfluxDB instance
REM ========================================================================

echo.
echo ========================================================================
echo InfluxDB Backup Utility
echo ========================================================================
echo.

REM Set backup directory with robust timestamp (YYYYMMDD_HHMMSS)
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value ^| findstr /i LocalDateTime') do set LDT=%%I
set YYYY=%LDT:~0,4%
set MM=%LDT:~4,2%
set DD=%LDT:~6,2%
set HH=%LDT:~8,2%
set MI=%LDT:~10,2%
set SS=%LDT:~12,2%
set BACKUP_DIR=influxdb-backups\backup_%YYYY%%MM%%DD%_%HH%%MI%%SS%

echo Creating backup directory: %BACKUP_DIR%
mkdir "%BACKUP_DIR%" 2>nul

echo.
echo Starting backup...
echo This will back up all buckets, users, dashboards, and data.
echo.

REM Detect Docker container named 'influxdb'
set MODE=cli
for /f "tokens=*" %%i in ('docker ps --format "{{.Names}}"') do (
    if /i "%%i"=="influxdb" set MODE=docker
)

if "%MODE%"=="docker" (
    echo Detected Docker container 'influxdb' - running in-container backup...
    REM Use env token; fail if missing
    if not defined INFLUX_TOKEN (
        echo ERROR: INFLUX_TOKEN is not set. Please set admin token and re-run.
        echo Example: set INFLUX_TOKEN=your_admin_token
        goto :end
    )
    docker exec influxdb influx backup /backup -t %INFLUX_TOKEN%
    docker cp influxdb:/backup "%BACKUP_DIR%"
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ========================================================================
        echo Backup completed successfully!
        echo ========================================================================
        echo Backup location: %BACKUP_DIR%
        echo.
        echo To restore this backup, run:
        echo   scripts\restore_influx.bat "%BACKUP_DIR%" --full
        echo.
    ) else (
        echo.
        echo ========================================================================
        echo ERROR: Backup failed in Docker mode!
        echo ========================================================================
        echo Make sure InfluxDB container is running: docker compose up -d influxdb
        echo.
    )
) else (
    echo No Docker container detected - using local CLI backup...
    where influx >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Influx CLI not found. Install it from https://docs.influxdata.com/influxdb/v2/install/ ^(Windows^) or add it to PATH.
        echo Alternatively, run via Docker: ensure a container named "influxdb" is running and re-run this script.
        goto :end
    )
    if not defined INFLUX_TOKEN (
        echo ERROR: INFLUX_TOKEN is not set. Please set admin token and re-run.
        echo Example: set INFLUX_TOKEN=your_admin_token
        goto :end
    )
    if not defined INFLUX_URL set INFLUX_URL=http://127.0.0.1:8086
    echo Using URL: %INFLUX_URL%
    influx backup "%BACKUP_DIR%" --token %INFLUX_TOKEN% --host %INFLUX_URL%
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ========================================================================
        echo Backup completed successfully!
        echo ========================================================================
        echo Backup location: %BACKUP_DIR%
        echo.
        echo To restore this backup, run:
        echo   scripts\restore_influx.bat "%BACKUP_DIR%" --full
        echo.
    ) else (
        echo.
        echo ========================================================================
        echo ERROR: Backup failed in CLI mode!
        echo ========================================================================
        echo Check that influxd is running and INFLUX_TOKEN/INFLUX_URL are correct.
        echo.
    )
)

:end

pause
