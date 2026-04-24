import json
import pathlib
import shutil
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

PROJECT_DIR = pathlib.Path(__file__).parent
LOG_DIR = PROJECT_DIR / "LOG"
FIGURES_DIR = LOG_DIR / "phantom_figures"
RESULTS_DIR = PROJECT_DIR.parent / "report" / "Results"

LOG_SINGLE_LANE_DIR = LOG_DIR / "SINGLE_LANE"
LOG_DOUBLE_LANE_DIR = LOG_DIR / "DOUBLE_LANE"
LOG_TRIPLE_LANE_DIR = LOG_DIR / "TRIPLE_LANE"
LOG_QUAD_LANE_DIR   = LOG_DIR / "QUAD_LANE"

RING_CIRCUMFERENCE = 791.0
M_PER_S_TO_KMH = 3.6
SLOW_THRESHOLD = 18.0  # km/h  (5 m/s)
PERTURBER_ID = 201

N_SEEDS = 3
SEED_SUBDIRS = [f"seed_{i}" for i in range(N_SEEDS)]

PENETRATION_RATES = [
    "0%", "10%", "20%", "30%", "40%", "50%", "60%", "70%", "80%", "90%", "100%"
]
GRID_RATES = ["0%", "20%", "40%", "60%", "80%", "100%"]

plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "legend.fontsize": 10,
    "figure.titlesize": 14
})

SPEED_CMAP = LinearSegmentedColormap.from_list(
    "traffic", ["#CC0000", "#FF6600", "#FFAA00", "#00CC44"], N=256
)


def load_log(filename: str, subdir: pathlib.Path) -> dict:
    filepath = subdir / filename
    with open(filepath) as f:
        return json.load(f)

def load_logs_multi_seed(label: str, log_dir: pathlib.Path) -> list[dict]:
    pct = label.replace("%", "pct")
    logs = []
    for seed_sub in SEED_SUBDIRS:
        candidates = [
            log_dir / seed_sub / f"phantom_jam_{pct}.json",
            log_dir / seed_sub / f"phantom_jam_1lane_{pct}.json",
            log_dir / seed_sub / f"phantom_jam_2lane_{pct}.json",
            log_dir / seed_sub / f"phantom_jam_3lane_{pct}.json",
            log_dir / seed_sub / f"phantom_jam_4lane_{pct}.json",
        ]
        loaded = False
        for c in candidates:
            if c.exists():
                with open(c) as f:
                    logs.append(json.load(f))
                loaded = True
                break
        if not loaded:
            raise FileNotFoundError(
                f"No log found for label={label} in {log_dir / seed_sub}"
            )
    return logs

def extract_trajectory_data_multi(logs: list[dict], stride: int = 1):
    t_all, x_all, v_all = [], [], []
    for log in logs:
        for frame in log["frames"][::stride]:
            t = frame["t"]
            for veh in frame["vehicles"]:
                t_all.append(t)
                x_all.append(veh["u"] % RING_CIRCUMFERENCE)
                v_all.append(veh["speed"] * M_PER_S_TO_KMH)
    return np.array(t_all), np.array(x_all), np.array(v_all)


def compute_frame_metrics(log: dict):
    frames = log["frames"]
    t_list, mean_v, std_v, frac_slow = [], [], [], []
    for frame in frames:
        speeds = np.array([v["speed"] * M_PER_S_TO_KMH for v in frame["vehicles"]])
        t_list.append(frame["t"])
        mean_v.append(np.mean(speeds))
        std_v.append(np.std(speeds))
        frac_slow.append(np.mean(speeds < SLOW_THRESHOLD))
    return np.array(t_list), np.array(mean_v), np.array(std_v), np.array(frac_slow)

