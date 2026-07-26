"""One-off analyzer for taskbar_trace.csv"""
from pathlib import Path
import csv
from collections import Counter

path = Path(__file__).resolve().parent.parent / "taskbar_trace.csv"
text = path.read_text(encoding="utf-8", errors="replace").splitlines()
rows_raw = [ln for ln in text if ln.strip() and not ln.startswith("#")]
print("header", rows_raw[0])
print("data lines", len(rows_raw) - 1)
print("sessions", sum(1 for ln in text if ln.startswith("# session")))

reader = csv.DictReader(rows_raw)
rows = list(reader)
print("parsed", len(rows))
print("events", Counter(r["event"] for r in rows))


def fnum(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except Exception:
        return None


for r in rows:
    r["_mono"] = fnum(r.get("mono_ms"))
    r["_real"] = fnum(r.get("real_top"))
    r["_follow"] = fnum(r.get("follow_top"))
    r["_gap"] = fnum(r.get("gap"))
    r["_real_d"] = fnum(r.get("real_d"))
    r["_follow_d"] = fnum(r.get("follow_d"))
    r["_pet_bottom"] = fnum(r.get("pet_bottom"))
    r["_dwm"] = fnum(r.get("dwm_top"))
    r["_gwr"] = fnum(r.get("gwr_top"))
    r["_abm"] = fnum(r.get("abm_top"))
    r["_glide"] = r.get("glide") == "1"

bursts = []
cur = []
for r in rows:
    if not cur:
        cur = [r]
        continue
    dt = (r["_mono"] or 0) - (cur[-1]["_mono"] or 0)
    if dt > 500:
        bursts.append(cur)
        cur = [r]
    else:
        cur.append(r)
if cur:
    bursts.append(cur)

print("\nbursts", len(bursts))
sig = []
for i, b in enumerate(bursts):
    reals = [r["_real"] for r in b if r["_real"] is not None]
    if not reals:
        continue
    real_span = max(reals) - min(reals)
    if real_span < 5 and not any(r["event"] == "snap" for r in b):
        continue
    sig.append((i, b, real_span))

print("significant bursts", len(sig))

for i, b, span in sig[:20]:
    t0 = b[0]["_mono"]
    t1 = b[-1]["_mono"]
    dur = (t1 - t0) if t0 is not None and t1 is not None else 0
    reals = [r["_real"] for r in b if r["_real"] is not None]
    follows = [r["_follow"] for r in b if r["_follow"] is not None]
    gaps = [r["_gap"] for r in b if r["_gap"] is not None]
    real_ds = [r["_real_d"] for r in b if r["_real_d"] is not None]
    follow_ds = [r["_follow_d"] for r in b if r["_follow_d"] is not None]
    events = Counter(r["event"] for r in b)

    direction = "up" if reals[-1] < reals[0] else ("down" if reals[-1] > reals[0] else "flat")
    final_real = reals[-1]
    last_real_change = 0
    for j in range(1, len(b)):
        if b[j]["_real"] != b[j - 1]["_real"]:
            last_real_change = j
    follow_reach = next(
        (
            j
            for j, r in enumerate(b)
            if r["_follow"] is not None and abs(r["_follow"] - final_real) < 0.5
        ),
        None,
    )

    max_gap = max(gaps) if gaps else None
    min_gap = min(gaps) if gaps else None
    max_abs_gap = max(abs(g) for g in gaps) if gaps else None
    max_real_d = max(real_ds, key=lambda x: abs(x)) if real_ds else None
    max_follow_d = max(follow_ds, key=lambda x: abs(x)) if follow_ds else None

    t_tray_end = b[last_real_change]["_mono"] - t0 if t0 is not None else None
    t_follow_end = (b[follow_reach]["_mono"] - t0) if follow_reach is not None and t0 is not None else None
    lag_after_tray = None
    if t_tray_end is not None and t_follow_end is not None:
        lag_after_tray = t_follow_end - t_tray_end

    print(
        f"\n=== burst#{i} n={len(b)} dur={dur:.0f}ms dir={direction} "
        f"real_span={span:.0f} events={dict(events)}"
    )
    print(
        f"  real {reals[0]:.0f} -> {reals[-1]:.0f}  "
        f"follow {follows[0]:.0f} -> {follows[-1]:.0f}"
    )
    print(f"  gap range [{min_gap}, {max_gap}] max_abs={max_abs_gap}")
    print(f"  max real_d={max_real_d} max follow_d={max_follow_d}")
    print(
        f"  tray_motion_end ~{t_tray_end:.0f}ms  follow_reach_final ~{t_follow_end}ms  "
        f"lag_after_tray={lag_after_tray}"
    )

    def show(r):
        return (
            f"    +{r['_mono'] - t0:6.0f}ms {r['event']:12s} "
            f"real={r['_real']} follow={r['_follow']} gap={r['_gap']} "
            f"rd={r['_real_d']} fd={r['_follow_d']} glide={r['glide']} "
            f"gt={r.get('glide_t', '')} gdur={r.get('glide_dur_ms', '')}"
        )

    print("  head:")
    for r in b[:8]:
        print(show(r))
    if gaps:
        jmax = max(range(len(b)), key=lambda j: abs(b[j]["_gap"] or 0))
        print(f"  max|gap| at +{b[jmax]['_mono'] - t0:.0f}ms:")
        print(show(b[jmax]))
    # sample mid
    mid = len(b) // 2
    print("  mid:")
    for r in b[max(0, mid - 2) : mid + 3]:
        print(show(r))
    print("  tail:")
    for r in b[-5:]:
        print(show(r))

rds = [r["_real_d"] for r in rows if r["_real_d"]]
fds = [r["_follow_d"] for r in rows if r["_follow_d"]]
print("\n=== real_d non-zero stats ===")
if rds:
    absrds = sorted(abs(x) for x in rds)
    print(
        f"count={len(rds)} max={max(absrds)} median={absrds[len(absrds) // 2]} "
        f"p90={absrds[int(len(absrds) * 0.9)]}"
    )
    big = [x for x in rds if abs(x) >= 20]
    print(f"|real_d|>=20 count={len(big)} values={big[:30]}")
print("=== follow_d non-zero stats ===")
if fds:
    absfds = sorted(abs(x) for x in fds)
    print(f"count={len(fds)} max={max(absfds)} median={absfds[len(absfds) // 2]}")

mismatch = sum(
    1
    for r in rows
    if r["_dwm"] is not None and r["_gwr"] is not None and r["_dwm"] != r["_gwr"]
)
print(f"\ndwm!=gwr rows: {mismatch}/{len(rows)}")
abm_diff = [
    (r["_real"] - r["_abm"])
    for r in rows
    if r["_real"] is not None and r["_abm"] is not None
]
if abm_diff:
    print(f"real-abm: min={min(abm_diff)} max={max(abm_diff)}")
