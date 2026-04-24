import json
import pathlib
import numpy as np

PROJECT_DIR = pathlib.Path(__file__).parent
LOG_DIR = PROJECT_DIR / "LOG"
SL_DIR = LOG_DIR / "SINGLE_LANE"
DL_DIR = LOG_DIR / "DOUBLE_LANE"
TL_DIR = LOG_DIR / "TRIPLE_LANE"
QL_DIR = LOG_DIR / "QUAD_LANE"

RING_C = 791.0
SLOW_THRESH = 5.0          # m/s
EQUILIBRIUM = 9.1          # m/s, initial flow speed
PERTURBER_ID = 201
PERT_START, PERT_END = 30.0, 35.0
RECOVERY_BAND = 0.5        # m/s tolerance around equilibrium speed
RATES = ["0%", "10%", "20%", "30%", "40%", "50%", "60%", "70%", "80%", "90%", "100%"]

N_SEEDS = 3
SEED_SUBDIRS = [f"seed_{i}" for i in range(N_SEEDS)]

LANE_CONFIGS = [
    ("SL", 1, SL_DIR, "SINGLE LANE"),
    ("DL", 2, DL_DIR, "DOUBLE LANE"),
    ("TL", 3, TL_DIR, "TRIPLE LANE"),
    ("QL", 4, QL_DIR, "QUAD LANE"),
]


def load_one(label, dir_, n_lanes, seed_sub):
    pct = label.replace("%", "pct")
    if n_lanes == 1:
        candidates = [
            dir_ / seed_sub / f"phantom_jam_{pct}.json",
            dir_ / seed_sub / f"phantom_jam_1lane_{pct}.json",
        ]
    else:
        candidates = [dir_ / seed_sub / f"phantom_jam_{n_lanes}lane_{pct}.json"]
    for fn in candidates:
        if fn.exists():
            with open(fn) as f:
                return json.load(f)
    raise FileNotFoundError(f"No log for {label} seed={seed_sub} in {dir_}")


def load_multi_seed(label, dir_, n_lanes):
    return [load_one(label, dir_, n_lanes, s) for s in SEED_SUBDIRS]


def frame_metrics(log, exclude_perturber=False):
    ts, mean_v, std_v, frac_slow, min_v = [], [], [], [], []
    for fr in log["frames"]:
        speeds = np.array([
            v["speed"] for v in fr["vehicles"]
            if not (exclude_perturber and v["id"] == PERTURBER_ID)
        ])
        ts.append(fr["t"])
        mean_v.append(speeds.mean())
        std_v.append(speeds.std())
        frac_slow.append((speeds < SLOW_THRESH).mean())
        min_v.append(speeds.min())
    return (np.array(ts), np.array(mean_v), np.array(std_v),
            np.array(frac_slow), np.array(min_v))


def recovery_time(t, mean_v, target=EQUILIBRIUM, band=RECOVERY_BAND):
    post = t >= PERT_END
    if not post.any():
        return None
    t_post = t[post]
    v_post = mean_v[post]
    inside = np.abs(v_post - target) <= band
    win = 20
    for i in range(len(inside) - win):
        if inside[i:i + win].all():
            return float(t_post[i])
    return None


def jam_wave_speed(log):
    pts_t, pts_x = [], []
    for fr in log["frames"]:
        if fr["t"] < PERT_START or fr["t"] > PERT_START + 200:
            continue
        for v in fr["vehicles"]:
            if v["id"] == PERTURBER_ID:
                continue
            if v["speed"] < SLOW_THRESH:
                pts_t.append(fr["t"])
                pts_x.append(v["u"] % RING_C)
    if len(pts_t) < 30:
        return None
    pts_t = np.array(pts_t)
    pts_x = np.array(pts_x)
    bins = np.linspace(0, RING_C, 40)
    idx = np.digitize(pts_x, bins)
    edge_t, edge_x = [], []
    for b in range(1, len(bins)):
        mask = idx == b
        if mask.sum() >= 2:
            edge_t.append(pts_t[mask].min())
            edge_x.append(pts_x[mask].mean())
    if len(edge_t) < 5:
        return None
    slope, _ = np.polyfit(np.array(edge_t), np.array(edge_x), 1)
    return float(slope)


