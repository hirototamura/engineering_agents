# 2D Bar Simulation (legacy reference)

Original LLM multi-agent 2D bar/fire simulation. Preserved under `materials/` for reference; not part of the ECLSS resilience-loop stack.

## Run

```bash
cd src/materials/2d-bar-simulation
python main.py --config config.yaml --save-frames
```

Requires Ollama running locally. See the root [README.md](../../../README.md) for setup details.

## Outputs

Frames and logs are written to the directory configured in `config.yaml` (`visualization.output_dir`, default `output/`).

## Visualization

- `visualization/viewer.html` — browser replay
- `visualization/generate_video.py` — MP4 from run artifacts
