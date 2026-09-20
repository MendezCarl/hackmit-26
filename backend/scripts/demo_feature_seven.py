"""Show the Feature 7 endpoint in process, or against a running local demo server."""

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.demo.runner import DemoRunResult
from app.main import create_app
from fastapi.testclient import TestClient


def run_demo(url: str | None = None) -> dict[str, object]:
    """Call the demo endpoint and return compact judge-facing evidence.

    Args:
        url: Optional HTTP server base URL. Omit for an isolated ASGI run.

    Returns:
        Synthetic card content, aggregate evidence and labeled comparison.

    Raises:
        RuntimeError: If the in-process endpoint does not return success.
        OSError: If the supplied server cannot be reached.
        ValueError: If the response violates the demo contract.
    """
    if url:
        request = Request(
            url.rstrip("/") + "/api/v1/demo/runs",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            result = DemoRunResult.model_validate_json(response.read())
    else:
        with TestClient(
            create_app(Settings(app_env="demo", provider_mode="mock"))
        ) as client:
            response = client.post("/api/v1/demo/runs", json={})
            if response.status_code != 201:
                raise RuntimeError("The synthetic demo endpoint did not complete.")
            result = DemoRunResult.model_validate_json(response.content)
    return {
        "mode": "synthetic_only",
        "missed_interval_ms": [
            result.recovery_job.requested_start_ms,
            result.recovery_job.requested_end_ms,
        ],
        "recovery_card": result.recovery_card.model_dump(
            mode="json",
            include={
                "topic",
                "what_you_missed",
                "key_facts",
                "source_timestamps",
                "follow_up_question",
            },
        ),
        "cache_status": result.cached_recovery_job.cache_status,
        "professor_status": result.professor_metrics.status,
        "professor_hotspots": [
            bucket.model_dump(mode="json")
            for bucket in result.professor_metrics.buckets
            if bucket.is_hotspot
        ],
        "small_group_status": result.professor_metrics_suppressed.status,
        "token_cost_comparison": result.token_cost_comparison.model_dump(mode="json"),
    }


def main() -> int:
    """Print the compact scenario as JSON; failures exit nonzero without provider details."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", help="Optional running demo server, e.g. http://127.0.0.1:8000"
    )
    args = parser.parse_args()
    try:
        print(json.dumps(run_demo(args.url), indent=2))
    except OSError, ValueError, RuntimeError:
        print(
            "Demo failed. Check the server URL, APP_ENV=demo and the response contract.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
