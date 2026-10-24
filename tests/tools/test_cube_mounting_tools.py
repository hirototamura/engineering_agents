import json
from pathlib import Path
import sys

import pytest

from tools import build_cube_memory_report, compare_cube_mounts


@pytest.mark.parametrize("mount", [None, "near_corner_000"])
def test_replay_projection_preserves_mount_geometry(tmp_path, mount):
    physics = {"cube_side_m": .18, "wheel_radius_m": .058, "wheel_face_inset_m": .012}
    if mount:
        physics["wheel_mount_side"] = mount
    result, compiled = tmp_path / "result.json", tmp_path / "compiled.json"
    result.write_text(json.dumps({"candidate_id": "model", "records": []}))
    compiled.write_text(json.dumps({"config": {"physics": physics}}))
    view = build_cube_memory_report._candidate(result, compiled, tmp_path / "report.html")
    assert view["physics"]["wheel_face_inset_m"] == .012
    assert view["physics"].get("wheel_mount_side", "far_corner_000") == (mount or "far_corner_000")


def test_inconclusive_fixture_check_has_nonzero_process_status(tmp_path, monkeypatch):
    monkeypatch.setattr(compare_cube_mounts, "qualify", lambda *args: {"state": "inconclusive"})
    monkeypatch.setattr(sys, "argv", ["fixture-check", "--qualification-input", str(tmp_path / "input.json"),
                                    "--output", str(tmp_path / "result")])
    with pytest.raises(SystemExit) as stopped:
        compare_cube_mounts.main()
    assert stopped.value.code == 2


def test_failed_native_fixture_preserves_completed_evidence(tmp_path, monkeypatch):
    import hashlib
    from environment.mujoco import backend
    from scenario.balancing_cube.adapter import BalancingCubeAdapter
    from scenario.balancing_cube.design import digest
    source = {"controller": {"K": [[1]], "yaw_rate_gain_nm_s": 0},
              "code_digests": {}, "fixtures": [
                  {"id": "first", "config": {}, "case": {"id": "first"}},
                  {"id": "failed", "config": {}, "case": {"id": "failed"}}]}
    source["controller_digest"] = digest(source["controller"])
    path = tmp_path / "input.json"
    path.write_text(json.dumps(source))
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(BalancingCubeAdapter, "_code_digests", staticmethod(lambda: {}))
    def native(config, case, controller):
        if case["id"] == "failed":
            raise RuntimeError("injected solver failure")
        return {"saved_result": "first"}
    monkeypatch.setattr(backend, "native_rollout", native)
    monkeypatch.setattr(backend, "gpu_rollouts", lambda *a: pytest.fail("MJX must not start after native failure"))
    output = tmp_path / "results"
    with pytest.raises(RuntimeError, match="injected solver failure"):
        compare_cube_mounts.qualify(path, output)
    assert json.loads((output / "first-native.json").read_text()) == {"saved_result": "first"}
    assert json.loads((output / "qualification.json").read_text())["completed_native_fixtures"] == 1
