"""Write the API's OpenAPI schema to a file (#21).

FastAPI already knows every response shape. Committing that schema turns it
into the frontend's source of truth instead of something a human re-types into
`types.ts` and keeps in sync by memory.

    uv run python scripts/dump_openapi.py

The output is committed. CI regenerates it and fails if it differs, so a
response-model change that nobody propagated shows up as a failing build rather
than as a runtime `undefined` on a screen.
"""

from __future__ import annotations

import json
import pathlib
import sys

# Importing the app is what produces the schema, so this runs the same startup
# checks the server does.
from app.main import app

OUTPUT = pathlib.Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> int:
    schema = app.openapi()
    # sort_keys so the committed file is stable across runs — otherwise the
    # drift check would fail on dictionary ordering rather than on real change.
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
