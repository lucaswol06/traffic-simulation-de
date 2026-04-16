from playwright.sync_api import sync_playwright
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_DIR = pathlib.Path(__file__).parent
RING_HTML = PROJECT_DIR.parent / "ring.html"
LOG_DIR = PROJECT_DIR / "LOG"
SCENARIOS_DIR = PROJECT_DIR / "scenarios"

LOG_SINGLE_LANE_DIR = LOG_DIR / "SINGLE_LANE"
LOG_DOUBLE_LANE_DIR = LOG_DIR / "DOUBLE_LANE"

def run_scenario(scenario_name: str, output_filename: str, output_dir: pathlib.Path = None) -> bool:
    if output_dir is None:
        output_dir = LOG_DIR

    scenario_path = SCENARIOS_DIR / f"{scenario_name}.json"
    output_path = output_dir / output_filename

    if output_path.exists():
        print(f"[SKIP] {scenario_name} (already exists)")
        return True

    print(f"[START] {scenario_name}")
    with open(scenario_path) as f:
        scenario = json.load(f)

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-extensions",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-default-apps",
                    "--disable-sync",
                ]
            )
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(RING_HTML.as_uri(), wait_until="networkidle")
            page.wait_for_selector("#scenarioInput", timeout=15000)
            page.fill("#scenarioInput", json.dumps(scenario))
            page.click("#scenarioRunBtn")

            try:
                page.wait_for_function(
                    """
                    () => {
                        const log = window.scenarioLogData;
                        if (!log) return false;
                        const events = log.events || [];
                        return events.some(e => e.type === 'sim_paused_duration');
                    }
                    """,
                    timeout=300000
                )
            except Exception:
                browser.close()
                return False

            log_data = page.evaluate("() => window.scenarioLogData")
            browser.close()

        with open(output_path, "w") as f:
            json.dump(log_data, f, indent=2)
        return True

    except Exception:
        return False

def main():
    cacc_scenarios = [
        ("exp1_cacc", "exp1_cacc.json", LOG_DIR),
        ("exp2_cacc", "exp2_cacc.json", LOG_DIR),
        ("exp1_pd", "exp1_pd.json", LOG_DIR),
    ]

    def build_phantom_scenario_list(pattern_prefix: str, output_dir: pathlib.Path) -> list:
        scenarios = []
        if SCENARIOS_DIR.exists():
            matches = list(SCENARIOS_DIR.glob(f"{pattern_prefix}*.json"))
            matches.sort(key=lambda f: int(f.stem.split("_")[-1].rstrip("pct")) if f.stem.split("_")[-1].endswith("pct") else 0)
            for scenario_file in matches:
                scenario_name = scenario_file.stem
                output_filename = scenario_name.replace("_1lane_", "_").replace("_2lane_", "_2lane_") + ".json"
                scenarios.append((scenario_name, output_filename, output_dir))
        return scenarios

    phantom_single_lane = build_phantom_scenario_list("phantom_jam_1lane_", LOG_SINGLE_LANE_DIR)
    phantom_double_lane = build_phantom_scenario_list("phantom_jam_2lane_", LOG_DOUBLE_LANE_DIR)

    scenarios = cacc_scenarios + phantom_single_lane + phantom_double_lane
    max_workers = 25
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for scenario_name, output_filename, output_dir in scenarios:
            future = executor.submit(run_scenario, scenario_name, output_filename, output_dir)
            futures[future] = scenario_name

        for future in as_completed(futures):
            try:
                success = future.result()
                results.append((futures[future], success))
            except Exception:
                results.append((futures[future], False))
    print("DONE")

    return 0 if all(success for _, success in results) else 1

if __name__ == "__main__":
    sys.exit(main())
