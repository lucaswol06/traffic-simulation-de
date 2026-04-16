import json
import pathlib

PROJECT_DIR = pathlib.Path(__file__).parent
SCENARIOS_DIR = PROJECT_DIR / "scenarios"

RING_CIRCUMFERENCE = 791.0  # meters
VEH_PER_LANE = 35         # Total number of cars per lane excluding perturber
EQUILIBRIUM_SPEED = 9.1     # m/s (Starting speed)
PERTURBER_ID = 201          # The "Orange Car"
PERTURBER_POS = 200.0       # Starting position of the perturber
# Lane switching threshold (MOBIL politeness factor for double-lane scenarios)
MOBIL_P = 0.1               # Lane change politeness factor [0-1], lower = more aggressive

BASE_PARAMETERS = {
    "CACC_T_platoon": 0.6,
    "CACC_alpha": 0.5,
    "IDM_v0": 30,
    "IDM_T": 1.4,
    "IDM_s0": 2,
    "IDM_a": 1.5,
    "IDM_b": 2.0,
    "IDM_v0_AV": 30,
    "IDM_T_AV": 1.4,
    "IDM_s0_AV": 2,
    "IDM_a_AV": 2.0,
    "IDM_b_AV": 3.0,
    "fracTruck": 0,
    "driver_varcoeff": 0.1,
    "MOBIL_p": MOBIL_P
}

BASE_ACTIONS = [
    {
        "time": 30,
        "vehicleId": PERTURBER_ID,
        "set": {
            "longModel": {"v0": 0, "T": 1.4, "s0": 2, "a": 1.5, "b": 4.0}
        }
    },
    {
        "time": 35,
        "vehicleId": PERTURBER_ID,
        "set": {
            "longModel": {"v0": 30, "T": 1.4, "s0": 2, "a": 1.5, "b": 2.0}
        }
    }
]

BASE_LOGGING = {
    "enabled": True,
    "sampleEverySec": 1.0,
    "autoExportEverySec": 0,
    "maxFrames": 5000,
    "includeSpecialVehicles": True,
    "logRegularOnly": False
}

PENETRATION_RATES = [
    (0.00, "0%"), (0.10, "10%"), (0.20, "20%"), (0.30, "30%"), (0.40, "40%"),
    (0.50, "50%"), (0.60, "60%"), (0.70, "70%"), (0.80, "80%"), (0.90, "90%"), (1.00, "100%"),
]

def compute_av_indices(frac_av, n_background):
    if frac_av < 0.01: return set()
    if frac_av > 0.99: return set(range(n_background))
    n_av = round(frac_av * n_background)
    indices = set()
    for k in range(n_av):
        idx = round(k * n_background / n_av) % n_background
        indices.add(idx)
    return indices

def generate_vehicle_list(frac_av, n_lanes=1, allow_lane_change=False):
    vehicles = []

    # Calculate spacing and background vehicles per lane
    spacing = RING_CIRCUMFERENCE / VEH_PER_LANE
    n_background_per_lane = VEH_PER_LANE - 1

    # For multi-lane scenarios, create vehicles for each lane
    vehicle_id = 1
    for lane in range(n_lanes):
        av_indices = compute_av_indices(frac_av, n_background_per_lane)

        for i in range(n_background_per_lane):
            pos = (PERTURBER_POS - (i + 1) * spacing) % RING_CIRCUMFERENCE
            is_av = i in av_indices

            vehicles.append({
                "id": vehicle_id,
                "road": 0,
                "type": "car",
                "lane": lane,
                "u": round(pos, 3),
                "speed": EQUILIBRIUM_SPEED,
                "isAV": is_av,
                "noLaneChange": not allow_lane_change  # True for single-lane, False for double-lane
            })
            vehicle_id += 1

    # Add the Perturber in lane 0
    vehicles.append({
        "id": PERTURBER_ID,
        "road": 0,
        "type": "car",
        "lane": 0,
        "u": PERTURBER_POS,
        "speed": EQUILIBRIUM_SPEED,
        "isAV": False,
        "noLaneChange": True  # Perturber always fixed to lane 0, regardless of scenario type
    })

    return vehicles

def generate_scenario(frac_av, n_lanes=1, allow_lane_change=False):
    params = BASE_PARAMETERS.copy()
    return {
        "seed": 42,
        "duration": 500,
        "timewarp": 5,
        "nLanes": n_lanes,
        "parameters": params,
        "vehicles": generate_vehicle_list(frac_av, n_lanes, allow_lane_change),
        "actions": BASE_ACTIONS,
        "logging": BASE_LOGGING
    }

def main():
    SCENARIOS_DIR.mkdir(exist_ok=True)

    for frac_av, label in PENETRATION_RATES:
        scenario = generate_scenario(frac_av, n_lanes=1, allow_lane_change=False)
        filepath = SCENARIOS_DIR / f"phantom_jam_1lane_{label.replace('%', 'pct')}.json"
        with open(filepath, "w") as f:
            json.dump(scenario, f, indent=2)

        scenario = generate_scenario(frac_av, n_lanes=2, allow_lane_change=True)
        filepath = SCENARIOS_DIR / f"phantom_jam_2lane_{label.replace('%', 'pct')}.json"
        with open(filepath, "w") as f:
            json.dump(scenario, f, indent=2)

if __name__ == "__main__":
    main()
