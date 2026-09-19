"""Generate separate contracts for each installed feature without sibling imports."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.timeline.application import create_demo_app
from app.timeline.composition import installed_features
from app.timeline.contracts import ErrorResponse, EventEnvelope, Receipt
from pydantic.json_schema import models_json_schema


def build_contracts() -> dict[Path, dict[str, Any]]:
    """Return per-feature OpenAPI and reusable schemas for installed feature modules."""
    documents: dict[Path, dict[str, Any]] = {}
    for feature in installed_features():
        models = feature.public_models() + [ErrorResponse, Receipt, EventEnvelope]
        _, schema = models_json_schema(
            [(model, "validation") for model in models],
            title=f"Lumina {feature.KEY} contracts",
        )
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:lumina:{feature.KEY}:1.0.0"
        documents[ROOT / f"shared/contracts/{feature.KEY}.schema.json"] = schema
        documents[ROOT / f"docs/api/{feature.KEY}.openapi.json"] = create_demo_app(
            (feature.KEY,)
        ).openapi()
        if feature.KEY == "signal_timeline":
            template = json.loads(
                (ROOT / "backend/app/signals/asyncapi_template.json").read_text()
            )
            documents[ROOT / "docs/api/signal_timeline.asyncapi.json"] = template
    return documents


def main() -> int:
    """Write snapshots, or fail check mode when a checked-in snapshot is stale."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = False
    for path, document in build_contracts().items():
        content = json.dumps(document, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != content:
                print(f"Stale contract: {path.name}")
                stale = True
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if not stale:
        print("Installed feature contracts are current.")
    return int(stale)


if __name__ == "__main__":
    raise SystemExit(main())
