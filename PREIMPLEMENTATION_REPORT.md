# PREIMPLEMENTATION_REPORT — ECLSS Recursive Subsystem Engineering Agents

**Phase:** 0 — Repository + GPU Preflight（設計書 §57 / §82）
**日付:** 2026-08-16（調査） / 2026-08-21（方針確定・追記）
**調査対象 commit:** `origin/main` = `7092890` "feat(ssos_eclss_loop): schedule ARS/OGS/WRS failures by step (#50)"
**作業ブランチ:** `feat/eclss-recursive-design`（base = `origin/feat/vllm-backend` = main の完全上位集合 + vLLM 4 commit）
**作業ツリー:** `C:\Users\rhagu\Documents\one piece\ea-recursive-design`。既存の `engineering_agents`／`ea-plant-sim` は不変更。push はしない
**判定サマリ:**

| Gate | 判定 | 根拠 |
| --- | --- | --- |
| Phase 0-A（Windows plant_sim smoke） | **PASS** | 406 passed / 4 skipped / 1 failed（既知の Windows path 問題）、plant_sim 閉ループ 72 step 成立、決定論性確認 |
| Phase 0-B（Remote GPU LLM） | **BLOCKED** | VPN 未接続（`Hackathon VPN` = Disconnected）。preflight 実装済・スタブで動作検証済だが実機未確認 |
| Gate 1（physics sensitivity, 設計書 §72） | **CONDITIONAL / 一部 NO-GO** | summary の `peak_co2` 等は設計変数に反応しない。plant_sim ledger を使えば反応する。詳細 §Technical Risks R1 |

**2026-08-21: Q1〜Q6 は全て回答済（§0）。この決定により実装順序が変わり、Gate 0（VPN/GPU）が Phase 1 の前提条件になった。**

---

## 0. 確定した方針（2026-08-21 ユーザー判断）

| # | 論点 | 決定 |
| --- | --- | --- |
| **D1** | 評価シミュレーション中の ECLSS 運転役 | **乗員エージェント（Qwen / LLM）が運転する。採点用の走行も全て LLM 運転。** 固定ルール運転は採用しない |
| **D2** | LLM provider 層 | **`feat/vllm-backend` の上に作る。** 作業ブランチ `feat/eclss-recursive-design` を同 branch base で作成済 |
| **D3** | CReA（Sabatier） | **model default 1.00 のまま変更しない。CReA Agent は advisory（数値を変えずレビューのみ）** |
| **D4** | 環境整備 | venv へ `typer` / `rich` 導入済、`.gitignore` に `*.secrets.*` / `preflight_private.json` 追記済 |
| **D5** | Human Factors | origin 全 branch に実装なし → `human_factors.enabled = false`（§4.2 G8） |

### D1 の帰結（重要）

1. **実装順序が変わる。** 元の「Phase 1 = LLM なしの決定論的評価基盤」は成立しない。
   採点走行そのものが LLM を必要とするため、**Gate 0（VPN → GPU → structured JSON）が Phase 1 の前提条件**になる。
2. **評価が非決定論になる。** 同一設計を 2 回評価しても同じ点数にならない。実装側で以下により吸収する:
   - `temperature = 0` ＋ vLLM の `seed` 固定でブレを抑える（実効性は preflight で実測。
     vLLM は continuous batching のためバッチ構成次第で完全一致は保証されない点に注意）
   - 同一 (design, benchmark case) を **N 回反復**し、中央値と最悪値で判定する
   - 反復間のばらつき（分散）を評価結果に必ず記録し、設計差がノイズに埋もれていないか検証可能にする
   - N の値は GPU の実測 latency / 同時実行数が判明してから決定（**未決事項 P1**）
3. **LLM 呼び出し回数が設計書の想定と 3 桁違う。** 設計書 §74 は
   「1000 physics evaluations ≒ LLM 250 calls」を前提にしているが、D1 では
   1 回の 24h 走行あたり `(乗員数 + 1) × 72` 回。乗員 10 体なら 792 回/走行。
   全体規模（設計案数 × benchmark case 数 × 反復 N）は preflight 後に再計算する（**未決事項 P2**）。
4. **良い副作用: OGS の頭打ち（§7 R4）が解消する。** ルール運転では
   `ogs_goal.input_water_mass = 0.15 kg` が固定で OGS 能力を上げても効果が出なかったが、
   LLM 乗員は水量を自分で決めるためハード能力の差が結果に出るようになる。
5. **`ars_capacity` / `wrs_max_feed` が復活する可能性がある。** §5.3 でこの 2 変数は null 変数だったが、
   原因はルール運転の cadence 依存。LLM 運転下で効くかは Gate 0 通過後に再測定する（**未決事項 P3**）。

### D3 の帰結

能動的に数値を変える Domain Agent は **ARS / OGS / WRS の 3 体**、advisory は **CReA / THC / FDS-WM の 3 体**。
能動的な設計変数は 5 個（`ars_capacity`, `ars_capture_efficiency`, `ogs_capacity`,
`wrs_urine_recovery`, `wrs_grey_recovery`）。うち `ars_capacity` は現時点で null 変数のため、
実効 4 個の可能性がある（P3 で確認）。

### 新規発見 — 【要修正】LLM 乗員に WRS が見えていない

`ssos_eclss_loop_team.py` の `_ECLSS_OPERATIONAL_LEVERS`（LLM に渡す操作メニュー）に載っているのは
`air_revitalisation` / `oxygen_generation` / `request_co2` / `request_o2` の 4 つだけで、
**`water_recovery` が含まれていない。** `_ECLSS_OPERATIONAL_KINDS` は受理するのに、
プロンプト側で存在を教えていないため LLM 乗員は WRS を知らない。
`build_llm_situation()` も `urine_buffer_l`（尿バッファ残量）を乗員へ見せていない。
`origin/feat/vllm-backend` にも同じ穴がある。

D1（全て LLM 運転）では致命的で、水が回収されず単調減少し、**WRS の設計変数 2 個が完全に死ぬ**。
ルール運転では `_labeled_recovery()` が別経路で WRS を発火させていたため表面化していなかった。

