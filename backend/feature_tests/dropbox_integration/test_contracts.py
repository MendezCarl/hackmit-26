"""Independent feature contracts, route isolation and original baseline compatibility."""

import json

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from scripts.generate_feature_contracts import build_contracts


def test_contract_snapshots() -> None:
    """All feature schema/OpenAPI snapshots must match the installed implementation."""
    for path, document in build_contracts().items():
        assert path.read_text() == json.dumps(document, indent=2, sort_keys=True) + "\n"
        if path.name.endswith(".schema.json"):
            Draft202012Validator.check_schema(document)


def test_only_assigned_feature_routes(client: TestClient) -> None:
    """The checkout must not expose either sibling feature's business endpoints."""
    paths = client.get("/openapi.json").json()["paths"]
    base = "/api/v1/sessions/{session_id}"
    assert (base + "/signals" in paths) is False
    assert (base + "/professor-summary" in paths) is False
    assert (base + "/dropbox/folder" in paths) is True
    for route in ("/health", "/docs", "/redoc"):
        assert client.get(route).status_code == 200
