import json
import pathlib
import shutil
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

PROJECT_DIR = pathlib.Path(__file__).parent
LOG_DIR = PROJECT_DIR / "LOG"
LOG_SINGLE_LANE_DIR = LOG_DIR / "SINGLE_LANE"
LOG_DOUBLE_LANE_DIR = LOG_DIR / "DOUBLE_LANE"
FIGURES_DIR = LOG_DIR / "phantom_figures"

RING_CIRCUMFERENCE = 791.0
SLOW_THRESHOLD = 5.0  # m/s
PERTURBER_ID = 201

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

def load_log(filename: str, subdir: pathlib.Path = None) -> dict:
    if subdir is None:
        subdir = LOG_DIR
    filepath = subdir / filename
    with open(filepath) as f:
        return json.load(f)

def extract_trajectory_data(log: dict, stride: int = 1):
    frames = log["frames"]
    t_vals, x_vals, v_vals = [], [], []
    for frame in frames[::stride]:
        t = frame["t"]
        for veh in frame["vehicles"]:
            t_vals.append(t)
            x_vals.append(veh["u"] % RING_CIRCUMFERENCE)
            v_vals.append(veh["speed"])
    return np.array(t_vals), np.array(x_vals), np.array(v_vals)

def compute_frame_metrics(log: dict):
    frames = log["frames"]
    t_list, mean_v, std_v, frac_slow = [], [], [], []
    for frame in frames:
        speeds = np.array([v["speed"] for v in frame["vehicles"]])
        t_list.append(frame["t"])
        mean_v.append(np.mean(speeds))
        std_v.append(np.std(speeds))
        frac_slow.append(np.mean(speeds < SLOW_THRESHOLD))
    return np.array(t_list), np.array(mean_v), np.array(std_v), np.array(frac_slow)

def fig_trajectory_grid(logs: dict, title_suffix: str = ""):
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), sharex=True, sharey=True)
    axes = axes.flatten()

    im = None
    for idx, label in enumerate(GRID_RATES):
        ax = axes[idx]
        log = logs[label]
        t_vals, x_vals, v_vals = extract_trajectory_data(log, stride=2)
        im = ax.scatter(t_vals, x_vals, c=v_vals, cmap=SPEED_CMAP, s=1.5, vmin=0, vmax=20, alpha=0.85, edgecolors="none")
        ax.axvspan(30, 35, color="grey", alpha=0.3, zorder=0)

        frames = log["frames"]
        t_p, x_p = [], []
        for frame in frames[::2]:
            t = frame["t"]
            for veh in frame["vehicles"]:
                if veh["id"] == PERTURBER_ID:
                    x = veh["u"] % RING_CIRCUMFERENCE
                    if len(x_p) > 0 and abs(x - x_p[-1]) > RING_CIRCUMFERENCE / 2:
                        ax.plot(t_p, x_p, "k--", linewidth=1.5, alpha=0.7)
                        t_p, x_p = [t], [x]
                    else:
                        t_p.append(t)
                        x_p.append(x)

        if t_p:
            ax.plot(t_p, x_p, "k--", linewidth=1.5, alpha=0.7, label="Lead Car" if idx == 0 else "")

        if idx >= 3:
            ax.set_xlabel("Time (s)")
        if idx % 3 == 0:
            ax.set_ylabel("Position on Ring (m)")

        ax.set_title(f"CACC Penetration: {label}")
        ax.set_ylim(0, RING_CIRCUMFERENCE)
        ax.set_xlim(left=0)

    cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
    cbar = fig.colorbar(im, cax=cbar_ax)
    cbar.set_label("Vehicle Speed (m/s)")

    title = f"Vehicle Trajectories: Dissipation of Phantom Jams with CACC{title_suffix}"
    fig.suptitle(title, y=0.97)
    plt.tight_layout(rect=[0, 0, 0.9, 0.95])
    return fig


