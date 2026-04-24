from playwright.sync_api import sync_playwright
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_DIR = pathlib.Path(__file__).parent
RING_HTML = PROJECT_DIR.parent / "ring.html"
LOG_DIR = PROJECT_DIR / "LOG"
SCENARIOS_DIR = PROJECT_DIR / "scenarios"
RUN_SEEDS = [0, 1, 2]

def _log_dir_for(lane_label: str, seed: int) -> pathlib.Path:
    return LOG_DIR / lane_label / f"seed_{seed}"

def run_scenario(scenario_name: str, output_filename: str, output_dir: pathlib.Path) -> bool:
    output_path = output_dir / output_filename

    if output_path.exists():
        print(f"[SKIP] {scenario_name} (already exists)")
        return True

    scenario_path = SCENARIOS_DIR / scenario_name
    if not scenario_path.exists():
        print(f"[ERROR] Scenario file not found: {scenario_path}")
        return False

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
        print(f"[DONE] {output_filename}")
        return True

    except Exception as e:
        print(f"[FAIL] {scenario_name}: {e}")
        return False

def build_phantom_scenario_list(n_lanes: int, lane_label: str, seed: int) -> list:
    scenarios = []
    seed_dir = SCENARIOS_DIR / f"seed_{seed}"
    if not seed_dir.exists():
        return scenarios

    prefix = f"phantom_jam_{n_lanes}lane_"
    matches = sorted(seed_dir.glob(f"{prefix}*.json"),
                     key=lambda f: int(f.stem.split("_")[-1].rstrip("pct") or 0))

    output_dir = _log_dir_for(lane_label, seed)
    for scenario_file in matches:
        # scenario_path passed as relative string: "seed_X/filename.json"
        rel_path = f"seed_{seed}/{scenario_file.name}"
        output_filename = scenario_file.name
        scenarios.append((rel_path, output_filename, output_dir))
    return scenarios

def main():
    all_scenarios = []

    for seed in RUN_SEEDS:
        all_scenarios += build_phantom_scenario_list(1, "SINGLE_LANE", seed)
        all_scenarios += build_phantom_scenario_list(2, "DOUBLE_LANE", seed)
        all_scenarios += build_phantom_scenario_list(3, "TRIPLE_LANE", seed)
        all_scenarios += build_phantom_scenario_list(4, "QUAD_LANE",   seed)

    print(f"Total scenarios to run: {len(all_scenarios)}")
    max_workers = 25
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for scenario_rel, output_filename, output_dir in all_scenarios:
            future = executor.submit(run_scenario, scenario_rel, output_filename, output_dir)
            futures[future] = scenario_rel

        for future in as_completed(futures):
            try:
                success = future.result()
                results.append((futures[future], success))
            except Exception as e:
                print(f"[EXCEPTION] {futures[future]}: {e}")
                results.append((futures[future], False))

    failed = [name for name, ok in results if not ok]
    if failed:
        print(f"\n[WARN] {len(failed)} scenarios failed:")
        for name in failed:
            print(f"  {name}")
    else:
        print(f"\n[DONE] All {len(results)} scenarios completed successfully.")

    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