→ **Phase 1 の最初のタスクとして修正する**
（operational levers への `water_recovery` 追加 + situation への `urine_buffer_l` 露出）。

### 未決事項（Gate 0 通過後に決める）

| # | 内容 | 必要な入力 |
| --- | --- | --- |
| **P1** | 反復回数 N（同一設計を何回まわして中央値を取るか） | GPU の latency / 同時実行数の実測 |
| **P2** | 乗員エージェント数（4 / 10 / それ以上）と全体の実行時間見積り | 同上 |
| **P3** | `ars_capacity` / `wrs_max_feed` を設計変数として残すか | LLM 運転下での感度再測定 |

---

## 1. Existing Repository Mapping

### 1.1 レイヤ規約（`AGENTS.md` / `docs/ja/AGENTS.md`）

```text
tools → scenario → environment → core
integrations/one_piece ← scenario から呼ぶ
```

- 下位から上位を import しない。**`environment/` に LLM / Persona ロジックを置かない。**
- 最重要原則は「自作自演の禁止」＝ 設計は AI、**仮想世界の合否判定は決定論的チェッカー**が行い LLM に pass/fail を聞かない。
  → 本設計書の「設計AIと評価の分離」は既存 repo の憲法と完全に一致する。矛盾なし。
- 検証要求（threshold）は監督（One Piece / `scenario.yaml`）の正本であり、**設計・検証側が独断で書き換えるのは禁止**と明記済み。
  → 設計書 §10「Verification Requirements は固定する」も既存規約と一致。

### 1.2 該当ソースの実体

| パス | 内容 | 行数規模 |
| --- | --- | --- |
| `src/core/llm/base.py` | `LLMClient` ABC。`generate()` / `check_connection()` / **`generate_async()`（`max_concurrency` semaphore + ThreadPoolExecutor）** | 32 |
| `src/core/llm/ollama.py` | `OllamaClient`。`OLLAMA_BASE_URL` env override、`format:"json"`、model 名からの concurrency 既定値 | 101 |
| `src/core/llm/parsing.py` | `strip_thinking_tags` / `extract_json_block`（最後の balanced object を採用）/ `parse_json_response` → `ok/partial/fallback/empty_response` | 219 |
| `src/core/agents/persona.py` | `TeamConfig`, `PersonaAgent`, `build_personas`, 各種 `*_contract()`（JSON 出力契約文字列）, `deliberate()` | — |
| `src/core/agents/memory.py` | `TeamMemoryStore`（runtime memory。プロセス内・run 単位） | — |
| `src/environment/ssos/eclss/plant_sim/` | `config.py` / `model.py` / `stoichiometry.py` / `backend.py` | 213 / 355 / — / 186 |
| `src/scenario/ssos_eclss_loop/` | `scenario_run.py`(477) / `agents.yaml` / `scenario.yaml` / `health.py` / `policy.py` / `design_proposals.py` / `subsystem_failures.py`(226) / `loop_mock_backend.py` | — |
| `src/scenario/agents/ssos_eclss_loop_team.py` | `SsosEclssLoopTeam`（labeled_rule_base / llm 両モード、運用コマンド発行、post-run design proposal） | 832 |
| `src/scripts/` | 各種 python smoke。**本 Phase で `preflight_remote_llm.py` を追加**（後述） |
| `src/experiments/results/` | run 成果物置き場。`.gitignore` で `src/experiments/results/*` 除外済 |

### 1.3 実行環境

- Python 3.12.13（`engineering_agents\.venv`）。`pyproject.toml` は `requires-python >= 3.11`。
- `pytest` 設定: `testpaths=["tests"]`, `pythonpath=["src"]`, marker `ssos_e2e`。
- run 出力先は `EA_RESULTS_ROOT` env で差し替え可能（`src/scenario/jobs/resolve.py`）。Phase 1 の一時 run はこれで repo 外へ逃がせる。

---

## 2. Existing ECLSS Simulation

### 2.1 `plant_sim` は設計書 §2.1 の記述どおり存在する

`PlantModel`（`model.py`）は純粋な質量収支。ROS / agent 型に依存しない。

| 操作 | 実装 | 主要パラメータ |
| --- | --- | --- |
| Crew metabolism | `advance_step()` | BVAD: CO₂ 1.04 / O₂ 0.84 / 飲用水 2.28 / 尿 1.50 / 凝縮水 0.75 kg/day/人、`crew_size=4`, `activity_factor=1.0` |
| ARS | `run_ars(goal_co2_mass_kg)` | `ars_capacity_kg_day=4.50`, `ars_capture_efficiency=0.83`, `ars_reference_goal_co2_kg=1.80`, `ars_operation_seconds=4800` |
| OGS + Sabatier | `run_ogs(input_water_mass_kg)` | `ogs_max_o2_kg_day=9.25`, `ogs_operation_seconds=1200`, `sabatier_conversion_efficiency=1.00` |
| WRS | `run_wrs(requested_urine_l)` | `wrs_urine_recovery=0.98`, `wrs_grey_recovery=0.90`, `wrs_max_feed_l_per_operation=10.0` |
| Services | `request_o2/co2/product_water`, `submit_grey_water` | — |

**設計書 §2.1 の記述との差分はほぼ無い。** CReA が `run_ogs()` 内の Sabatier 処理である点も記述どおり。

### 2.2 設計変数の注入経路は既に存在する（重要）

`PlantSimConfig.from_scenario_config()` が `scenario.yaml` の `plant_sim:` ブロックを読む。
設計書 §6 `DesignVariableRegistry` の `path` 表記と**そのまま 1:1 対応する**。

| 設計書の variable_id | 設計書の path | 実装上のキー | 存在 |
| --- | --- | --- | --- |
| `ars_capacity` | `plant_sim.ars.capacity_kg_day` | `plant_sim.ars.capacity_kg_day` | ✅ |
| `ars_capture_efficiency` | `plant_sim.ars.capture_efficiency` | 同左 | ✅ |
| `ogs_capacity` | `plant_sim.ogs.max_o2_kg_day` | 同左 | ✅ |
| `sabatier_efficiency` | `plant_sim.sabatier.conversion_efficiency` | 同左 | ✅ |
| `wrs_urine_recovery` | `plant_sim.wrs.urine_recovery` | 同左 | ✅ |
| `wrs_grey_recovery` | `plant_sim.wrs.grey_recovery` | 同左 | ✅ |
| `wrs_max_feed` | `plant_sim.wrs.max_feed_l_per_operation` | 同左 | ✅ |

