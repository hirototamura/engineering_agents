# Historical experiment setup

These commands were recorded in the README for the hackathon environment. VPN, GPU availability, and endpoint addresses describe that historical setup. Use the [current quick start](../../../../en/users/quickstart.md) for installation today; the commands and conditions below are retained as history.


You need Python 3.11+, Git, and VPN access to the GPU environment provided for the hackathon. The design agent sends requests over the VPN to the vLLM endpoint running on that GPU.

> Note: the GPU/VPN steps apply only during the hackathon GPU access period. Outside that period, provide another LLM endpoint and update `agents.yaml` or pass an override with `--set`.

First, clone the repository and set up the Python environment.

```bash
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
ea doctor
```

Windows PowerShell:

```powershell
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m tools.cli doctor
```

Next, connect to the GPU environment using the VPN profile provided for the hackathon. After connecting, check that the vLLM endpoint is reachable.

```bash
curl http://10.10.0.108:8001/v1/models
```

Windows PowerShell:

```powershell
Invoke-RestMethod http://10.10.0.108:8001/v1/models
```

Run the design loop. With the default `agents.yaml`, the design agent uses the vLLM endpoint on the GPU.

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --iterate 10 --llm-provider vllm
```

For a single trial run:

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --steps 72 --llm-provider vllm
ea results
```

If the assigned GPU endpoint is different, pass it explicitly.

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --iterate 10 --llm-provider vllm --set agents.design.llm.base_url=http://<GPU_VPN_IP>:8001/v1
```

Open the dashboard:

```bash
python3 -m streamlit run src/tools/dashboard/app.py
```

---