def summarize_one(label, log):
    t, mean_v, std_v, frac_slow, min_v = frame_metrics(log, exclude_perturber=True)
    post = t >= PERT_END
    pert = (t >= PERT_START) & (t <= PERT_START + 60)
    return {
        "label": label,
        "mean_speed_post": float(mean_v[post].mean()),
        "std_post":        float(std_v[post].mean()),
        "frac_slow_post":  float(frac_slow[post].mean()),
        "min_mean_speed":  float(mean_v[pert].min()),
        "max_std":         float(std_v[pert].max()),
        "max_frac_slow":   float(frac_slow[pert].max()),
        "min_indiv_speed": float(min_v[pert].min()),
        "recovery_t":      recovery_time(t, mean_v),
        "wave_speed":      jam_wave_speed(log),
        "duration":        float(t.max()),
        "n_frames":        len(t),
    }


def average_summaries(summaries: list[dict]) -> dict:
    result = {"label": summaries[0]["label"]}
    scalar_keys = [k for k in summaries[0] if k != "label"]
    for k in scalar_keys:
        vals = [s[k] for s in summaries if s[k] is not None]
        result[k]         = float(np.mean(vals)) if vals else None
        result[k + "_sd"] = float(np.std(vals))  if vals else None
    return result


def summarize(label, logs):
    sums = [summarize_one(label, log) for log in logs]
    return average_summaries(sums)


def fmt(v, nd=3):
    if v is None:
        return "  n/a "
    return f"{v:>7.{nd}f}"


def print_table(rows, title):
    print(f"\n=== {title} ===")
    hdr = ("Pen%   meanV_post  stdV_post  fracSlow  minMeanV  maxStd"
           "  maxFracSlow  minIndivV  recovery_t  waveSpeed_m/s")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['label']:>4}   "
              f"{fmt(r['mean_speed_post'])}    "
              f"{fmt(r['std_post'])}   "
              f"{fmt(r['frac_slow_post'])}  "
              f"{fmt(r['min_mean_speed'])}  "
              f"{fmt(r['max_std'])}  "
              f"{fmt(r['max_frac_slow'])}     "
              f"{fmt(r['min_indiv_speed'])}  "
              f"{fmt(r['recovery_t'], 1)}    "
              f"{fmt(r['wave_speed'])}")


def critical_threshold(rows, metric_key, target_frac=0.5, baseline_idx=0):
    base = rows[baseline_idx][metric_key]
    full = rows[-1][metric_key]
    if base is None or full is None or base == full:
        return None
    gap = base - full
    for r in rows:
        if r[metric_key] is not None and (base - r[metric_key]) / gap >= target_frac:
            return r["label"]
    return None