**現行 `scenario.yaml` には `plant_sim:` ブロックが無い**（default 値で動く）。したがって Phase 1 の design apply は
「overrides に `plant_sim:` を差し込む」だけで既存コードを 1 行も変えずに実現できる。
これは Phase 1 実装の最大の追い風。

### 2.3 Fault injection（設計書 §9 の F1/F2/F3 に対応）

`subsystem_failures.py`（PR #50、main に取り込み済）で step 指定の ARS/OGS/WRS failure を注入できる。

```yaml
inject_failures: true
subsystem_failures:
  - subsystem: ars
    start_step: 20
    end_step: 40      # または duration_steps
```

schedule が所有する subsystem は毎 step 再アサートされるため、agent が failure flag を勝手に解除できない。
**benchmark case F1/F2/F3 は既存機構でそのまま構成できる。**

### 2.4 決定論性

同一 design + 同一 benchmark を 2 回実行し、`peak_co2 / min_o2 / final_water / overall / command_count` が完全一致することを確認済（後述 §5.3）。
設計書 §52 Reproducibility の前提は成立する。

---

## 3. Existing Agent Architecture

### 3.1 既存 Agent は「運用側」であり「設計側」ではない — 設計書 §3 の認識は正しい

`SsosEclssLoopTeam` は各 step で telemetry を見て運用コマンド（`air_revitalisation` / `oxygen_generation` / `water_recovery` / `request_co2` / `request_o2`）を発行する。
モードは `none` / `labeled_rule_base` / `llm` の 3 種。

### 3.2 【最重要の発見】`agents.mode: none` では ECLSS が一切動かない

`PlantSimEclssBackend` は**完全に受動的**である。ARS / OGS / WRS は agent がコマンドを送った時にしか実行されない
（`scenario_run.py:319` `if team is not None:` の中でのみ `apply_outcome` が呼ばれる。`mode: none` では `build_team()` が `None` を返す）。

実測（`--backend plant_sim --agents-mode none --steps 40`）:

```
peak_co2_storage_kg  : 3.55      (critical 2.2 超過)
min_o2_storage_kg    : 0.0       (critical)
final_water          : 46.06 L
operational_command_count : 0
overall              : critical
```

つまり代謝だけが進む開放系になる。
**設計書 §3 / §33 の「Engineering optimization 時は `agents.mode: none` を使う」は、この repo ではそのまま採用できない。**
`none` にすると ARS/OGS/WRS 設計変数の効果がすべて 0 になり、Gate 1（physics sensitivity）が原理的に成立しない。

→ 推奨: **`labeled_rule_base` を「凍結された決定論的運用コントローラ」として benchmark の一部に固定する。**
`labeled_rule_base` は LLM を一切使わず、閾値バンドで動く純ルールなので「設計AIと評価の分離」原則は守られる。
運用 policy（`agents.yaml` の `policy:`）は benchmark 側で凍結し、Engineering Agent からは immutable にする（設計書 §83 論点4 の推奨と整合）。

### 3.3 LLM クライアント

- `LLMClient.generate_async()` が既にあり、設計書 §31 の `asyncio.gather` 並列は**そのまま実装可能**。
- `max_concurrency` は semaphore で効く。設計書 §31.1 の `llm.max_concurrency: 4` は既存機構で表現できる。
- ただし `SsosEclssLoopTeam._build_llm_client()` は **`OllamaClient` を直接 new している**（provider 抽象なし）。

### 3.4 既存 post-run design proposal（`design_proposals.py`）は今回そのまま使えない

`change_kind` は `action_profile` / `service_config` / `set_parameter` / `graph_rewire` の 4 種。

- `action_profile` の対象フィールドは **ARS/OGS/WRS の goal payload（＝運用量）** であり、hardware 設計変数ではない。
- `ALLOWED_SET_PARAMETER_TARGETS` に **`thresholds.co2_storage_high_kg` 等の検証閾値が含まれている**。
  設計書 §10「threshold を自動変更対象から外す」の要求と真っ向から矛盾する。

→ **結論: `design_proposals.py` は Engineering Agent の設計提案チャネルとして再利用しない。** 既存 demo 用にそのまま残し、
新パッケージ側に別の proposal schema + validator を作る（設計書 §11 / §12 の方針で正しい）。

---

## 4. Design Document Gap Analysis

設計書の「現状認識」と `origin/main` (`7092890`) の差分。

### 4.1 設計書が正しかった点

| 設計書の記述 | 実態 |
| --- | --- |
| §2.1 `scenario_run.py` に mock / plant_sim / ros2 の backend 切替がある | ✅ 正しい |
| §2.1 plant_sim に crew / ARS / OGS / CReA / WRS がある | ✅ 正しい |
| §2.1 fault injection がある | ✅ 正しい（さらに step schedule 化済） |
| §2.1 `PersonaAgent` / `TeamMemoryStore` / `LLMClient` / `OllamaClient` / structured JSON parse がある | ✅ 全て存在 |
| §2.1 `design_proposals.py` に 4 種の change kind がある | ✅ 正しい |
| §6 の variable path 表記 | ✅ `PlantSimConfig.from_scenario_config` と 1:1 一致 |
| §43 Sabatier default が 1.0 で CReA に改善余地がない | ✅ 正しい（`sabatier_conversion_efficiency: 1.00`） |
| §31 `LLMClient.generate_async()` がある | ✅ 正しい |

### 4.2 設計書と main の差分（要修正）

