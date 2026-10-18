"""Export the API contract without connecting to a database or a market provider."""

import json
from pathlib import Path

from cyclescope.api.app import create_app
from cyclescope.config import Settings
from cyclescope.providers.synthetic import SyntheticProvider

if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "frontend/openapi.json"
    target.write_text(
        json.dumps(
            create_app(settings=Settings(), provider=SyntheticProvider()).openapi(),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"Exported {target.name}")
