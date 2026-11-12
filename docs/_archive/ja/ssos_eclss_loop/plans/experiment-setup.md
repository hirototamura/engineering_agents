# 実験時の環境設定

当時の README に記録したハッカソン環境の手順です。VPN・GPU 使用期間・接続先は当時の条件であり、現在の導入手順は[共通クイックスタート](../../../../ja/users/quickstart.md)を参照してください。以下のコマンドと前提は履歴として保持します。


必要なものは Python 3.11+、Git、ハッカソンで提供されたGPU環境へのVPN接続です。設計エージェントは、VPN越しにGPU上のvLLM endpointへリクエストを送ります。

> 注: GPU/VPNを使う手順は、ハッカソンのGPU使用期間中だけ有効です。期間外に動かす場合は、別途LLM endpointを用意して `agents.yaml` または `--set` で接続先を変更してください。

まずリポジトリを取得し、Python環境を作ります。

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

次に、ハッカソンで配布されたVPNプロファイルでGPU環境へ接続します。接続後、vLLM endpointに届くことを確認します。

```bash
curl http://10.10.0.108:8001/v1/models
```

Windows PowerShell:

```powershell
Invoke-RestMethod http://10.10.0.108:8001/v1/models
```

設計ループを回します。`agents.yaml` の既定設定では、設計エージェントがGPU上のvLLM endpointを使います。

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --iterate 10 --llm-provider vllm
```

1回だけ試す場合:

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --steps 72 --llm-provider vllm
ea results
```

GPU endpointが配布時の値と違う場合は、接続先を明示します。

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --iterate 10 --llm-provider vllm --set agents.design.llm.base_url=http://<GPU_VPN_IP>:8001/v1
```

ダッシュボードを見る:

```bash
python3 -m streamlit run src/tools/dashboard/app.py
```

---