| # | 設計書の前提 | main の実態 | 影響 |
| --- | --- | --- | --- |
| **G1** | §3/§33: engineering 評価は `agents: mode: none` で回す | `none` では ARS/OGS/WRS が一切実行されず、設計変数の効果が 0 になる | **Blocker。**Phase 1 の benchmark 定義を変更（Q1） |
| **G2** | §26/§27.1: 「GPU が Ollama なら既存 `OllamaClient` をそのまま使うのが第一候補」 | 未マージ branch **`origin/feat/vllm-backend`（main の 4 commit 先）が既に存在**し、研究室 GPU は **vLLM（OpenAI 互換）**であることを前提にした `VllmClient` + `build_llm_client()` factory + 並列 deliberation + `tests/core/test_vllm.py` を実装済 | **大。**§27.2「Preflight で Ollama でないと判明した場合のみ openai_compatible を追加」は既に半分終わっている。ゼロから書かず branch の再利用を検討（Q2） |
| **G3** | §26: provider / port / model は「確認必須」 | 上記 branch のコードから、研究室 GPU は `gpu-sv-008` = `10.10.0.108`、`:8000/v1` = `qwen3-8b`、`:8001/v1` = `qwen3-32b`、api_key は `dummy` 相当と読み取れる（別 repo `hirototamura/vllm_server`） | 有力な仮説だが**未検証**。VPN 接続後に preflight で実測する（§6） |
| **G4** | §10: threshold は Agent から immutable | 既存 `design_proposals.py` の `set_parameter` は `thresholds.*` を変更可能 | 中。新パッケージでは threshold を許可リストから除外する（実装で対応） |
| **G5** | §73: `.gitignore` に `*.secrets.*` / `preflight_private.json` | 現状 `.gitignore` は `.env` / `.env.*` のみ | 小。Phase 1 で追記推奨 |
| **G6** | §55: Windows path discipline（`/tmp` を埋め込まない） | `tests/scripts/test_ssos_regression_job_spec.py:40` が `/tmp/ea_regression/loop` をハードコードし、**Windows native で失敗する**（既存の main の不具合） | 小。Phase 1 のスコープ外。既知の失敗として扱う |
| **G7** | §2.1「design_proposals の次 run 適用」 | 正しい。加えて #45 で effective config 出力、#48 で 0-based step、#50 で failure schedule が追加済 | 情報更新のみ |
| **G8** | §35 Guinea-pig / Human Factors agents が別 branch にある可能性 | **origin の全 branch を `guinea|cognitive_load|human_factors|mental_state` で grep したが 0 件** | §35.1 に従い `human_factors.enabled = false`。「cognitive load を評価済」とは言わない |
| **G9** | §17 `TeamMemoryStore` は runtime memory としては使える | 正しい。プロセス内・run 単位で永続化なし → SQLite 追加は妥当 | 差分なし |

### 4.3 未マージ branch の棚卸し（Phase 1 で衝突しうる範囲）

