# #64 改良実装仕様書
## Design Decision Loop / DesignState / Candidate Pipeline / Integrity + Physics Gate

作成日: 2026-08-29

## 1. 背景

#64の現行実装では、LLMが設計判断だけでなく、次に呼ぶtoolの選択、証拠収集の順序管理、constraint確認、candidate simulation、比較、終了判断まで担っている。

参照会話で確認したログ上の問題は以下。

- 約15分経過してcandidateが1本しか生成されていない
- `evaluate_design_constraints` が少なくとも7回繰り返し呼ばれている
- `compare_design_runs` が複数回呼ばれている
- `empty_response` が複数回発生している
- `no tool call` が発生している
- Evidence Gateは「必要証拠が揃ったか」を見るだけで、「既に済んだtoolを再実行しているか」は止められない
- 過去tool resultを毎turn promptへ再投入しており、contextとcompletion budgetの両方を圧迫している

根本原因は、LLMに「何を設計するか」と「作業手順をどう進めるか」を同時に任せていることにある。

## 2. 改良の目的

今回の変更では、#64の基本思想をさらに明確化する。

```text
LLM
  = 設計判断だけを行う

Python
  = 調査、検証、simulation、評価、比較、workflow管理を行う
```

つまり、LLMには「次にどのtoolを呼ぶか」を選ばせない。LLMは現在状態を読み、candidateを提案するか、終了するかだけを返す。

## 3. 非目標

以下は今回やらない。

- INSTRUMENTにある7種類の攻撃を毎回流す回帰テストの追加
- Evaluation総合点をDesign Rankingの目的関数にする
- LLMにphysics validityやscoreを計算させる
- LLMの文章を設計値の正本にする
- Survivalとmass/costを単一weighted scoreで交換可能にする
- INSTRUMENTのA-D配点方式をそのまま移植する

## 4. 改良後の全体フロー

```text
Pristine scenario / agents config
        |
        v
Scoring Integrity Guard
  - pristine vs effective config
  - scoring_bar_modified
  - operating_point_modified
  - arm_modified
        |
        v
Baseline Simulation
        |
        v
Telemetry-only Physics Gate
  - finite / non-negative
  - monotonic totals
  - C/O2/H2O ledger
  - stoichiometry
  - failure quiescence
  - capacity bounds
        |
        v
#62系 Deterministic Evaluator
  - survival
  - TCL
  - environment
  - resource recovery
  - actor decision
  - device response
        |
        v
Deterministic Evidence Builder
  - artifacts
  - timeseries
  - ECLSS features
  - theoretical capacity
  - evaluation diagnosis
  - physics / integrity result
        |
        v
DesignState生成
        |
        v
LLM Design Decision
  - propose_candidate
  - finish
        |
        v
Candidate Pipeline
  - validate fields
  - constraints
  - Integrity Guard
  - simulation
  - Physics Gate
  - Evaluator
  - candidate outcome
  - deterministic comparison
        |
        v
DesignState更新
        |
        v
LLM review or finish
        |
        v
Deterministic Final Ranking
```

Evaluatorの総合点をDesign Rankingに使わない、という現行#64の原則は維持する。

## 5. Tool-use LoopをDesign Decision Loopへ置き換える

現在のようなtool-use loopを廃止する。

```text
LLM -> load artifacts
LLM -> summarize
LLM -> theory
LLM -> propose
LLM -> constraint
LLM -> constraint
LLM -> constraint
...
```

改良後は、以下のtoolをLLMから直接呼べないようにする。

- `load_run_artifacts`
- `summarize_timeseries`
- `compute_eclss_features`
- `compute_theoretical_capacity`
- `evaluate_design_constraints`
- `run_design_candidate`
- `compare_design_runs`

これらはPython側のdeterministic serviceとして再編する。

LLMが返すJSONは2種類だけにする。

### Candidate提案

```json
{
  "decision": "propose_candidate",
  "rationale": "ARSとOGSが不足しており、CO2 critical dwellとO2 shortageを同時に解消するため容量を増やす。",
  "fields": {
    "plant_sim.ars.capacity_kg_day": 10.2,
    "plant_sim.ogs.max_o2_kg_day": 8.4,
    "plant_sim.wrs.max_feed_l_per_operation": 4.5
  }
}
```

### 終了

```json
{
  "decision": "finish",
  "rationale": "candidate_2がfull survivalを満たし、critical dwellを解消しつつmassが最小である。",
  "selected_candidate_id": "candidate_2"
}
```

LLM出力から以下を削除する。

- `task_plan`
- `tool_call`
- tool name
- evidence completion self-report
- comparison score self-report

