"""Type check with a ratchet (2.11): mypy runs on the whole package, and CI fails when a file has more type errors
than tools/mypy_baseline.json allows. Files at 0 must stay at 0; old debt can only go down.

    python tools/typecheck.py            check against the baseline
    python tools/typecheck.py --update   write the current counts as the new baseline (only after fixing errors)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tools" / "mypy_baseline.json"


def counts() -> Counter:
    uscita = subprocess.run([sys.executable, "-m", "mypy", "wmm", "--ignore-missing-imports", "--no-error-summary"],
                            cwd=ROOT, capture_output=True, text=True).stdout
    conta: Counter = Counter()
    for riga in uscita.splitlines():
        m = re.match(r"^(wmm[^:]+\.py):\d+: error:", riga)
        if m:
            conta[m.group(1).replace("\\", "/")] += 1
    return conta


def main() -> int:
    attuali = counts()
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps(dict(sorted(attuali.items())), indent=1) + "\n", encoding="utf-8")
        print(f"Baseline written: {sum(attuali.values())} errors in {len(attuali)} files.")
        return 0
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    peggiori = {f: (n, base.get(f, 0)) for f, n in attuali.items() if n > base.get(f, 0)}
    for f, (n, b) in sorted(peggiori.items()):
        print(f"{f}: {n} type errors (allowed {b})")
    meglio = sum(base.values()) - sum(attuali.values())
    if peggiori:
        print("New type errors: run  python -m mypy wmm --ignore-missing-imports  and fix them.")
        return 1
    print(f"Type check OK: {sum(attuali.values())} known errors" + (f", {meglio} fewer than the baseline (run --update)" if meglio > 0 else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