def compute_frame_metrics_averaged(logs: list[dict]):
    all_t, all_mean, all_std, all_frac = [], [], [], []
    for log in logs:
        t, m, s, f = compute_frame_metrics(log)
        all_t.append(t)
        all_mean.append(m)
        all_std.append(s)
        all_frac.append(f)

    t_ref = all_t[0]
    mean_avg   = np.mean(all_mean, axis=0)
    mean_sigma = np.std(all_mean,  axis=0)
    std_avg    = np.mean(all_std,  axis=0)
    std_sigma  = np.std(all_std,   axis=0)
    frac_avg   = np.mean(all_frac, axis=0)
    frac_sigma = np.std(all_frac,  axis=0)

    return t_ref, mean_avg, mean_sigma, std_avg, std_sigma, frac_avg, frac_sigma

def _perturber_segments(log: dict, stride: int = 2):
    segments = []
    t_p, x_p = [], []
    for frame in log["frames"][::stride]:
        t = frame["t"]
        for veh in frame["vehicles"]:
            if veh["id"] == PERTURBER_ID:
                x = veh["u"] % RING_CIRCUMFERENCE
                if len(x_p) > 0 and abs(x - x_p[-1]) > RING_CIRCUMFERENCE / 2:
                    segments.append((list(t_p), list(x_p)))
                    t_p, x_p = [t], [x]
                else:
                    t_p.append(t)
                    x_p.append(x)
    if t_p:
        segments.append((t_p, x_p))
    return segments

def fig_trajectory_grid(logs_multi: dict, title_suffix: str = ""):
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), sharex=True, sharey=True)
    axes = axes.flatten()

    im = None
    for idx, label in enumerate(GRID_RATES):
        ax = axes[idx]
        logs = logs_multi[label]
        t_vals, x_vals, v_vals = extract_trajectory_data_multi(logs, stride=2)
        im = ax.scatter(t_vals, x_vals, c=v_vals, cmap=SPEED_CMAP,
                        s=0.8, vmin=0, vmax=72, alpha=0.6, edgecolors="none")
        ax.axvspan(30, 35, color="grey", alpha=0.3, zorder=0)

        for t_seg, x_seg in _perturber_segments(logs[0]):
            ax.plot(t_seg, x_seg, "k--", linewidth=1.5, alpha=0.7)

        if idx == 0:
            ax.plot([], [], "k--", linewidth=1.5, label="Perturber")

        if idx >= 3:
            ax.set_xlabel("Time (s)")
        if idx % 3 == 0:
            ax.set_ylabel("Position on Ring (m)")

        ax.set_title(f"CACC Penetration: {label}")
        ax.set_ylim(0, RING_CIRCUMFERENCE)
        ax.set_xlim(left=0)

    cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
    cbar = fig.colorbar(im, cax=cbar_ax)
    cbar.set_label("Vehicle Speed (km/h)")

    fig.suptitle(
        f"Vehicle Trajectories: Dissipation of Phantom Jams with CACC{title_suffix}\n"
        f"(scatter combines {N_SEEDS} independent seed runs)",
        y=0.97
    )
    plt.tight_layout(rect=[0, 0, 0.9, 0.95])
    return fig

