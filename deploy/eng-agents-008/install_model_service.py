"""Install an isolated systemd user service; never modifies existing services."""
import os
from pathlib import Path
import re
import subprocess

here = Path(__file__).resolve().parent
workspace = Path(os.environ.get("EA_WORKSPACE", str(here.parents[2]))).resolve()
unit_path = Path.home() / ".config/systemd/user/eng-agents-hermes-model.service"
gpu_uuid = os.environ.get("EA_GPU_UUID")
gpu_override = None
if gpu_uuid is not None:
    if not re.fullmatch(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", gpu_uuid):
        raise ValueError("EA_GPU_UUID must be the full GPU UUID from nvidia-smi -L")
    gpu_override = f"[Service]\nEnvironment=EA_GPU_UUID={gpu_uuid}\n"
gpu_override_path = unit_path.with_name(unit_path.name + ".d") / "50-eng-agents-gpu.conf"
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
if gpu_override is not None and gpu_override_path.exists() and gpu_override_path.read_text() != gpu_override:
    raise FileExistsError(f"Refusing to replace an existing GPU override: {gpu_override_path}")
unit_path.parent.mkdir(parents=True, exist_ok=True)
unit_path.write_text(unit)
if gpu_override is not None:
    gpu_override_path.parent.mkdir(exist_ok=True)
    gpu_override_path.write_text(gpu_override)
subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
subprocess.run(["systemctl", "--user", "enable", "--now", unit_path.name], check=True)
print("Installed", unit_path.name)
print("This user service starts at user login; it does not enable system linger.")