## 6. DesignStateを導入する

履歴そのものをLLMへ戻さない。毎回、Python側で最新状態を1個のJSONへ再構成し、LLMにはそれだけを渡す。

例:

```json
{
  "baseline": {
    "crew": {
      "initial": 50,
      "remaining": 0
    },
    "physics_gate": "passed",
    "bottlenecks": ["ars", "ogs"],
    "critical_dwell": {
      "co2": 41,
      "o2": 18,
      "water": 0
    }
  },
  "theoretical_capacity": {
    "ars": {
      "required_kg_day": 60.5,
      "installed_kg_day": 18.0
    },
    "ogs": {
      "required_kg_day": 44.2,
      "installed_kg_day": 12.0
    },
    "wrs": {
      "required_l_operation": 8.0,
      "installed_l_operation": 4.0
    }
  },
  "candidates": [
    {
      "candidate_id": "candidate_1",
      "fields": {
        "plant_sim.ars.capacity_kg_day": 62.0
      },
      "crew_remaining": 50,
      "physics_gate": "passed",
      "constraints": "passed",
      "critical_dwell": {
        "co2": 6,
        "o2": 0,
        "water": 0
      },
      "mass_kg": 3200.0,
      "volume_m3": 22.4,
      "cost_musd": 18.7
    }
  ],
  "current_best": "candidate_1",
  "remaining_candidate_budget": 3,
  "decision_needed": "refine_or_finish"
}
```

DesignStateの目的は、LLMが過去のtool結果を読み返す必要をなくすこと。これにより、「turn 6でconstraintを確認したことをturn 15で忘れる」問題を構造的に消す。

`tool_trace.jsonl`は削除しない。ただし、LLMへの入力ではなく、人間向け監査ログとしてのみ残す。

## 7. Candidate Pipelineを完全自動化する

LLMがcandidate fieldsを返した瞬間に、コード側で必ず以下を実行する。

```text
candidate fields
  |
  v
design variable validation
  |
  v
engineering constraints
  |
  v
Integrity Guard
  |
  v
candidate simulation
  |
  v
Physics Gate
  |
  v
Evaluator
  |
  v
design outcome
  |
  v
all candidates comparison
  |
  v
DesignState update
```

これにより、LLMが `evaluate_design_constraints` を何度も呼ぶ余地をなくす。

また、candidate fieldsを正規化してhash化する。

```text
同じ設計値
  -> candidate simulationを再実行しない
  -> 既存candidate outcomeを再利用する
```

正規化時は以下を揃える。

- field pathのsort
- numeric valueの丸め粒度
- default valueとの差分のみ保存
- semanticに同一なcandidateを同一hashへ集約

## 8. LLM呼び出し回数

現在の `max_tool_iterations` は廃止する。

新しい基本上限:

```text
Initial design      1回
Candidate 1 review  1回
Candidate 2 review  1回
Candidate 3 review  1回
Candidate 4 review  1回
```

最大5 design decisionsを標準とする。

設定例:

```yaml
tool_use:
  enabled: true
  max_candidate_runs: 4

  decision_loop:
    max_decisions: 5
    max_parse_retries: 1
```

## 9. Parse Failure / Empty Responseの扱い

新仕様では、parse failureやempty responseで長いloopを続けない。

```text
LLM request
  |
  v
empty / malformed
  |
  v
short repair promptで1回だけretry
  |
  v
再度失敗
  |
  v
state-aware deterministic fallback
```

重要なのは、fallback時に証拠収集を最初からやり直さないこと。

candidateがまだ0本の場合:

- theoretical capacityから1.15 margin程度のcandidateを生成する
- そのcandidateを通常のCandidate Pipelineへ送る

candidateが既に存在する場合:

- 既存candidateを捨てない
- `current_best` と `remaining_candidate_budget` から続行する
- 続行不能なら、その時点のbestを採用候補としてfinal rankingへ渡す

## 10. LLM Prompt Context

promptは以下の4ブロックだけにする。

```text
1. Expert Context Pack
2. Current DesignState
3. Design objective
4. Output JSON schema
```

過去のtool result一覧は入れない。

LLMは「過去を読む」のではなく、「現在状態を見る」方式にする。

## 11. Scoring Integrity Guard

INSTRUMENTで確認された重要な問題は、良い設計を作る代わりに採点基準自体を緩めれば良く見えてしまうこと。特にthreshold変更だけで、物理状態が改善していないのに評価が改善する余地がある。

新規ファイル:

```text
src/scenario/ssos_eclss_loop/integrity_guard.py
```

run開始前に、以下を比較する。