def fig_metrics_vs_time(logs_multi: dict, title_suffix: str = ""):
    fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    colors = plt.cm.viridis(np.linspace(0, 0.9, len(PENETRATION_RATES)))

    for idx, label in enumerate(PENETRATION_RATES):
        logs = logs_multi[label]
        t, m_avg, m_sig, s_avg, s_sig, f_avg, f_sig = compute_frame_metrics_averaged(logs)
        linestyle = "-" if int(label.rstrip("%")) <= 50 else "--"
        lw = 2.5 if int(label.rstrip("%")) <= 50 else 2.0
        c = colors[idx]

        axes[0].plot(t, m_avg, label=f"{label} CACC", color=c, linewidth=lw, linestyle=linestyle)
        axes[0].fill_between(t, m_avg - m_sig, m_avg + m_sig, color=c, alpha=0.12)

        axes[1].plot(t, s_avg, label=f"{label} CACC", color=c, linewidth=lw, linestyle=linestyle)
        axes[1].fill_between(t, s_avg - s_sig, s_avg + s_sig, color=c, alpha=0.12)

        axes[2].plot(t, f_avg, label=f"{label} CACC", color=c, linewidth=lw, linestyle=linestyle)
        axes[2].fill_between(t, f_avg - f_sig, f_avg + f_sig, color=c, alpha=0.12)

    for i, ax in enumerate(axes):
        ax.axvspan(30, 35, alpha=0.15, color="red",
                   label="Perturbation Window" if i == 2 else "")
        ax.grid(True, linestyle="--", alpha=0.6)

    for ax in axes[:2]:
        lines = ax.get_lines()
        data_vals = np.concatenate([l.get_ydata() for l in lines if len(l.get_ydata()) > 0])
        finite = data_vals[np.isfinite(data_vals)]
        lo, hi = finite.min(), finite.max()
        pad = (hi - lo) * 0.12 if hi > lo else 1.0
        ax.set_ylim(lo - pad, hi + pad)

    axes[0].set_ylabel("Mean Speed (km/h)")
    axes[1].set_ylabel("Speed Std Dev (km/h)")
    axes[1].set_title("Flow Stability", fontsize=12)
    axes[2].set_ylabel("Fraction Slow (< 18 km/h)")
    axes[2].set_xlabel("Time (s)")
    axes[2].set_ylim(0, 1)
    axes[2].legend(loc="upper left", ncol=2)
    fig.suptitle(
        f"Traffic Flow Metrics Over Time vs CACC Penetration{title_suffix}\n"
        f"(mean ± 1σ across {N_SEEDS} seed runs)",
        y=0.98
    )
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    return fig

def _summarize_post(logs_multi: dict):
    speeds, stds, jams = [], [], []
    for label in PENETRATION_RATES:
        t, m_avg, _, s_avg, _, f_avg, _ = compute_frame_metrics_averaged(logs_multi[label])
        mask = t >= 35
        speeds.append(float(np.mean(m_avg[mask])))
        stds.append(float(np.mean(s_avg[mask])))
        jams.append(float(np.mean(f_avg[mask]) * 100))
    return speeds, stds, jams