def fig_metrics_vs_time(logs: dict, title_suffix: str = ""):
    fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    colors = plt.cm.viridis(np.linspace(0, 0.9, len(PENETRATION_RATES)))

    for idx, label in enumerate(PENETRATION_RATES):
        log = logs[label]
        t, mean_v, std_v, frac_slow = compute_frame_metrics(log)
        axes[0].plot(t, mean_v, label=f"{label} CACC", color=colors[idx], linewidth=2)
        axes[1].plot(t, std_v, label=f"{label} CACC", color=colors[idx], linewidth=2)
        axes[2].plot(t, frac_slow, label=f"{label} CACC", color=colors[idx], linewidth=2)

    for i, ax in enumerate(axes):
        ax.axvspan(30, 35, alpha=0.15, color="red", label="Perturbation Window" if i == 2 else "")
        ax.grid(True, linestyle="--", alpha=0.6)

    for ax in axes[:2]:
        lines = ax.get_lines()
        data_vals = np.concatenate([l.get_ydata() for l in lines if len(l.get_ydata()) > 0])
        finite = data_vals[np.isfinite(data_vals)]
        lo, hi = finite.min(), finite.max()
        pad = (hi - lo) * 0.12 if hi > lo else 1.0
        ax.set_ylim(lo - pad, hi + pad)

    axes[0].set_ylabel("Mean Speed (m/s)")
    axes[1].set_ylabel("Speed Std Dev (m/s)")
    axes[1].set_title("Flow Stability", fontsize=12)
    axes[2].set_ylabel("Fraction Slow (< 5 m/s)")
    axes[2].set_xlabel("Time (s)")
    axes[2].set_ylim(0, 1)
    axes[2].legend(loc="upper left", ncol=2)
    title = f"Traffic Flow Metrics Over Time vs CACC Penetration{title_suffix}"
    fig.suptitle(title, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def fig_summary_bars(logs: dict, title_suffix: str = ""):
    mean_speeds, speed_stds, frac_slow_avg = [], [], []

    for label in PENETRATION_RATES:
        log = logs[label]
        t, mean_v, std_v, frac_slow = compute_frame_metrics(log)
        mask = t >= 35
        mean_speeds.append(np.mean(mean_v[mask]))
        speed_stds.append(np.mean(std_v[mask]))
        frac_slow_avg.append(np.mean(frac_slow[mask]))

    x = np.arange(len(PENETRATION_RATES))
    width = 0.25
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(x - width, mean_speeds, width, label="Mean Speed (m/s)", color="royalblue", alpha=0.85)
    ax.bar(x, speed_stds, width, label="Speed Std Dev (m/s)", color="darkorange", alpha=0.85)
    ax.bar(x + width, frac_slow_avg, width, label="Frac. Slow (<5 m/s)", color="firebrick", alpha=0.85)

    ax.set_xlabel("CACC Penetration Rate")
    ax.set_title(f"Post-Perturbation System State Average (t = 35s to End){title_suffix}")
    ax.set_xticks(x)
    ax.set_xticklabels(PENETRATION_RATES)
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    return fig


def fig_trajectory_single(log: dict, label: str):
    fig, ax = plt.subplots(figsize=(12, 7))

    t_vals, x_vals, v_vals = extract_trajectory_data(log, stride=1)
    im = ax.scatter(t_vals, x_vals, c=v_vals, cmap=SPEED_CMAP, s=2.0,
                    vmin=0, vmax=20, alpha=0.85, edgecolors="none")
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Speed (m/s)")

    frames = log["frames"]
    t_p, x_p = [], []
    for frame in frames:
        t = frame["t"]
        for veh in frame["vehicles"]:
            if veh["id"] == PERTURBER_ID:
                x = veh["u"] % RING_CIRCUMFERENCE
                if len(x_p) > 0 and abs(x - x_p[-1]) > RING_CIRCUMFERENCE / 2:
                    ax.plot(t_p, x_p, "k--", linewidth=2.5, alpha=0.8)
                    t_p, x_p = [t], [x]
                else:
                    t_p.append(t)
                    x_p.append(x)

    if t_p:
        ax.plot(t_p, x_p, "k--", linewidth=2.5, alpha=0.8, label="Perturber Vehicle")

    ax.axvspan(30, 35, color="grey", alpha=0.3, zorder=0, label="Perturbation Window")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position Along Ring (m)")
    ax.set_title(f"Vehicle Trajectories: {label} CACC Penetration")
    ax.set_ylim(0, RING_CIRCUMFERENCE)
    ax.set_xlim(left=0)
    ax.legend(loc="upper right", framealpha=0.9)

    plt.tight_layout()
    return fig


def fig_compare_metrics(logs_sl: dict, logs_dl: dict):
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    sl_speeds, sl_stds, sl_jams = [], [], []
    dl_speeds, dl_stds, dl_jams = [], [], []

    for label in PENETRATION_RATES:
        # single lane
        t, mean_v, std_v, frac_slow = compute_frame_metrics(logs_sl[label])
        mask = t >= 35
        sl_speeds.append(np.mean(mean_v[mask]))
        sl_stds.append(np.mean(std_v[mask]))
        sl_jams.append(np.mean(frac_slow[mask]) * 100)

        # double lane
        t, mean_v, std_v, frac_slow = compute_frame_metrics(logs_dl[label])
        mask = t >= 35
        dl_speeds.append(np.mean(mean_v[mask]))
        dl_stds.append(np.mean(std_v[mask]))
        dl_jams.append(np.mean(frac_slow[mask]) * 100)

    x = np.arange(len(PENETRATION_RATES))
    width = 0.35

    # Mean speed
    axes[0, 0].bar(x - width/2, sl_speeds, width, label="Single Lane", color="steelblue", alpha=0.85)
    axes[0, 0].bar(x + width/2, dl_speeds, width, label="Double Lane", color="darkorange", alpha=0.85)
    axes[0, 0].set_ylabel("Avg Speed (m/s)")
    axes[0, 0].set_title("Mean Post-Perturbation Speed")
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(PENETRATION_RATES)
    axes[0, 0].legend()
    axes[0, 0].grid(True, axis="y", alpha=0.3)

    # Speed std dev
    axes[0, 1].bar(x - width/2, sl_stds, width, label="Single Lane", color="steelblue", alpha=0.85)
    axes[0, 1].bar(x + width/2, dl_stds, width, label="Double Lane", color="darkorange", alpha=0.85)
    axes[0, 1].set_ylabel("Speed Std Dev (m/s)")
    axes[0, 1].set_title("Flow Stability")
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(PENETRATION_RATES)
    axes[0, 1].legend()
    axes[0, 1].grid(True, axis="y", alpha=0.3)

    # Jam fraction
    axes[0, 2].bar(x - width/2, sl_jams, width, label="Single Lane", color="steelblue", alpha=0.85)
    axes[0, 2].bar(x + width/2, dl_jams, width, label="Double Lane", color="darkorange", alpha=0.85)
    axes[0, 2].set_ylabel("Jam Fraction (%)")
    axes[0, 2].set_title("Congestion")
    axes[0, 2].set_xticks(x)
    axes[0, 2].set_xticklabels(PENETRATION_RATES)
    axes[0, 2].legend()
    axes[0, 2].grid(True, axis="y", alpha=0.3)

    # Speed improvement
    speed_impr = np.array(dl_speeds) - np.array(sl_speeds)
    axes[1, 0].bar(x, speed_impr, color=["green" if v > 0 else "red" for v in speed_impr], alpha=0.85)
    axes[1, 0].axhline(y=0, color="black", linestyle="-", linewidth=0.8)
    axes[1, 0].set_ylabel("Speed Improvement (m/s)")
    axes[1, 0].set_title("Lane Switching Benefit on Speed")
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(PENETRATION_RATES)
    axes[1, 0].grid(True, axis="y", alpha=0.3)

    # Stability improvement
    stab_impr = np.array(sl_stds) - np.array(dl_stds)
    axes[1, 1].bar(x, stab_impr, color=["green" if v > 0 else "red" for v in stab_impr], alpha=0.85)
    axes[1, 1].axhline(y=0, color="black", linestyle="-", linewidth=0.8)
    axes[1, 1].set_ylabel("Stability Improvement (m/s)")
    axes[1, 1].set_title("Lane Switching Benefit on Flow Stability")
    axes[1, 1].set_xticks(x)
    axes[1, 1].set_xticklabels(PENETRATION_RATES)
    axes[1, 1].grid(True, axis="y", alpha=0.3)

    # Jam reduction
    jam_impr = np.array(sl_jams) - np.array(dl_jams)
    axes[1, 2].bar(x, jam_impr, color=["green" if v > 0 else "red" for v in jam_impr], alpha=0.85)
    axes[1, 2].axhline(y=0, color="black", linestyle="-", linewidth=0.8)
    axes[1, 2].set_ylabel("Jam Reduction (%)")
    axes[1, 2].set_title("Lane Switching Benefit on Congestion Reduction")
    axes[1, 2].set_xticks(x)
    axes[1, 2].set_xticklabels(PENETRATION_RATES)
    axes[1, 2].grid(True, axis="y", alpha=0.3)

    fig.suptitle("Single-Lane vs Double-Lane Phantom Jam Mitigation Comparison", fontsize=14, fontweight="bold")
    plt.tight_layout()
    return fig

def main():
    if FIGURES_DIR.exists():
        shutil.rmtree(FIGURES_DIR)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Load single-lane scenarios
    logs_sl = {}
    for label in PENETRATION_RATES:
        filename = f"phantom_jam_{label.replace('%', 'pct')}.json"
        logs_sl[label] = load_log(filename, LOG_SINGLE_LANE_DIR)

    # Load double-lane scenarios
    logs_dl = {}
    for label in PENETRATION_RATES:
        filename = f"phantom_jam_2lane_{label.replace('%', 'pct')}.json"
        logs_dl[label] = load_log(filename, LOG_DOUBLE_LANE_DIR)

    # Single-lane figures
    fig1 = fig_trajectory_grid(logs_sl, " - Single Lane")
    fig1.savefig(FIGURES_DIR / "01_phantom_trajectory_grid_single_lane.png", dpi=150, bbox_inches="tight")
    plt.close(fig1)

    fig2 = fig_metrics_vs_time(logs_sl, " - Single Lane")
    fig2.savefig(FIGURES_DIR / "02_phantom_metrics_vs_time_single_lane.png", dpi=150, bbox_inches="tight")
    plt.close(fig2)

    # Double-lane figures
    fig4 = fig_trajectory_grid(logs_dl, " - Double Lane")
    fig4.savefig(FIGURES_DIR / "04_phantom_trajectory_grid_double_lane.png", dpi=150, bbox_inches="tight")
    plt.close(fig4)

    fig5 = fig_metrics_vs_time(logs_dl, " - Double Lane")
    fig5.savefig(FIGURES_DIR / "05_phantom_metrics_vs_time_double_lane.png", dpi=150, bbox_inches="tight")
    plt.close(fig5)

    # Comparative figure
    fig7 = fig_compare_metrics(logs_sl, logs_dl)
    fig7.savefig(FIGURES_DIR / "07_phantom_comparison_single_vs_double.png", dpi=150, bbox_inches="tight")
    plt.close(fig7)

    # Individual trajectories
    for label in PENETRATION_RATES:
        fig = fig_trajectory_single(logs_sl[label], f"{label} CACC (Single Lane)")
        fname = f"trajectory_single_{label.replace('%', 'pct')}.png"
        fig.savefig(FIGURES_DIR / fname, dpi=150, bbox_inches="tight")
        plt.close(fig)

        fig = fig_trajectory_single(logs_dl[label], f"{label} CACC (Double Lane)")
        fname = f"trajectory_double_{label.replace('%', 'pct')}.png"
        fig.savefig(FIGURES_DIR / fname, dpi=150, bbox_inches="tight")
        plt.close(fig)
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
