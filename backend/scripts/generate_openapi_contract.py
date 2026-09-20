"""Generate or verify the checked-in OpenAPI contract from FastAPI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
OPENAPI_OUTPUT_PATH = REPOSITORY_ROOT / "docs" / "api" / "openapi.json"

# Allow this script to run from either the repository root or backend directory.
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # Import after adding backend to sys.path.


def build_openapi_contract() -> str:
    """Serialize FastAPI's current OpenAPI schema deterministically.

    Returns:
        The formatted OpenAPI JSON document with a trailing newline.
    """

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def write_openapi_contract(output_path: Path = OPENAPI_OUTPUT_PATH) -> None:
    """Write the generated OpenAPI contract to the repository documentation.

    Args:
        output_path: Destination for the generated OpenAPI JSON document.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_openapi_contract(), encoding="utf-8")


def is_openapi_contract_current(output_path: Path = OPENAPI_OUTPUT_PATH) -> bool:
    """Check whether the committed OpenAPI snapshot matches the live app schema.

    Args:
        output_path: Existing OpenAPI JSON snapshot to compare.

    Returns:
        ``True`` when the snapshot exists and exactly matches the generated schema.
    """

    if not output_path.exists():
        return False
    return output_path.read_text(encoding="utf-8") == build_openapi_contract()


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options for generation or verification.

    Returns:
        Parsed arguments containing the ``check`` mode flag.
    """

    parser = argparse.ArgumentParser(
        description="Generate or verify docs/api/openapi.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit unsuccessfully instead of writing when the snapshot is stale.",
    )
    return parser.parse_args()


def main() -> int:
    """Generate the snapshot or verify that it is current.

    Returns:
        Process exit code: zero on success and one for a stale snapshot.
    """

    arguments = parse_arguments()
    if arguments.check:
        if is_openapi_contract_current():
            print(f"OpenAPI contract is current: {OPENAPI_OUTPUT_PATH}")
            return 0
        print(
            "OpenAPI contract is stale. Run "
            "`python backend/scripts/generate_openapi_contract.py`.",
            file=sys.stderr,
        )
        return 1

    write_openapi_contract()
    print(f"Generated OpenAPI contract: {OPENAPI_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