```text
pristine config
vs
effective config
```

返却例:

```json
{
  "scoring_bar_modified": false,
  "operating_point_modified": true,
  "arm_modified": false,
  "changed_paths": {
    "scoring_bar": [],
    "operating_point": [
      "plant_sim.ars.capacity_kg_day"
    ],
    "arm": []
  }
}
```

### 11.1 scoring_bar_modified

以下の変更は評価証拠として無効にする。

```text
thresholds/**
plant_sim.survival/**
plant_sim.habitat/**
simulation.initial_o2_storage_kg
plant_sim.crew/**
```

`scoring_bar_modified=true` のrunは、simulation自体は保存してよいが、評価・設計比較の証拠としては `invalid` にする。

### 11.2 operating_point_modified

記録のみ。candidateによるARS/OGS/WRS capacity変更はここに入る。

例:

```text
plant_sim.ars.capacity_kg_day
plant_sim.ogs.max_o2_kg_day
plant_sim.wrs.max_feed_l_per_operation
```

### 11.3 arm_modified

agents policy等の変更。これも記録のみ。

### 11.4 実装方針

Guardの比較は個別field列挙ではなく、部分木diffで実装する。field列挙方式は隣接fieldの変更を取りこぼしやすいため。

## 12. Telemetry-only Physics Gate

現行#64にもPhysics Gateはあるが、scenario configも参照している。改良後は、`telemetry.jsonl` だけから判定する独立監査をcanonical implementationにする。

新規ファイル:

```text
src/scenario/ssos_eclss_loop/physics_gate.py
```

チェックは9種類。

```text
1. readings_present_and_finite
2. inventories_non_negative
3. totals_monotonic
4. carbon_ledger
5. oxygen_ledger
6. water_ledger
7. stoichiometric_residual
8. failure_quiescence
9. capacity_bounds
```

各checkは以下を返す。

```json
{
  "name": "oxygen_ledger",
  "status": "passed",
  "reason": null,
  "details": {}
}
```

測定不能な場合はpassにせず、`skipped` と理由を返す。

Physics Gate全体のstatus:

```text
failed
  1個でもfailed

incomplete
  failedはないがskippedあり

passed
  全項目passed
```

Design candidateの最終採用資格は `passed` のみ。

## 13. Telemetry追加

Physics Gateをconfig非依存にするため、監査に必要な値をtelemetryへ残す。

最低限、以下を各stepまたはrun開始時snapshotとして保存する。

- subsystem failure state
- subsystem busy state
- installed capacity snapshot
- operation processed quantity
- cumulative resource totals
- cumulative crew generation/consumption

依存方向は以下に固定する。

```text
simulator
  -> telemetry
  -> independent Physics Gate
```

Physics Gateからscenario configやagent configへ逆参照しない。

## 14. Evaluator統合

#62由来のEvaluatorは基本的に維持する。

維持する評価軸:

- survival
- TCL
- environment trajectory
- resource recovery
- actor decision
- device response

ただしEvaluatorは、先にIntegrity GuardとPhysics Gateを確認する。

```text
scoring_bar_modified
  -> evaluation.status = invalid

Physics failed / incomplete
  -> evaluation.status = invalid
```

INSTRUMENTのA-D配点方式そのものは取り込まない。理由は、Cに逆インセンティブがあり、Dはほぼ定数で、O2/水軸の感度不足があるため。

## 15. Design Ranking

Evaluation total scoreはrankingに使用しない。

Design eligibility:

```text
preflight valid
AND candidate simulated
AND Integrity Guard valid
AND Physics Gate passed
AND Design Evidence complete
AND crew_remaining == crew_initial
AND engineering bounds内
```

Ranking priority:

```text
1. final_eligible
2. crew_remaining
3. critical dwell
4. warning dwell
5. total_mass_kg
6. total_volume_m3
7. total_cost_musd
8. environment terminal margin / tie break
```

重要なルール:

```text
full survivalを達成していないcandidateが、
Evaluation scoreの高さによってfull-survival candidateを逆転してはいけない。
```

## 16. 保存Artifact

runごとに最低限、以下を保存する。

```text
summary.json
scenario_config.yaml
agents_config.yaml

run_integrity.json
physics_gate.json

evaluation.json
evaluation.html

design_state.json
tool_trace.jsonl
design_proposals.json
```

`evaluation.json`にも、IntegrityとPhysics Gateの要約を埋め込む。

```json
{
  "integrity": {
    "scoring_bar_modified": false,
    "operating_point_modified": true,
    "arm_modified": false
  },
  "physics_gate": {
    "status": "passed"
  }
}
```

