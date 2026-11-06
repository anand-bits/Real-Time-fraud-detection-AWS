"""Upload all event families for one batch and publish its final ready marker."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--ingest-date", required=True)
    parser.add_argument("--region", default="ap-southeast-2")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    common = [
        "--input-dir", args.input_dir,
        "--bucket", args.bucket,
        "--batch-id", args.batch_id,
        "--ingest-date", args.ingest_date,
        "--region", args.region,
    ]
    for script in ("land_synthetic_batch.py", "land_secondary_events.py"):
        subprocess.run(
            [sys.executable, str(repo_root / "scripts" / script), *common],
            cwd=repo_root,
            check=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