| branch | main より先 | 内容 | Phase 1 との関係 |
| --- | --- | --- | --- |
| `origin/feat/vllm-backend` | 4 | vLLM backend / LLM factory / 並列 deliberation / doctor 拡張 | **直撃。**Q2 |
| `origin/cursor/cloud-agent-1786242486932-70m6l` | 13 | dashboard の plant_sim shortfall timing 等 | 低（dashboard 側） |
| `origin/feat/apply-proposal-dashboard` | 5 | dashboard step replay | 低 |
| `origin/cursor/subsystem-failure-schedule-d343` | 7 | failure injection gate（#50 の元枝） | 低（main 取込済） |
| `origin/fix/loop-mock-wrs-backend` | 1 | LoopMock の WRS 実装 | 低（plant_sim には無関係） |
| その他 cursor/* | 1–2 | docs / repo 管理 | 無関係 |

---

## 5. Windows Environment Result

すべて Windows 11 Pro (10.0.26200) native、WSL 不使用、`engineering_agents\.venv`（Python 3.12.13）で実行。

### 5.1 既存テスト

```powershell
python -m pytest --ignore=tests/e2e -q
```

| 結果 | 件数 | 備考 |
| --- | --- | --- |
| collection error | 2 | `tests/tools/test_cli.py`, `tests/tools/test_doctor.py` — **venv に `typer` が未インストール**（`pyproject.toml` の必須依存だが venv に入っていない）。コードの不具合ではなく環境不備 |

`tests/tools` を除外して再実行:

```powershell
python -m pytest --ignore=tests/e2e --ignore=tests/tools -q
→ 1 failed, 288 passed, 4 skipped in 16.73s
```

唯一の失敗:

```
tests/scripts/test_ssos_regression_job_spec.py::test_regression_job_spec_labeled_ros2
  assert '\tmp\ea_regression\loop' == '/tmp/ea_regression/loop'
```

`Path("/tmp/...")` が Windows で `\tmp\...` に正規化されるため。**main 由来の既存 Windows 固有の失敗**であり、テスト側の POSIX 前提の問題（G6）。ECLSS ループ本体には無関係。

### 5.2 plant_sim smoke（設計書 Phase 0-A）

`agents.mode: none`（設計書の推奨どおり）:

| 指標 | 値 |
| --- | --- |
| backend / agents | plant_sim / none |
| steps | 40 |
| peak CO₂ | **3.553 kg**（critical 2.2 超） |
| min O₂ | **0.0 kg**（critical） |
| final water | 46.06 L |
| operational commands | **0** |
| overall | critical |

`agents.mode: labeled_rule_base`, 72 step（= 1200 s × 72 = 24 h）:

| 指標 | 値 |
| --- | --- |
| peak CO₂ | **1.560 kg**（high 1.5 をわずかに超え、critical 2.2 未満） |
| min O₂ | **0.410 kg**（low 0.45 未満 / critical 0.3375 以上 = warning 帯） |
| final water | **48.157 L**（low 50.0 未満 = warning） |
| final health | co2 safe / o2 safe / water **warning** / overall warning |
| operational commands | 59 |
| design proposals | 5 |
| wall time | **1.05 s** |

**Phase 0-A Acceptance = PASS。** Windows native で plant_sim 閉ループが成立する。
1 run 約 1 秒 ⇒ 1000 physics evaluations でも数十分オーダー（設計書 §34 の InProcessPlantSimRunner は当面不要）。

### 5.3 設計変数感度スイープ（Gate 1 事前確認、`labeled_rule_base` / 72 step）

サマリ指標:

```
case                    peak_co2   min_o2   water_l   overall  cmds
baseline                    1.56     0.41     48.16   warning    59
ars_capacity_x0.5           1.56     0.41     48.16   warning    75
ars_capacity_x2.0           1.56     0.41     48.16   warning    51
ars_capture_0.60            1.56     0.41     48.11   warning    59
ars_capture_0.98            1.56     0.41     48.16   warning    59
ogs_capacity_x0.5           1.56     0.00     48.74  critical    69
ogs_capacity_x2.0           1.56     0.40     48.16   warning    58
sabatier_eff_0.80           1.56     0.41     47.80   warning    59
wrs_urine_0.70              1.56     0.41     46.57   warning    59
wrs_maxfeed_3L              1.56     0.41     48.16   warning    59
crew_activity_1.4           1.58     0.34     47.24   warning    82
all_max                     1.56     0.40     48.44   warning    50
F1_ars_failure              2.61     0.41     47.90   warning    72
F2_ogs_failure              1.56     0.00     48.74  critical    71
F3_wrs_failure              1.56     0.41     48.16   warning    74
determinism (baseline ×2, identical metrics): True
```

同じ run の `telemetry.jsonl` 最終行にある plant_sim ledger:

```
case                    co2_vented  h2_vented  ch4_vented  brine_loss  o2_shortfall
baseline                     0.680     0.0162      0.8051      0.3967        0.0
ars_capacity_x0.5            0.680     0.0162      0.8051      0.3967        0.0
ars_capacity_x2.0            0.680     0.0162      0.8051      0.3967        0.0
ars_capture_0.60             1.600     0.0260      0.7857      0.3967        0.0
ars_capture_0.98             0.080     0.0162      0.8051      0.3967        0.0
ogs_capacity_x0.5            0.680     0.0162      0.5475      0.3967      0.5851
ogs_capacity_x2.0            0.680     0.0168      0.8014      0.3967        0.0
sabatier_eff_0.80            0.680     0.0971      0.6441      0.3967        0.0
wrs_urine_0.70               0.680     0.0162      0.8051      1.9833        0.0
wrs_maxfeed_3L               0.680     0.0162      0.8051      0.3967        0.0
all_max                      0.080     0.0168      0.8014      0.1133        0.0
F1_ars_failure               0.5525    0.0746      0.6890      0.3967        0.0
F2_ogs_failure               0.680     0.0162      0.5475      0.3967      0.6026
F3_wrs_failure               0.680     0.0162      0.8051      0.3967        0.0
```

読み取り（Technical Risks R1 の根拠）:

1. **`peak_co2` は設計変数に対して飽和している。** 閾値バンド制御（CO₂ ≥ 1.5 で ARS 起動）なので、peak は「閾値 + 1 step 分の代謝 CO₂」で決まり、ARS 能力では変わらない。ARS 能力は**コマンド回数（75 ↔ 51）にしか出ない**。
2. **`ars_capacity` は現行 benchmark では完全な null 変数。** サマリも ledger も全て同値。閉ループでは総除去量＝総発生量に固定され、能力は cadence を変えるだけ。効くのは transient（故障復旧速度）だけ。
3. **`wrs_max_feed` も null 変数。** 1 step あたりの廃水発生は (1.50 + 0.75) kg/day/人 × 4 人 × 1200 s / 86400 = **0.125 L/step**、trigger 0.5 L で 4 step ごとに約 0.5 L 処理。10 L の batch 上限には決して到達しない。
4. **`ogs_capacity` は勾配でなく崖。** 1 action の O₂ 上限 = 9.25 × 1200/86400 = **0.1285 kg**、必要水 = 0.1285 × 1.126 = **0.1447 kg**。policy の `input_water_mass = 0.15 kg` がこれを僅かに上回るため baseline は**能力律速ぎりぎり**。0.5× で O₂ が 0 に落ち、2× にしても policy 側の 0.15 kg が律速になって改善しない。
5. **ledger 指標は設計変数に明確に反応する。** capture 0.60 → CO₂ vent 1.60 vs 0.98 → 0.08（20 倍）。sabatier 0.80 → H₂ vent 0.0971 vs 1.00 → 0.0162（6 倍）。urine recovery 0.70 → brine 1.98 vs 0.98 → 0.397（5 倍）。
6. **`all_max` は最良ではない**（water 48.44 は baseline 48.16 より良いが min_o2 は 0.40 で悪化）。ただしこれは「真の trade-off が成立している」からではなく「指標が飽和している」ためであり、Gate 2 が通ったとは言えない。
7. **故障ケースは差が出る。** F1 (ARS 20–40 step 停止) で peak CO₂ 2.61（critical 2.2 超）、F2 (OGS 停止) で O₂ 0 / shortfall 0.60 kg。**F3 (WRS 停止) は全指標が baseline と同一** → 現行 seed では WRS 故障ケースは意味を持たない。

---

## 6. Remote GPU / LLM Preflight

### 6.1 実装（本 Phase の成果物）

| 追加ファイル | 役割 |
| --- | --- |
| `src/scripts/preflight_remote_llm.py` | 設計書 §29 の Check 1–6 を実装。**provider を推測せず endpoint に問い合わせて判定**（`GET /v1/models` と `GET /api/tags` を両方叩き、200 を返した方を採用）。`preflight_report.json` を出力 |
| `scripts/windows/preflight_remote_llm.ps1` | 設計書 §29 が指定した Windows native entry point。VPN のプロファイル**状態のみ**表示し、認証情報には触れない・VPN をダイヤルもしない |

設計原則の遵守:

- endpoint は **env のみ**（`EA_LLM_BASE_URL` / `EA_LLM_MODEL` / `EA_LLM_API_KEY`）。**private IP も token も repo に入れていない**（設計書 §73）。
- API key はレポートに `"(set, N chars)"` としか書かない。
- `--host` を渡した場合のみ候補ポート（既定 8000, 8001, 11434）を走査する。
- JSON 判定には既存 `core.llm.parsing.parse_json_response` を再利用（import できない場合は `json.loads` にフォールバック）。
- 出力既定パスは `src/experiments/results/preflight/preflight_report.json`（`.gitignore` 済ディレクトリ）。

### 6.2 実測結果 — **BLOCKED（VPN 未接続）**

```
Get-VpnConnection
Name          ConnectionStatus AuthenticationMethod
Hackathon VPN Disconnected     {Pap}
```

up している NIC は物理 Ethernet と Hyper-V 仮想スイッチのみ。VPN アダプタなし。

`--host 10.10.0.108`（`feat/vllm-backend` 由来の候補アドレス）に対する実行結果:

| Check | 結果 |
| --- | --- |
| 1. Python | ✅ 3.12.13 / Windows-11-10.0.26200-SP0 |
| 2. ICMP ping | ❌ returncode 1（参考値） |
| 3. TCP 8000 / 8001 / 11434 | ❌ 全て `TimeoutError: timed out` |
| 4–6 | 未実行（3 で打ち切り） |
| overall | `overall_ok: false`, blocking = "No TCP port open … Is the VPN connected and the LLM server running?" |

### 6.3 preflight 自体の妥当性検証（スタブによる happy path）

VPN が無い状態でツールの正しさを担保するため、ローカルに OpenAI 互換のスタブサーバ（scratchpad、repo 外）を立てて全 6 チェックを通した:

```
4_health : provider = openai_compatible, api_base = .../v1, models = ["stub-qwen3-8b"]
5_structured_json : ok = true, parse_status = "ok", response = {"ok": true}
6_parallel : concurrency 4, success 4/4, malformed 0, latency min/median/max = 160.4 / 162.3 / 164.6 ms, wall 0.168 s
overall_ok : true, gate_0_remote_llm : "GO"
```

**preflight の実装は動作する。残っているのは実機（VPN + GPU）での実行のみ。**

### 6.4 ユーザーが VPN 接続後に実行するコマンド

```powershell
# 1) VPN を接続（Hackathon VPN, PAP）
# 2) 候補ポート走査モード
$env:PYTHONPATH = "C:\Users\rhagu\Documents\one piece\ea-recursive-design\src"
& "C:\Users\rhagu\Documents\one piece\engineering_agents\.venv\Scripts\python.exe" `
  "C:\Users\rhagu\Documents\one piece\ea-recursive-design\src\scripts\preflight_remote_llm.py" `
  --host 10.10.0.108 --concurrency 4

# もしくは endpoint が分かっている場合
$env:EA_LLM_BASE_URL = "http://10.10.0.108:8000/v1"
$env:EA_LLM_MODEL    = "qwen3-8b"
.\scripts\windows\preflight_remote_llm.ps1
```

exit code 0 = Gate 0 GO、1 = NO-GO。

### 6.5 provider / model の現時点の推定（**未検証**）

未マージ branch `origin/feat/vllm-backend` の `src/core/llm/vllm.py` docstring より:

| 項目 | 推定値 | 確度 |
| --- | --- | --- |
| provider | vLLM（OpenAI 互換 `/v1/chat/completions`） | 高（コードと別 repo `hirototamura/vllm_server` の記述） |
| host | `gpu-sv-008` = `10.10.0.108`（VPN / LAN 限定） | 高 |
| port / model | `:8000` → `qwen3-8b`（日常）、`:8001` → `qwen3-32b`（重い判断） | 高 |
| auth | Bearer、既定 `dummy`（実質認証なし） | 中 |
| 同時実行 | branch の既定値は 8B が 100、32B が 32（8B は 6-way replicated で理論値 ~384） | 中（実測必須） |
| latency / JSON mode | 不明 | **未確認** |

設計書 §81-13「GPU server API を推測しない」に従い、**この推定は preflight 実測まで実装判断の根拠にしない。**

---

## 7. Technical Risks

### R1 — 【最大】現行の評価指標では設計変数が効かない（Gate 1 / Gate 2）

- 閾値バンド制御の閉ループでは `peak_co2` / `min_o2` / `final_water` が飽和し、`ars_capacity` と `wrs_max_feed` は完全な null 変数（§5.3）。
- このまま optimization を始めると Engineering Agent は「効かない変数をいじり続ける」ことになり、PoC が成立しない。
- **Mitigation:**
  1. 指標を summary ではなく **plant_sim ledger（`telemetry.jsonl` の `raw_topics.plant_sim.total_*`）から算出**する。CO₂ vent / H₂ vent / brine loss / O₂ shortfall / water shortfall は明確に反応する。
  2. 時間積分系指標を追加（`time_above_co2_high`、`integral_co2_exceedance`、`failure_recovery_steps`、`total_operational_commands` = 運用負荷 proxy）。
  3. 故障・高負荷ケースを benchmark の主戦場にする（`ars_capacity` は F1 の復旧速度でのみ効く）。
  4. Phase 1.5 Calibration（設計書 §59）を**省略しない**。null 変数は registry から外すか bounds を変える。

### R2 — Remote LLM が未確認（設計書 §72 Gate 0）

VPN 未接続のため provider / latency / concurrency / JSON 安定性が全て未実測。
設計書 §72「Remote LLM provider を確定するまで Agent 開発を進めない」に従い、**Phase 2 以降は Gate 0 通過まで着手しない**。
なお Phase 1（LLM 不使用の決定論的評価基盤）は Gate 0 と独立に進められる。

### R3 — `agents.mode: none` 前提の崩れ

§4.2 G1。benchmark 定義が設計書と変わるため、「運用 policy を何で凍結するか」を決めないと再現性の根拠が崩れる。

### R4 — 運用 policy と hardware 設計の交絡

`ogs_goal.input_water_mass = 0.15` は 24 h shakeout 用に手で合わせた値であり（`agents.yaml` のコメントに「SHAKEOUT tuning」「B4」と明記）、
**OGS 能力 2 倍にしても policy が律速して効果が出ない**（§5.3-4）。
policy を凍結すると OGS 設計変数の上側が死に、policy も可変にすると「control tuning になる」（設計書 §83 論点4 の懸念）。
**Mitigation:** OGS の 1 action あたり水量を「ハード能力に比例する従属変数」として benchmark 側で決定論的に導出する案を Phase 1.5 で検討（要ユーザー判断 = Q3）。

### R5 — F3 (WRS failure) が現行 seed では無意味

WRS を 20 step 止めても全指標が baseline と同一（§5.3-7）。水の在庫が十分厚く、復旧後に取り戻せるため。
**Mitigation:** seed の初期水量を下げる / 停止 window を延ばす / 水指標を積分系にする。Phase 1.5 Calibration で調整。

### R6 — `python -m` 実行時の import 経路事故（Windows 固有・実害あり）

venv には `engineering-agents` が **`C:\Users\rhagu\Documents\one piece\engineering_agents`（＝未コミット 22 ファイルを抱えた別ワークツリー）** に editable install されている。

```
> python -c "import core; print(core.__file__)"
C:\Users\rhagu\Documents\one piece\engineering_agents\src\core\__init__.py   ← 別ツリー
```

`pytest` は `pythonpath=["src"]` を前置するので worktree 側が勝つ（検証済）が、
**`python -m ...` や `ea` コマンドを素で叩くと汚れた別ツリーのコードが動く。**
**Mitigation:** 本作業では常に `PYTHONPATH=<worktree>\src` を明示する。Phase 1 の run スクリプト／ドキュメントにも明記する。

### R7 — venv の依存欠落

`typer` が未インストールで `tests/tools` が collection error（§5.1）。`pyproject.toml` の必須依存なので環境側の不備。
**Mitigation:** `pip install -e ".[dev]"` の再実行、または `pip install typer rich`。ユーザー環境の変更になるため未実施（Q5）。

### R8 — Sabatier / WRS の headroom（設計書 §43 / §44）

`sabatier_conversion_efficiency` の default が 1.00 のため CReA Agent に「上げる余地」がない。
実測では 0.80 に下げると H₂ vent が 6 倍になり **下げ方向には明確に効く**ので、
設計書 §43 推奨案 A（experiment seed のみ 0.8–0.9 に下げ、model default は変えない）は妥当。ユーザー承認事項（Q4）。

### R9 — 秘匿情報の取り扱い

VPN 認証情報は一切読んでいない・コピーしていない・commit していない。
ただし `.gitignore` は `.env` / `.env.*` のみで、設計書 §73 の `*.secrets.*` / `preflight_private.json` は未登録（G5）。Phase 1 で追記推奨。

---

## 8. Recommended Phase 1 Implementation

設計書 §58 Phase 1（LLM なし、決定論的 design evaluation）。**既存 `ssos_eclss_loop` を一切変更しない**方針で構成できる。

### 8.1 新規追加（すべて新規パッケージ内）

```text
src/scenario/eclss_recursive_design/
├─ __init__.py
├─ design_space.yaml          # DesignVariableRegistry（§6）+ bounds（relative_to_baseline）
├─ benchmark.yaml             # N0/N1/F1/F2/F3 + verification thresholds（immutable）
├─ baseline_seed.yaml         # §42 の seed（model default は変更しない）
├─ schemas.py                 # Design / Evaluation / SimulationResult dataclass
├─ variable_registry.py       # variable_id → plant_sim path 解決、owner、bounds、mutable 判定
├─ design_validator.py        # bounds / NaN / immutable / ownership / resource budget
├─ resource_index.py          # §7.1 dimensionless Design Resource Index
├─ simulation/
│  ├─ base.py                 # DesignSimulationRunner Protocol（§32）
│  └─ scenario_runner.py      # ScenarioRunnerAdapter（§33）: SsosEclssLoopScenario を overrides で呼ぶ
└─ evaluation/
   ├─ metrics.py              # telemetry.jsonl + plant_sim ledger から決定論的に指標算出
   ├─ verification.py         # hard pass/fail（閾値は benchmark.yaml から。Agent 不可変）
   ├─ benchmark_runner.py     # 1 design × N cases
   └─ pareto.py               # §41 archive（Phase 4 と共用）
```

```text
tests/scenario/eclss_recursive_design/
  test_variable_registry.py
  test_design_bounds.py            # 契約テスト C（budget 超過を reject）
  test_resource_index.py
  test_verification_freeze.py      # 契約テスト B/F（threshold 変更を reject）
  test_benchmark_runner.py
  test_determinism.py              # 契約テスト D（同一 design → 同一 physics）
```

### 8.2 既存ファイルへの変更 — **原則ゼロ**

`ScenarioRunnerAdapter` は次の形で既存 API だけを使う（新規コードは追加、既存は不変）:

```python
SsosEclssLoopScenario().run(
    overrides={
        "backend": {"kind": "plant_sim"},
        "agents":  {"mode": "labeled_rule_base"},   # ← Q1 の決定に依存
        "simulation": {"steps": 72},
        "plant_sim": {                               # ← design を注入
            "ars": {"capacity_kg_day": ..., "capture_efficiency": ...},
            "ogs": {"max_o2_kg_day": ...},
            "sabatier": {"conversion_efficiency": ...},
            "wrs": {"urine_recovery": ..., "grey_recovery": ...,
                    "max_feed_l_per_operation": ...},
        },
        "inject_failures": True,                     # benchmark case ごと
        "subsystem_failures": [...],
    },
    run_id=f"eclss-rd-{design_id}-{case}",
    results_root=<experiment dir>,
)
```

指標は返ってきた `run_dir` の `telemetry.jsonl` / `health_metrics.jsonl` / `summary.json` から**決定論的 Python 関数**で算出する（LLM は関与しない）。

**唯一検討に値する既存変更:** `plant_sim` ledger 合計を `summary.json` にも出す小改修。
ただし Phase 1 では `telemetry.jsonl` を読めば足りるので、**設計書 §81-4「既存 ssos_eclss_loop を壊さない」を優先して見送りを推奨**。

### 8.3 Phase 1 の Acceptance（設計書 §58）に対する具体化

| 設計書の Acceptance | Phase 1 での検証方法 |
| --- | --- |
| Design A / B で物理結果が変わる | capture 0.60 vs 0.98 で CO₂ vent 1.60 vs 0.08（§5.3 で実測済） |
| benchmark が自動 run | N0/N1/F1/F2/F3 の 5 case を 1 コマンドで |
| hard pass/fail 出力 | `verification.py` が benchmark.yaml の閾値のみ参照 |
| immutable benchmark enforcement | `test_verification_freeze.py` |

### 8.4 Phase 1.5 Calibration で必ず確認すること（§5.3 の結果を受けて）

1. `ars_capacity` / `wrs_max_feed` を registry に残すか外すか（現状 null 変数）。
2. F3 (WRS failure) が差を生む seed へ調整。
3. `sabatier_conversion_efficiency` の seed 値（Q4）。
4. resource index の重みが「全部最大が唯一解」にならないこと（設計書 Gate 2）。

### 8.5 Phase 2 以降の前提

Gate 0（remote LLM）通過後に着手。LLM provider 層は Q2 の決定に従う。

---

## 9. Questions / Decisions Required（2026-08-21 全て回答済 — 結論は §0 参照）

> 以下は 2026-08-16 時点の設問と当時の推奨案。**確定した決定は §0 の表が正本**。
> Q1 は推奨案 A ではなく「採点走行も含め全て LLM 運転」に、
> Q4 は推奨案 A ではなく「100% 据え置き + CReA を advisory 化」に決定した。

### Q1 — 【Blocker】design evaluation 時の `agents.mode` をどうするか

`mode: none` では ARS/OGS/WRS が一切動かず（CO₂ 3.55 / O₂ 0.0）、設計変数の効果が測れない（§3.2）。

| 案 | 内容 | 評価 |
| --- | --- | --- |
| **A（推奨）** | `labeled_rule_base` を「凍結された決定論的運用コントローラ」として benchmark に固定。`agents.yaml` の `policy:` は benchmark 側でスナップショットして immutable 化 | LLM を使わないので「設計AIと評価の分離」は保たれる。既存資産をそのまま使える |
| B | plant_sim に自律運用ロジックを追加（backend が自分で ARS/OGS/WRS を回す） | physics 層に制御を入れると層責務が濁る。既存 `ssos_eclss_loop` の挙動とも乖離 |
| C | `mode: none` のまま「無制御時の耐久性」を評価 | 全 design が fail し optimization が成立しない |

→ **A を推奨。承認をお願いします。**

### Q2 — 【Blocker】LLM provider 層をどう調達するか

`origin/feat/vllm-backend`（main の 4 commit 先）に `VllmClient` / `build_llm_client()` factory / 並列 deliberation / テスト一式が既にある。

| 案 | 内容 | 評価 |
| --- | --- | --- |
| **A（推奨）** | Gate 0 で vLLM と確定したら `feat/vllm-backend` を main に取り込む（またはその上に Phase 1 を積む）ようチームに依頼 | 重複実装ゼロ。設計書 §46「core 変更は最小」と整合 |
| B | 新パッケージ内に独自の provider adapter を書く | `src/core/llm/` に将来 2 実装が並ぶ。§46 に反する |
| C | Phase 1 は LLM 不使用なので判断を Phase 2 まで先送り | 進行は可能。ただし Q2 は結局必要 |

→ **A を推奨。ただしまず VPN 接続 → preflight で「本当に vLLM か」を確定させたい。**

### Q3 — 運用 policy をどこまで凍結するか（設計書 §83 論点4）

`ogs_goal.input_water_mass = 0.15` を凍結すると OGS 能力を上げても効果が出ない（§7 R4）。

| 案 | 内容 |
| --- | --- |
| **A（推奨）** | 運用 policy は完全凍結。OGS の上側 headroom は benchmark 側（高負荷 N1 / 故障 F2）で作る |
| B | 1 action あたり水量をハード能力から決定論的に導出する（`input_water_mass = f(ogs_max_o2_kg_day)`）。設計変数を変えると運用量も追随する |
| C | 運用 policy も Engineering Agent の設計変数にする |

→ A で開始し、Phase 1.5 Calibration の結果次第で B を検討、を推奨。C は「control tuning 化」するため非推奨。

### Q4 — CReA seed（設計書 §83 論点7、要承認）

`sabatier_conversion_efficiency` の default は 1.00 で改善余地なし。
**推奨: `baseline_seed.yaml` でのみ 0.85 程度に下げる。`PlantSimConfig` の default（1.00）は変更しない。** ご承認をお願いします。

### Q5 — 環境・ブランチの取り扱い

1. **worktree の場所** — `C:\Users\rhagu\Documents\one piece\ea-recursive-design`（`origin/main` detached）で作業してよいか。既存の `engineering_agents`（`hagura/windows-setup` の未コミット 22 ファイル）と `ea-plant-sim` には触れていません。
2. **ブランチ名** — Phase 1 用に切るブランチ名の希望（例 `feat/eclss-recursive-design`）。現在 Phase 0 の追加 2 ファイルは detached HEAD 上で未コミットのままです。
3. **venv の `typer`** — `tests/tools` を通すために `pip install typer rich`（または `pip install -e ".[dev]"` 再実行）してよいか。**ユーザー環境の変更になるため未実施です。**
4. **`.gitignore`** — 設計書 §73 に従い `*.secrets.*` / `preflight_private.json` を追記してよいか。

### Q6 — Human Factors / Guinea-pig（設計書 §35、情報共有）

origin の全 branch を grep しましたが `guinea` / `cognitive_load` / `human_factors` / `mental_state` は **0 件**でした。
設計書 §35.1 に従い **`human_factors.enabled = false`** で進め、「cognitive load を評価済み」とは表現しません。
別 repo / 未 push の実装があればご教示ください。

---

## 10. Phase 0 Deliverables

| 成果物 | 場所 |
| --- | --- |
| 本レポート | `PREIMPLEMENTATION_REPORT.md`（repo root） |
| preflight 実装（Python） | `src/scripts/preflight_remote_llm.py` |
| preflight 実装（Windows entry point） | `scripts/windows/preflight_remote_llm.ps1` |
| preflight_report.json（VPN down 時） | scratchpad（repo 外）。VPN 接続後に再実行して repo の `src/experiments/results/preflight/` へ出力予定 |
| 感度スイープの生データ | scratchpad（repo 外、throwaway） |

**Phase 1 以降には着手していません。** Q1〜Q5 のご回答をお待ちします。