def main():
    all_logs = {}
    all_rows = {}
    for key, n_lanes, dir_, title in LANE_CONFIGS:
        logs = {l: load_multi_seed(l, dir_, n_lanes) for l in RATES}
        all_logs[key] = logs
        all_rows[key] = [summarize(l, logs[l]) for l in RATES]
        print_table(all_rows[key], f"{title} — mean over {N_SEEDS} seeds (perturber excluded)")

    print("\n=== CRITICAL PENETRATION THRESHOLDS ===")
    for key, target, label in [
        ("frac_slow_post", 0.5, "50% jam reduction (post)"),
        ("frac_slow_post", 0.9, "90% jam reduction (post)"),
        ("std_post",       0.5, "50% std-dev reduction (post)"),
        ("max_std",        0.5, "50% peak-std reduction"),
    ]:
        sl_t = critical_threshold(all_rows["SL"], key, target)
        dl_t = critical_threshold(all_rows["DL"], key, target)
        tl_t = critical_threshold(all_rows["TL"], key, target)
        ql_t = critical_threshold(all_rows["QL"], key, target)
        print(f"  {label:<35}  SL={sl_t}   DL={dl_t}   TL={tl_t}   QL={ql_t}")

    print("\n=== HEADLINE COMPARISONS (multi-lane vs single-lane baseline) ===")
    hdr = ("Pen%   dV_DL   dV_TL   dV_QL     dStd_DL  dStd_TL  dStd_QL    "
           "dJam_DL  dJam_TL  dJam_QL")
    print(hdr)
    print("-" * len(hdr))
    for i, pct in enumerate(RATES):
        sl = all_rows["SL"][i]
        dl = all_rows["DL"][i]
        tl = all_rows["TL"][i]
        ql = all_rows["QL"][i]
        dV_d = dl["mean_speed_post"] - sl["mean_speed_post"]
        dV_t = tl["mean_speed_post"] - sl["mean_speed_post"]
        dV_q = ql["mean_speed_post"] - sl["mean_speed_post"]
        dS_d = sl["std_post"] - dl["std_post"]
        dS_t = sl["std_post"] - tl["std_post"]
        dS_q = sl["std_post"] - ql["std_post"]
        dJ_d = (sl["frac_slow_post"] - dl["frac_slow_post"]) * 100
        dJ_t = (sl["frac_slow_post"] - tl["frac_slow_post"]) * 100
        dJ_q = (sl["frac_slow_post"] - ql["frac_slow_post"]) * 100
        print(f"  {pct:>4}   {dV_d:+6.2f}  {dV_t:+6.2f}  {dV_q:+6.2f}    "
              f"{dS_d:+6.2f}   {dS_t:+6.2f}   {dS_q:+6.2f}    "
              f"{dJ_d:+6.2f}   {dJ_t:+6.2f}   {dJ_q:+6.2f}")

    print("\n=== ABSOLUTE TABLE (all lane configs) ===")
    hdr2 = ("Pen%   meanV_SL  meanV_DL  meanV_TL  meanV_QL   "
            "std_SL  std_DL  std_TL  std_QL   "
            "jam_SL  jam_DL  jam_TL  jam_QL")
    print(hdr2)
    print("-" * len(hdr2))
    for i, pct in enumerate(RATES):
        sl = all_rows["SL"][i]; dl = all_rows["DL"][i]
        tl = all_rows["TL"][i]; ql = all_rows["QL"][i]
        print(f"  {pct:>4}   "
              f"{sl['mean_speed_post']:7.3f}  {dl['mean_speed_post']:7.3f}  "
              f"{tl['mean_speed_post']:7.3f}  {ql['mean_speed_post']:7.3f}   "
              f"{sl['std_post']:5.2f}  {dl['std_post']:5.2f}  "
              f"{tl['std_post']:5.2f}  {ql['std_post']:5.2f}   "
              f"{sl['frac_slow_post']:5.3f}  {dl['frac_slow_post']:5.3f}  "
              f"{tl['frac_slow_post']:5.3f}  {ql['frac_slow_post']:5.3f}")

    print("\n=== META ===")
    print(f"  ring circumference     : {RING_C} m")
    print(f"  equilibrium speed      : {EQUILIBRIUM} m/s  ({EQUILIBRIUM*3.6:.1f} km/h)")
    print(f"  slow threshold         : {SLOW_THRESH} m/s  ({SLOW_THRESH*3.6:.0f} km/h)")
    print(f"  perturbation window    : {PERT_START}–{PERT_END} s")
    print(f"  recovery band          : +/-{RECOVERY_BAND} m/s for >=20 s")
    print(f"  seed runs              : {N_SEEDS} (seeds 0, 1, 2)")
    print(f"  vehicles per lane      : 35 (34 background + 1 perturber in lane 0)")
    print(f"  total vehicles by cfg  : SL=35, DL=70, TL=105, QL=140")
    print(f"  density               : {35/RING_C*1000:.1f} veh/km per lane")


if __name__ == "__main__":
    main()
