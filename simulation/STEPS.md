# How to Run the Simulation

1. **Generate scenarios** — `python generate_phantom_scenarios.py`
   - creates the scenario JSON files used by the sim. Modify parameters as necessary.

2. **Run the sim** — `python run_sim.py`
   - runs through each scenario, logs output to `LOG/`. Modify workers as compute permits.

3. **Analyze results** — `python analyze_phantom.py`
   - crunches the logs, spits out figures in `LOG/phantom_figures/`

4. **Check metrics** — `python report_metrics.py`
   - prints a summary table of the key numbers