def fig_compare_metrics(logs_sl: dict, logs_dl: dict, logs_tl: dict, logs_ql: dict):
    fig, axes = plt.subplots(4, 3, figsize=(18, 14))

    speeds = {}
    stds   = {}
    jams   = {}
    for key, lm in [("1", logs_sl), ("2", logs_dl), ("3", logs_tl), ("4", logs_ql)]:
        speeds[key], stds[key], jams[key] = _summarize_post(lm)

    x = np.arange(len(PENETRATION_RATES))
    width = 0.2
    colors = ["steelblue", "darkorange", "forestgreen", "crimson"]
    labels = ["1 Lane", "2 Lanes", "3 Lanes", "4 Lanes"]

    # Row 0: absolute metrics
    for i, (key, color, label) in enumerate(zip(["1","2","3","4"], colors, labels)):
        axes[0,0].bar(x + i*width - 1.5*width, speeds[key], width, label=label, color=color, alpha=0.85)
    axes[0,0].set_ylabel("Avg Speed (km/h)")
    axes[0,0].set_title("Mean Post-Perturbation Speed")
    axes[0,0].set_xticks(x); axes[0,0].set_xticklabels(PENETRATION_RATES)
    axes[0,0].legend(loc="lower right", fontsize=9)
    axes[0,0].grid(True, axis="y", alpha=0.3)

    for i, (key, color, label) in enumerate(zip(["1","2","3","4"], colors, labels)):
        axes[0,1].bar(x + i*width - 1.5*width, stds[key], width, label=label, color=color, alpha=0.85)
    axes[0,1].set_ylabel("Speed Std Dev (km/h)")
    axes[0,1].set_title("Flow Stability (lower = more stable)")
    axes[0,1].set_xticks(x); axes[0,1].set_xticklabels(PENETRATION_RATES)
    axes[0,1].legend(loc="upper right", fontsize=9)
    axes[0,1].grid(True, axis="y", alpha=0.3)

    for i, (key, color, label) in enumerate(zip(["1","2","3","4"], colors, labels)):
        axes[0,2].bar(x + i*width - 1.5*width, jams[key], width, label=label, color=color, alpha=0.85)
    axes[0,2].set_ylabel("Jam Fraction (%)")
    axes[0,2].set_title("Congestion")
    axes[0,2].set_xticks(x); axes[0,2].set_xticklabels(PENETRATION_RATES)
    axes[0,2].legend(loc="upper right", fontsize=9)
    axes[0,2].grid(True, axis="y", alpha=0.3)

    # Rows 1-3: signed improvement vs single-lane baseline
    lane_configs = [("2","2 Lanes vs 1 Lane"), ("3","3 Lanes vs 1 Lane"), ("4","4 Lanes vs 1 Lane")]
    for row, (lane_key, row_label) in enumerate(lane_configs, start=1):
        speed_impr = np.array(speeds[lane_key]) - np.array(speeds["1"])
        axes[row,0].bar(x, speed_impr, color=["green" if v >= 0 else "red" for v in speed_impr], alpha=0.85)
        axes[row,0].axhline(0, color="black", linewidth=0.8)
        axes[row,0].set_ylabel("Speed Improvement (km/h)")
        axes[row,0].set_title(f"Speed Benefit: {row_label}")
        axes[row,0].set_xticks(x); axes[row,0].set_xticklabels(PENETRATION_RATES)
        axes[row,0].grid(True, axis="y", alpha=0.3)

        stab_impr = np.array(stds["1"]) - np.array(stds[lane_key])
        axes[row,1].bar(x, stab_impr, color=["green" if v >= 0 else "red" for v in stab_impr], alpha=0.85)
        axes[row,1].axhline(0, color="black", linewidth=0.8)
        axes[row,1].set_ylabel("Stability Improvement (km/h)")
        axes[row,1].set_title(f"Flow Stability Benefit: {row_label}")
        axes[row,1].set_xticks(x); axes[row,1].set_xticklabels(PENETRATION_RATES)
        axes[row,1].grid(True, axis="y", alpha=0.3)

        jam_impr = np.array(jams["1"]) - np.array(jams[lane_key])
        axes[row,2].bar(x, jam_impr, color=["green" if v >= 0 else "red" for v in jam_impr], alpha=0.85)
        axes[row,2].axhline(0, color="black", linewidth=0.8)
        axes[row,2].set_ylabel("Jam Reduction (%)")
        axes[row,2].set_title(f"Congestion Reduction: {row_label}")
        axes[row,2].set_xticks(x); axes[row,2].set_xticklabels(PENETRATION_RATES)
        axes[row,2].grid(True, axis="y", alpha=0.3)

    fig.suptitle(
        "Phantom Jam Mitigation: Comparison Across Lane Configurations\n"
        f"(averaged over {N_SEEDS} seed runs; green = multi-lane better, red = worse than single-lane)",
        fontsize=13, fontweight="bold"
    )
    plt.tight_layout()
    return fig

# ---------------------------------------------------------------------------
# Figure 10: Lane switching benefits (3-panel bar chart)
# ---------------------------------------------------------------------------

