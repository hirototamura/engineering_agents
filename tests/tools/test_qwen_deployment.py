import json
import os
from pathlib import Path
import subprocess
import sys


def run_launcher(tmp_path, **extra):
    venv = tmp_path / "runtime"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").symlink_to(sys.executable)
    fake = venv / "bin/vllm"
    fake.write_text("#!/usr/bin/env python3\nimport os,json,sys\nprint(json.dumps({'argv':sys.argv[1:],'devices':os.environ['CUDA_VISIBLE_DEVICES']}))\n")
    fake.chmod(0o755)
    script = Path(__file__).parents[2] / "scripts/serve_qwen_six_gpu.sh"
    env = {**os.environ, "EA_VLLM_VENV": str(venv), "VLLM_MODEL_REVISION": "frozen-test-revision",
           "EA_LLM_GPU_IDS": "0,1,2,3,4,5", "EA_MJX_GPU_IDS": "6,7", **extra}
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)


def test_six_gpu_deployment_uses_three_two_gpu_replicas(tmp_path):
    result = run_launcher(tmp_path)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["devices"] == "0,1,2,3,4,5"
    args = plan["argv"]
    assert args[args.index("--tensor-parallel-size") + 1] == "2"
    assert args[args.index("--data-parallel-size") + 1] == "3"
    assert args[args.index("--revision") + 1] == "frozen-test-revision"


def test_deployment_rejects_overlapping_simulation_devices_before_launch(tmp_path):
    result = run_launcher(tmp_path, EA_MJX_GPU_IDS="5,6")
    assert result.returncode != 0
    assert "disjoint" in result.stderr
    assert not result.stdout