## 17. 主な変更ファイル

```text
src/scenario/agents/
  ssos_tool_use_design.py
    - Tool loopをDesign Decision Loopへ変更
    - LLM output schemaをpropose_candidate / finishに限定
    - parse retryとstate-aware fallbackを実装

src/scenario/ssos_eclss_loop/
  design_tools.py
    - LLM tool catalogではなくdeterministic servicesとして整理
    - evidence collection / candidate execution / comparisonを内部API化

  design_state.py
    - NEW
    - DesignState生成
    - compact serialization
    - current_best更新
    - remaining budget管理

  integrity_guard.py
    - NEW
    - pristine/effective config比較
    - scoring_bar / operating_point / arm分類
    - 部分木diff

  physics_gate.py
    - NEW
    - telemetry-only 9 physics checks
    - passed / incomplete / failed判定

  evaluation.py
    - 内蔵physics処理をphysics_gate.pyへ委譲
    - Integrity Guard / Physics Gateを先に確認
    - invalid statusを明確化

  unified_evaluation.py
    - Integrity + Physics + Evaluator統合の薄い入口
    - baseline/candidate共通の評価入口

  scenario_run.py
    - pre-run Integrity Guard追加
    - baseline simulation後にPhysics Gate / Evaluatorを実行
    - candidate runでも同じ評価artifactを生成

  agents.yaml
    - max_tool_iterations削除
    - decision_loop設定追加
```

## 18. テスト方針

先に決めた通り、INSTRUMENTにある「7種類の攻撃を毎回流す回帰テスト」は今回は入れない。

ただし通常のunit/integration testは入れる。

### 18.1 Guard

- threshold変更は `scoring_bar_modified=true` になり、評価証拠としてinvalidになる
- capacity変更は `operating_point_modified=true` として記録されるが、rejectされない
- agents policy変更は `arm_modified=true` として記録される
- 部分木配下の変更が検出される

### 18.2 Physics

- 正常telemetryは `passed`
- mass balance破綻は `failed`
- 必要データなしは `incomplete`
- failed subsystemが処理している場合は `failure_quiescence` がfailed
- processed quantityがinstalled capacityを超える場合は `capacity_bounds` がfailed

### 18.3 Design Loop

- LLMがcandidateを返すと、constraint / simulation / evaluation / compareが自動実行される
- 同じcandidateを再提案した場合、simulationを二重実行しない
- `empty_response` は1回だけrepair retryする
- repair retryも失敗した場合、state-aware fallbackへ移る
- 既存candidateがある状態でLLM failureが起きてもcandidateを消さない
- final rankingでevaluation総合点を使わない

### 18.4 Evaluator Integration

- `scoring_bar_modified=true` のrunは `evaluation.status=invalid`
- Physics Gate `failed` / `incomplete` のrunは `evaluation.status=invalid`
- candidate runにも `evaluation.json` と `evaluation.html` が生成される
- `evaluation.json` に `integrity` と `physics_gate` 要約が含まれる

## 19. Acceptance Criteria

実装完了条件:

- LLMが直接toolを選ぶ既存loopがDesign Decision Loopへ置き換わっている
- LLM出力schemaが `propose_candidate` / `finish` に限定されている
- DesignStateが毎decisionごとに再構成され、promptへ投入される
- Candidate Pipelineが完全自動化されている
- 同一candidate hashの再simulationが抑止されている
- parse failure / empty responseが1 retry + fallbackで収束する
- Scoring Integrity Guardが導入され、scoring bar改変をinvalid化できる
- Physics Gateがtelemetry-onlyで実行される
- EvaluatorがIntegrity / Physicsの結果を取り込む
- Design RankingがEvaluation total scoreを使わない
- unit/integration testが上記テスト方針の範囲で追加されている

## 20. 完成後の期待挙動

現在の問題ある挙動:

```text
15分
21 LLM turns
candidate 1本
constraint tool大量重複
parse error
```

改良後の期待挙動:

```text
Baseline analysis: Python

LLM #1
  -> Candidate 1
  -> 自動simulation/evaluation/comparison

LLM #2
  -> Candidate 2
  -> 自動simulation/evaluation/comparison

LLM #3
  -> finish

Deterministic final ranking
```

今回の中心は、LLMの思考時間を削ることではない。LLMが「作業手順を忘れて迷子になる時間」をなくすこと。

INSTRUMENTからはスコアカードそのものを大量移植するのではなく、次の2点を強く取り込む。

- 評価対象が物差しを書き換えていないこと
- simulation resultが物理的な証拠として成立していること

この組み合わせが、#64のDesign Agent改善として最も効果が高い。
