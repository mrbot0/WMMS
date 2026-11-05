"""A second PC for tests/test_v28.py, in its own process: a sharing PC with its own data folder, key and port, that
allows reports and safe fixes and runs nothing for real (the jobs are recorded and answered at once). It prints one
JSON line {"port", "key"} and serves until its standard input is closed."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wmm.agent import fleet  # noqa: E402


def main() -> None:
    cartella = Path(sys.argv[1])
    condivisione = fleet.Fleet(cartella / "fleet.json")
    chiave = condivisione.new_key()
    condivisione.set_share(True, 8766, "safe")
    lavori = {}

    def avvia(ids):
        job = f"{len(lavori) + 1:032x}"
        lavori[job] = {"id": job, "active": False, "done": len(ids), "total": len(ids),
                       "results": [{"action_id": a, "status": "ok", "note": "peer", "verify": {"label": "x", "before": "1", "after": "0", "verdict": "fixed"}}
                                   for a in ids]}
        return job

    server = fleet.summary_server(condivisione, 0, lambda: {"hostname": "PEER", "version": "2.8.0", "overall": 77, "scores": {"cleanup": 80}},
                                  {"start": avvia, "status": lambda job: lavori[job]})
    print(json.dumps({"port": server.server_address[1], "key": chiave}), flush=True)
    sys.stdin.read()
    server.shutdown()


if __name__ == "__main__":
    main()
