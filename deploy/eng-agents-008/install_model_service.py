"""Install an isolated systemd user service; never modifies existing services."""
import os
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
workspace = Path(os.environ.get("EA_WORKSPACE", str(here.parents[2]))).resolve()
unit_path = Path.home() / ".config/systemd/user/eng-agents-hermes-model.service"
script = workspace / "engineering_agents/deploy/eng-agents-008/start-model.sh"
if any(c in str(script) for c in ['"', '\n', '%', '\\']):
    raise ValueError("Unsupported systemd path character")
unit = f'''[Unit]
Description=Engineering Agents Hermes local model (one RTX A5000)
StartLimitIntervalSec=300
StartLimitBurst=2

[Service]
Type=simple
ExecStart=/usr/bin/bash "{script}"
Restart=on-failure
RestartSec=15
TimeoutStopSec=30

[Install]
WantedBy=default.target
'''
if unit_path.exists() and unit_path.read_text() != unit:
    raise FileExistsError(f"Refusing to replace a different service: {unit_path}")
unit_path.parent.mkdir(parents=True, exist_ok=True)
unit_path.write_text(unit)
subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
subprocess.run(["systemctl", "--user", "enable", "--now", unit_path.name], check=True)
print("Installed", unit_path.name)
print("This user service starts at user login; it does not enable system linger.")
