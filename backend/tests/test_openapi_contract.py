"""Tests that keep the checked-in OpenAPI contract synchronized."""

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.generate_openapi_contract import is_openapi_contract_current  # noqa: E402


def test_openapi_contract_is_current() -> None:
    """Require API and route-model changes to regenerate the OpenAPI snapshot."""

    assert is_openapi_contract_current(), (
        "docs/api/openapi.json is stale; run "
        "`python backend/scripts/generate_openapi_contract.py`."
    )