def fig_lane_switching_benefits(logs_sl: dict, logs_dl: dict, logs_tl: dict, logs_ql: dict):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    def summarize(lm):
        sp, st, jm = [], [], []
        for label in PENETRATION_RATES:
            t, m, _, s, _, f, _ = compute_frame_metrics_averaged(lm[label])
            mask = t >= 35
            sp.append(np.mean(m[mask]))
            st.append(np.mean(s[mask]))
            jm.append(np.mean(f[mask]) * 100)
        return np.array(sp), np.array(st), np.array(jm)

    sl_sp, sl_st, sl_jm = summarize(logs_sl)
    dl_sp, dl_st, dl_jm = summarize(logs_dl)
    tl_sp, tl_st, tl_jm = summarize(logs_tl)
    ql_sp, ql_st, ql_jm = summarize(logs_ql)

    x = np.arange(len(PENETRATION_RATES))
    w = 0.25
    colors2 = ["darkorange", "forestgreen", "crimson"]
    labels2  = ["2 Lanes", "3 Lanes", "4 Lanes"]

    for ax, (imp2, imp3, imp4), ylabel, title in [
        (axes[0], (dl_sp - sl_sp, tl_sp - sl_sp, ql_sp - sl_sp),
         "Speed Improvement (km/h)", "Lane Switching Benefit on Speed"),
        (axes[1], (sl_st - dl_st, sl_st - tl_st, sl_st - ql_st),
         "Stability Improvement (km/h)", "Lane Switching Benefit on Flow Stability"),
        (axes[2], (sl_jm - dl_jm, sl_jm - tl_jm, sl_jm - ql_jm),
         "Jam Reduction (%)", "Lane Switching Benefit on Congestion Reduction"),
    ]:
        for offset, imp, c, lbl in zip([-w, 0, w], [imp2, imp3, imp4], colors2, labels2):
            ax.bar(x + offset, imp, w, label=lbl, color=c, alpha=0.85)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x); ax.set_xticklabels(PENETRATION_RATES)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend()
        ax.grid(True, axis="y", alpha=0.3)

    axes[2].set_xlabel("CACC Penetration Rate")
    fig.suptitle(
        f"Lane Switching Benefits vs Single-Lane Baseline\n"
        f"(averaged over {N_SEEDS} seed runs)",
        fontsize=14, fontweight="bold"
    )
    plt.tight_layout()
    return fig

def main():
    if FIGURES_DIR.exists():
        shutil.rmtree(FIGURES_DIR)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    logs_sl, logs_dl, logs_tl, logs_ql = {}, {}, {}, {}

    for label in PENETRATION_RATES:
        logs_sl[label] = load_logs_multi_seed(label, LOG_SINGLE_LANE_DIR)
        logs_dl[label] = load_logs_multi_seed(label, LOG_DOUBLE_LANE_DIR)
        logs_tl[label] = load_logs_multi_seed(label, LOG_TRIPLE_LANE_DIR)
        logs_ql[label] = load_logs_multi_seed(label, LOG_QUAD_LANE_DIR)

    def save(fig, internal_name: str, report_name: str):
        p1 = FIGURES_DIR / internal_name
        p2 = RESULTS_DIR / report_name
        fig.savefig(p1, dpi=150, bbox_inches="tight")
        shutil.copy(p1, p2)
        plt.close(fig)
        print(f"  Saved {report_name}")

    print("Generating figures...")

    save(fig_trajectory_grid(logs_sl, " — Single Lane"),
         "01_trajectory_single_lane.png",
         "fig01_trajectory_single_lane.png")

    save(fig_metrics_vs_time(logs_sl, " — Single Lane"),
         "02_metrics_single_lane.png",
         "fig02_metrics_single_lane.png")

    save(fig_trajectory_grid(logs_dl, " — Double Lane"),
         "03_trajectory_double_lane.png",
         "fig03_trajectory_double_lane.png")

    save(fig_metrics_vs_time(logs_dl, " — Double Lane"),
         "04_metrics_double_lane.png",
         "fig04_metrics_double_lane.png")

    save(fig_trajectory_grid(logs_tl, " — Triple Lane"),
         "05_trajectory_triple_lane.png",
         "fig05_trajectory_triple_lane.png")

    save(fig_metrics_vs_time(logs_tl, " — Triple Lane"),
         "06_metrics_triple_lane.png",
         "fig06_metrics_triple_lane.png")

    save(fig_trajectory_grid(logs_ql, " — Quad Lane"),
         "07_trajectory_quad_lane.png",
         "fig07_trajectory_quad_lane.png")

    save(fig_metrics_vs_time(logs_ql, " — Quad Lane"),
         "08_metrics_quad_lane.png",
         "fig08_metrics_quad_lane.png")

    save(fig_compare_metrics(logs_sl, logs_dl, logs_tl, logs_ql),
         "09_comparison_all_lanes.png",
         "fig09_comparison_all_lanes.png")

    save(fig_lane_switching_benefits(logs_sl, logs_dl, logs_tl, logs_ql),
         "10_lane_switching_benefits.png",
         "fig10_lane_switching_benefits.png")

    print(f"\nDone. 10 figures saved to:\n  {FIGURES_DIR}\n  {RESULTS_DIR}")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
