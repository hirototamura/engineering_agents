# Dashboard screenshots

The English and Japanese README files reference PNG screenshots in this directory:

| File | README section |
| --- | --- |
| `dashboard-overview-compare.png` | Overview — two LLM runs side by side |
| `dashboard-topology-proposals.png` | Design proposals — Before / After topology |
| `dashboard-step-replay.png` | Step replay — timeline, reasoning, telemetry |

## Capturing screenshots

1. Install and run a labeled or LLM scenario so `src/experiments/results/` contains at least one run (and two runs for the compare shot).
2. Start the dashboard: `python -m streamlit run src/tools/dashboard/app.py`
3. Capture the three views above at a representative step (step 17 works well for EPS boost in step replay).
4. Save PNGs into this directory using the filenames in the table.

Until images are committed, README figure links will 404 in the GitHub UI. The dashboard itself works without these assets.
