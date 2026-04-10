#!/usr/bin/env python3
"""
Run the R extraction pipeline for untrimmed bad-subject epochs.

This wrapper injects setwd() and executes scripts/extract_untrimmed_from_rds.R.
"""

import argparse
import subprocess
import tempfile
from pathlib import Path


def _r_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run_extraction(
    rscript_exe: str,
    working_dir: Path,
    r_script: Path,
    rds_path: Path,
    output_csv: Path,
) -> None:
    launcher = f'''setwd("{_r_string(str(working_dir))}")
source("{_r_string(str(r_script))}")
run_untrimmed_export(
  rds_path = "{_r_string(str(rds_path))}",
  output_csv = "{_r_string(str(output_csv))}"
)
'''

    with tempfile.NamedTemporaryFile("w", suffix=".R", delete=False, encoding="utf-8") as tmp:
        tmp.write(launcher)
        launcher_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [rscript_exe, str(launcher_path)],
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "R extraction failed.\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        print(result.stdout.strip())
    finally:
        if launcher_path.exists():
            launcher_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract untrimmed 5s epochs for excluded subjects from raw_data.rds")
    parser.add_argument(
        "--rds-path",
        type=Path,
        default=Path(r"C:\Users\Hanna\Downloads\OneDrive_1_4-2-2026\data\processed\raw_data.rds"),
        help="Path to raw_data.rds",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path(r"C:\Users\Hanna\Downloads\OneDrive_1_4-2-2026\data\processed\master_epochs_untrimmed.csv"),
        help="Output CSV path for untrimmed 5s epochs",
    )
    parser.add_argument(
        "--r-script",
        type=Path,
        default=Path(__file__).resolve().with_name("extract_untrimmed_from_rds.R"),
        help="Path to extraction R script",
    )
    parser.add_argument(
        "--rscript-exe",
        default="Rscript",
        help="Rscript executable",
    )
    parser.add_argument(
        "--working-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Working directory passed to setwd()",
    )
    args = parser.parse_args()

    run_extraction(
        rscript_exe=args.rscript_exe,
        working_dir=args.working_dir,
        r_script=args.r_script,
        rds_path=args.rds_path,
        output_csv=args.output_csv,
    )


if __name__ == "__main__":
    main()
