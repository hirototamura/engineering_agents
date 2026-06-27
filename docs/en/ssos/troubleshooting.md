> Japanese: [../ja/ssos/troubleshooting.md](../ja/ssos/troubleshooting.md)

# Troubleshooting

Common issues and fixes when integrating SSOS ECLSS + EPS.

---

## Action Type Mismatch — Goal Waits Forever

### Symptoms

```
Waiting for an action server...
```

`air_revitalisation` appears in `ros2 action list`, but `send_goal` never returns.

### Cause

Action **names** may match while **types** differ. Legacy docs referencing `space_station_eclss/action/...` are invalid on the current Jazzy image.

### Verification

```bash
ros2 node info /air_revitalisation | grep -A1 'Action Servers'
# Expected: space_station_interfaces/action/AirRevitalisation
```

### Fix

Send manually with the correct type:

```bash
ros2 action send_goal /air_revitalisation \
  space_station_interfaces/action/AirRevitalisation \
  "{initial_co2_mass: 1800.0, initial_moisture_content: 25.0, initial_contaminants: 5.0}"
```

In code, use the `ACTION_TYPE_*` constants in `eclss_topics.py` (`Ros2EclssBridge` follows these).

---

## Power Granted vs Goal — Interpreting Action Results

### Symptoms

Action returns `SUCCEEDED`, but expected CO₂/O₂ changes do not appear in telemetry. Or feedback shows only "Power granted".

### Cause

The SSOS ECLSS subsystem may depend on EPS power state. With ECLSS headless only and EPS not running, Actions may be accepted but physical effects are limited.

### Fix

1. Consider full-station launch: `ros2 launch space_station space_station.launch.py`
2. Compare `poll_telemetry()` **before and after** the action (smoke report `telemetry_before` / `telemetry_after`)
3. In Phase 1b, treat Sabatier **signal** (`sabatier_signal: true`) as pass criteria — prioritize correlation over absolute values

---

## ros2 CLI Not Found (Host Mac)

### Symptoms

```
ros2 CLI not found on host and docker is unavailable.
```

Or failure when running `PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke` on the host.

### Cause

**Expected behavior.** ROS 2 Jazzy is not installed on the Mac host.

### Fix

Use wrapper scripts:

```bash
./scripts/run_ssos_eclss_smoke.sh
./scripts/run_ssos_eclss_1b_smoke.sh
./scripts/run_ssos_eclss_2_smoke.sh
./scripts/run_ssos_eps_smoke.sh
```

---

## PYTHONPATH Overwrites ROS Workspace

### Symptoms

After running `PYTHONPATH=src python3 ...` inside the container, `ros2` itself breaks / import errors.

### Cause

`PYTHONPATH=src` **assigns** (does not prepend), wiping ROS workspace paths.

### Fix

**Prepend** instead:

```bash
PYTHONPATH=/tmp/engineering_agents/src:${PYTHONPATH} python3 -m scripts.ssos_eclss_ars_smoke
```

Smoke wrappers automatically set `PYTHONPATH='$CONTAINER_REPO/src:'${PYTHONPATH}`.

---

## Empty ros2 Graph

### Symptoms

```
WARNING: ros2 graph is empty — ECLSS may not be running yet.
```

### Cause

ECLSS / station not started in Terminal 1, or discovery not complete immediately after startup.

### Fix

1. Terminal 1: confirm `bash /root/ssos-eclss-headless.sh` is running
2. Inside container: verify graph with `ros2 topic list` / `ros2 action list`
3. Extend smoke `--wait-timeout` (check script arguments)
4. Confirm `ROS_DOMAIN_ID` matches the SSOS startup side (especially for EPS)

---

## Service Call Parse Failure (Jazzy)

### Symptoms

`request_co2` / `request_o2` always return `success=False`, but manual `ros2 service call` succeeds.

### Cause

Jazzy `ros2 service call` output is Python repr, not YAML.

### Fix

`Ros2EclssBridge` parses both formats (fixed in Phase 1b). Use the latest `main` branch.

Manual check:

```bash
ros2 service call /ars/request_co2 space_station_interfaces/srv/Co2Request "{amount: 25.0}"
```

---

## SSOS Container Not Found

### Symptoms

```
SSOS container 'ssos' is not running.
```

### Fix

```bash
docker ps -a | grep ssos
docker start ssos && docker exec -it ssos bash

# If using a different name
SSOS_CONTAINER=my_ssos ./scripts/run_ssos_eclss_smoke.sh
```

---

## EPS: Discharge Not Armed / support_w Is 0

### Symptoms

`request_discharge(100, 3)` returns success but `consume_scheduled_support()` returns 0.

### Cause (Phase 3a interim)

- BCDU has not entered `discharging` mode yet (SSU voltage threshold not met)
- `ROS_DOMAIN_ID` mismatch — cannot read `/bcdu/status`
- EPS launch not running

### Fix

```bash
export ROS_DOMAIN_ID=23   # Match SSOS side
ros2 topic echo /bcdu/status space_station_interfaces/msg/BCDUStatus --once
ros2 topic echo /solar_controller/ssu_voltage_v std_msgs/msg/Float64 --once
```

The bridge uses `current_draw × bus_voltage` as live `support_w` when BCDU is `discharging`. When not discharging, it falls back to the armed value.

---

## Daemon / Zombie Processes

### Symptoms

Stale `ros2 daemon` or headless launch processes cause port conflicts or stale graph references.

### Fix (inside container)

```bash
# Ctrl+C running launch
ros2 daemon stop
ros2 daemon start
# Restart container if needed
docker restart ssos
```

---

## pytest Failures

```bash
pip install -e ".[dev]"
pytest tests/environment/ -v
```

Most tests need no Docker. Expect 2–3 skipped ROS integration tests.

---

## Still Stuck?

1. Check the `errors` array in the smoke report JSON (`--json-out`)
2. Run the relevant Phase’s manual commands inside the container ([ECLSS Integration](eclss-integration.md), [EPS Integration](eps-integration.md))
3. Development memo: [SSOS ECLSS Connection Plan](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)
