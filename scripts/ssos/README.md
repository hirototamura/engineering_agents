# SSOS container helpers

Host-side scripts and launch files for the [Space Station OS](https://github.com/space-station-os/space_station_os) Docker image. These files are **volume-mounted into `/root/`** when you create the `ssos` container — they are not part of the upstream image.

Originally maintained under `~/dev/ssos` on the Mac host; canonical copies live here so `ea run ssos_eclss_loop` works without a separate checkout.

## Command cheat sheet (Mac)

### First time: setup through simulation

Once per machine. Run on the **host** (not inside the container).

```bash
cd /path/to/engineering_agents

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

./scripts/ssos/mac/ssos-run-detached.sh

docker ps --filter name=ssos
docker exec ssos test -f /root/ssos-eclss-headless.sh && echo "headless helper OK"

ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

### After setup: simulation only

**Container Up:**

```bash
cd /path/to/engineering_agents
source .venv/bin/activate
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

**Container stopped:**

```bash
docker start ssos
cd /path/to/engineering_agents
source .venv/bin/activate
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

More detail: [docs/ja/cli.md](../../docs/ja/cli.md) · [docs/ja/ssos/quickstart.md](../../docs/ja/ssos/quickstart.md)

## Layout

| Path | Mounted in container | Role |
| --- | --- | --- |
| `ssos-container-setup.sh` | `/root/ssos-container-setup.sh` | Fast DDS discovery, ROS workspace in `.bashrc` |
| `ssos-eclss-headless.sh` | `/root/ssos-eclss-headless.sh` | Start solar + EPS + ECLSS (one launch tree) |
| `ssos-headless.launch.py` | `/root/ssos-headless.launch.py` | Launch file used by headless script |
| `ssos-eps.launch.py` | `/root/ssos-eps.launch.py` | EPS-only headless (no ECLSS) |
| `mac/ssos-run.sh` | — | **Mac**: interactive shell (`-it`) |
| `mac/ssos-run-detached.sh` | — | **Mac**: persistent container for `ea run` |
| `linux/ssos-run-detached.sh` | — | **Linux**: persistent container for `ea run` |
| `windows/ssos-run-detached.ps1` | — | **Windows**: persistent container for `ea run` |

`ea run` uses `scripts/ssos_host_run.sh`, which **stops and restarts** `/root/ssos-eclss-headless.sh` before each simulation so plant state does not leak between runs. That script launches **solar + EPS + ECLSS** — not `eclss.launch.py` alone — so storage topics such as `/co2_storage` publish correctly.

## Mac (Colima / Apple Silicon)

`ssos-run*.sh` starts Colima if Docker is not running (Apple Silicon: `aarch64` VM + Rosetta for `linux/amd64` images).

**Interactive debugging** (shell inside container):

```bash
./scripts/ssos/mac/ssos-run.sh
# inside container:
bash /root/ssos-eclss-headless.sh
```

## Linux

```bash
./scripts/ssos/linux/ssos-run-detached.sh
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
```

Interactive shell: `./scripts/ssos/linux/ssos-run.sh`

## Windows (PowerShell)

```powershell
.\scripts\ssos\windows\ssos-run-detached.ps1
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
```

Interactive shell: `.\scripts\ssos\windows\ssos-run.ps1`

Requires Docker Desktop. Set `SSOS_CONTAINER_NAME` if you use a non-default container name (`ea run` honors `SSOS_CONTAINER` or `SSOS_CONTAINER_NAME`).

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SSOS_CONTAINER` | `ssos` | Target container for `ssos_host_run.sh` / `ea run` |
| `SSOS_CONTAINER_NAME` | `ssos` | Container name when creating via platform runners |
| `SSOS_PLATFORM` | `linux/amd64` | Image platform (`docker pull --platform`) |
| `SSOS_LAUNCH_FILE` | `/root/ssos-headless.launch.py` | Override headless launch file (in container) |
| `SSOS_CONTAINER_DETACHED` | — | Set by `ssos-run-detached.sh`; skips interactive shell in setup |
