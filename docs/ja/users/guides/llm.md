# モデルサービスを接続する

LLM モードには、稼働中で接続可能な Ollama または OpenAI 互換 vLLM サービスと、そのサービスで利用できるモデルが必要です。Engineering Agents のインストールは、これらのサービスの導入や起動を行いません。ローカル ECLSS クイックスタートはラベル付きルールだけで実行できます。

## モデルを使う担当を選ぶ

ECLSS は実行中の actor と実行後の designer を分けます。次の例は運用をルールに固定し、設計に Ollama を使います。

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --actor-mode labeled_rule_base --design-mode llm \
  --llm-provider ollama --llm-model gemma4:e4b \
  --set agents.design.llm.base_url=http://localhost:11434 \
  --steps 20 --run-id local-llm-01 --set iteration.enabled=false --dry-run --json
```

解決された provider・model・URL を確認して dry-run 指定を外します。ECLSS では `--llm-provider` と `--llm-model` は `llm` モードの担当だけに作用します。actor と designer に別サービスを使う場合は URL も分けます。スクラバーは `--agents-mode llm`、キューブは[専用の設計設定](../scenarios/balancing_cube/configuration.md)を使います。

## 接続設定の優先順位

`LLM_PROVIDER` は YAML の provider を上書きします。`OLLAMA_BASE_URL` は Ollama の URL を、`VLLM_BASE_URL`・`VLLM_MODEL`・`VLLM_API_KEY` は vLLM の接続設定を上書きします。全体の vLLM URL は ECLSS の両担当に作用するため、別々の接続先を使う場合は解除してください。

同梱 ECLSS 設定は actor と designer に別の研究室 vLLM を指定し、スクラバーは Ollama を既定とします。共通のモデルを仮定せず、シナリオの設定を確認してください。vLLM には served-model ID を指定します。`:` を含む Ollama タグは vLLM の既定モデルにフォールバックします。vLLM の URL は末尾が `/v1` になるよう正規化されます。

YAML の `api_timeout` は Ollama 用です。vLLM は `VLLM_API_TIMEOUT` がなければ 300 秒のクライアント既定値を使います。`max_concurrency`、メモリ、会話窓、コンテキスト長、出力トークン予算は、速度と応答の完全性に影響します。

## 接続や応答を調べる

`PYTHONPATH=src python -m tools.cli doctor` で報告された URL を確認します。これは環境の報告であり、選んだシナリオの正確なモデルがロード済みという保証ではありません。通常の ECLSS/スクラバー実行は dry-run 判定後に LLM 接続を確認します。提案が壊れている、拒否された、出力されない場合は messages と設計記録を残し、[問題の調査](troubleshooting.md)へ進みます。

## 接続先と役割を分ける

| 設定 | 適用範囲 | 比較時に起こりやすい誤解 |
| --- | --- | --- |
| `--actor-mode` / `--design-mode` | ECLSS の各担当がルール・LLM・無効のどれか | designer も actor と同じでなければならないと思う |
| `agents.actor.llm.*` | ECLSS actor のサービスと生成設定 | actor の遅延調査で designer を変更する |
| `agents.design.llm.*` | 実行後の ECLSS designer | 生成した説明を検証とみなす |
| `VLLM_BASE_URL` / `VLLM_MODEL` | プロセス内の全 vLLM クライアント | 分離した両担当を同じサービスへ意図せず集約する |
| `--llm-model` | CLI で選んだ ECLSS の全 `llm` 担当 | 片側だけが変わると思う |

解決した接続先、保存した議論・提案、測定結果を組にして確認します。モデルと観測期間を同時に変えると、モデルだけの比較にはなりません。
