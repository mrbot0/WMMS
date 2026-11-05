"""Writes docs/openapi.json from the route table (2.11). Run it after adding or changing a route:

    python tools/build_docs.py

tests/test_v211.py fails when docs/openapi.json is out of date."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "openapi.json"


def render() -> str:
    from wmm.server import openapi
    return json.dumps(openapi.document(), indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    OUT.write_text(render(), encoding="utf-8")
    print(f"Written {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
