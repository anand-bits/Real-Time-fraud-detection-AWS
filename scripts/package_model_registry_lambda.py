#!/usr/bin/env python3
"""Package the lightweight SageMaker model-registry gate Lambda for Terraform."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/lambda/model_registry/handler.py"
OUTPUT = ROOT / "infra/terraform/model_registry_lambda.zip"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(SOURCE, "handler.py")
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
