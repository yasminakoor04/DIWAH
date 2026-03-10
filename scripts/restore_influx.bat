@echo off
REM ========================================================================
REM InfluxDB Restore Script
REM Restores data and metadata to InfluxDB from backup
REM ========================================================================

echo.
echo ========================================================================
echo InfluxDB Restore Utility
echo ========================================================================
echo.

if "%~1"=="" (
    echo ERROR: No backup directory specified!
    echo.
    echo Usage: restore_influx.bat BACKUP_PATH
    echo.
    echo Example:
    echo   restore_influx.bat influxdb-backups\backup_20251202_143000
    echo.
    pause
    exit /b 1
)

set BACKUP_PATH=%~1

if not exist "%BACKUP_PATH%" (
    echo ERROR: Backup directory not found: %BACKUP_PATH%
    echo.
    pause
    exit /b 1
)

echo Backup directory: %BACKUP_PATH%
echo.
echo WARNING: This will restore data to InfluxDB.
echo If data already exists, you may need to use --full flag.
echo.
set /p CONFIRM="Continue with restore? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Cancelled.
    exit /b 0
)

echo.
echo Copying backup to container...
docker cp "%BACKUP_PATH%" influxdb:/restore-temp

echo.
echo Starting restore...
docker exec influxdb influx restore /restore-temp -t dev-token --full

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================================
    echo Restore completed successfully!
    echo ========================================================================
    echo.
    echo Restart the dashboard to see restored data:
    echo   python run_dashboard.py
    echo.
) else (
    echo.
    echo ========================================================================
    echo ERROR: Restore failed!
    echo ========================================================================
    echo.
    echo Common issues:
    echo   - Bucket already exists: Use --full flag or delete existing bucket
    echo   - InfluxDB not running: docker compose up -d influxdb
    echo.
)

REM Cleanup
docker exec influxdb rm -rf /restore-temp

@echo off
REM ========================================================================
REM InfluxDB Restore Script (OSS v2)
REM Restores data/metadata from a backup directory
REM Supports Docker container (named 'influxdb') and bare-metal CLI
REM Usage:
REM   restore_influx.bat <BACKUP_DIR> [--full] [--bucket BUCKET_NAME] [--new-bucket NEW_NAME]
REM Examples:
REM   restore_influx.bat influxdb-backups\backup_20251202_120000 --full
REM   restore_influx.bat influxdb-backups\bucket_wearables_20251202 --bucket wearables --new-bucket wearables_restored
REM ========================================================================

if "%~1"=="" (
    echo Usage: restore_influx.bat ^<BACKUP_DIR^> [--full] [--bucket BUCKET_NAME] [--new-bucket NEW_NAME]
    exit /b 1
)

set BACKUP_DIR=%~1
set MODE=cli
set FULL_FLAG=
set BUCKET=
set NEW_BUCKET=

:parse_args
if "%~2"=="--full" (
    set FULL_FLAG=--full
    shift
    goto parse_args
)
if "%~2"=="--bucket" (
    set BUCKET=%~3
    shift
    shift
    goto parse_args
)
if "%~2"=="--new-bucket" (
    set NEW_BUCKET=%~3
    shift
    shift
    goto parse_args
)

REM Detect Docker container named 'influxdb'
for /f "tokens=*" %%i in ('docker ps --format "{{.Names}}" ^| findstr /i ^<influxdb^>') do set MODE=docker

echo.
echo ========================================================================
echo InfluxDB Restore Utility
echo Backup source: %BACKUP_DIR%
echo Mode: %MODE%
echo Full restore: %FULL_FLAG%
echo Bucket: %BUCKET%
echo New bucket: %NEW_BUCKET%
echo ========================================================================
echo.

REM Configure token and URL (use env vars if set)
if not defined INFLUX_TOKEN set INFLUX_TOKEN=REPLACE_WITH_ADMIN_TOKEN
if not defined INFLUX_URL set INFLUX_URL=http://127.0.0.1:8086

if "%MODE%"=="docker" (
    echo Restoring inside Docker container 'influxdb'...
    echo Copying backup into container...
    docker cp "%BACKUP_DIR%" influxdb:/restore_src || (
        echo ERROR: Failed to copy backup into container.
        exit /b 1
    )
    echo Running influx restore in container...
    if defined FULL_FLAG (
        docker exec influxdb influx restore /restore_src %FULL_FLAG% -t %INFLUX_TOKEN% || (
            echo ERROR: Full restore failed.
            exit /b 1
        )
    ) else (
        if defined BUCKET (
            if defined NEW_BUCKET (
                docker exec influxdb influx restore /restore_src --bucket %BUCKET% --new-bucket %NEW_BUCKET% -t %INFLUX_TOKEN% || (
                    echo ERROR: Bucket restore failed.
                    exit /b 1
                )
            ) else (
                docker exec influxdb influx restore /restore_src --bucket %BUCKET% -t %INFLUX_TOKEN% || (
                    echo ERROR: Bucket restore failed.
                    exit /b 1
                )
            )
        ) else (
            docker exec influxdb influx restore /restore_src -t %INFLUX_TOKEN% || (
                echo ERROR: Restore failed.
                exit /b 1
            )
        )
    )
) else (
    echo Restoring using local CLI...
    if defined FULL_FLAG (
        influx restore "%BACKUP_DIR%" %FULL_FLAG% -t %INFLUX_TOKEN% -u %INFLUX_URL% || (
            echo ERROR: Full restore failed.
            exit /b 1
        )
    ) else (
        if defined BUCKET (
            if defined NEW_BUCKET (
                influx restore "%BACKUP_DIR%" --bucket %BUCKET% --new-bucket %NEW_BUCKET% -t %INFLUX_TOKEN% -u %INFLUX_URL% || (
                    echo ERROR: Bucket restore failed.
                    exit /b 1
                )
            ) else (
                influx restore "%BACKUP_DIR%" --bucket %BUCKET% -t %INFLUX_TOKEN% -u %INFLUX_URL% || (
                    echo ERROR: Bucket restore failed.
                    exit /b 1
                )
            )
        ) else (
            influx restore "%BACKUP_DIR%" -t %INFLUX_TOKEN% -u %INFLUX_URL% || (
                echo ERROR: Restore failed.
                exit /b 1
            )
        )
    )
)

echo.
echo ========================================================================
echo Restore completed.
echo Verify buckets with:
echo   influx bucket list -t %INFLUX_TOKEN% -u %INFLUX_URL%
echo ========================================================================
echo.

pause
