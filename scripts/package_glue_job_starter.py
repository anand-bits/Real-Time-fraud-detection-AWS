"""Package the standard-library-only Glue starter Lambda for Terraform."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "src/lambda/glue_job_starter/handler.py"
    output = root / "infra/terraform/glue_job_starter.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(source, arcname="handler.py")
    print(f"Packaged {source} -> {output}")


if __name__ == "__main__":
    main()
