"""Core logic checks: session merge, drop-short, crash recovery, totals. Run: python test_core.py"""
import tempfile
from pathlib import Path

from tracker import SESSIONS_TXT, TOTALS_TXT, Tracker

T0 = 1_700_000_000.0


def make(d):
    app, out = Path(d) / "app", Path(d) / "out"
    app.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    return Tracker(app, out), app, out


def run(tr, start, end, names):
    t = start
    while t <= end:
        tr.tick(t, names)
        t += 15
    return end


def lines(out):
    p = out / SESSIONS_TXT
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def test_merge_and_totals():
    with tempfile.TemporaryDirectory() as d:
        tr, app, out = make(d)
        t = run(tr, T0, T0 + 600, {"Valorant"})            # 10 min
        t = run(tr, t + 15, t + 240, set())                # 4 min gap (< 5): merge
        t = run(tr, t + 15, t + 615, {"Valorant"})         # 10 more min
        run(tr, t + 15, t + 400, set())                    # gap > 5 min: finalize
        got = lines(out)
        assert len(got) == 1, got
        assert got[0].endswith("| Valorant | 20m"), got
        tot = (out / TOTALS_TXT).read_text(encoding="utf-8").splitlines()
        assert tot[0].startswith("Grand total: 20m"), tot
        assert tot[1].startswith("Valorant - 20m | sessions: 1 | first: "), tot


def test_short_dropped_and_sorted_totals():
    with tempfile.TemporaryDirectory() as d:
        tr, app, out = make(d)
        t = run(tr, T0, T0 + 60, {"Blip"})                 # < 2 min: dropped
        t = run(tr, t + 15, t + 400, set())
        t = run(tr, t + 15, t + 915, {"Small"})            # 15 min
        t = run(tr, t + 15, t + 400, set())
        t = run(tr, t + 15, t + 3615, {"Big"})             # 60 min
        run(tr, t + 15, t + 400, set())
        assert len(lines(out)) == 2, lines(out)
        tot = (out / TOTALS_TXT).read_text(encoding="utf-8").splitlines()
        assert tot[1].startswith("Big - 1h 0m") and tot[2].startswith("Small - 15m"), tot


def test_crash_recovery():
    with tempfile.TemporaryDirectory() as d:
        tr, app, out = make(d)
        run(tr, T0, T0 + 1200, {"Valorant"})               # 20 min, then "crash"
        tr.save_state()
        assert lines(out) == []
        tr2 = Tracker(app, out)                            # restart after crash
        got = lines(out)
        assert len(got) == 1 and got[0].endswith("| Valorant | 20m"), got
        assert Tracker(app, out).sessions == {} and len(lines(out)) == 1  # not logged twice


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
