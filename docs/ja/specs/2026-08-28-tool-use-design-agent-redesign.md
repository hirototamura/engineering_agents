# Tool Use中心のSSOS ECLSS設計エージェント再設計案

対象リポジトリ: `hirototamura/engineering_agents`

調査日: 2026-08-28

対象範囲: `ssos_eclss_loop`、特に `backend=plant_sim` における ARS / OGS / WRS の処理能力設計。

## 1. 目的

現行の `ssos_eclss_loop` は、50人の乗員を対象に ECLSS の運用と事後設計提案を行う。ただし現状の設計エージェントは、ラン後 summary と一部状態を見て `design_proposals.json` を作る構造であり、人間エキスパートのように「必要な情報を取りに行く」「時系列を解析する」「理論計算をする」「候補設計を再シミュレーションで検証する」という工程が弱い。

本再設計では、設計エージェントを Tool Use 中心に作り替える。エージェントは、固定プロンプトに渡された断片情報だけで判断せず、ツールを選んで根拠を集め、制約下で ARS / OGS / WRS の処理能力を変更し、再実行で候補を検証する。

## 2. 現行構成の把握

### 2.1 主要ファイル

- `src/scenario/ssos_eclss_loop/scenario.yaml`
  - 50人の `plant_sim.crew.size`
  - ARS / OGS / WRS の能力値
  - CO2 / O2 / 水の health threshold
  - survival 設定
  - actor / designer mode
- `src/scenario/ssos_eclss_loop/scenario_run.py`
  - step ループ本体
  - telemetry / health / design_state / events / messages / summary の出力
  - actor 実行、operation 適用、survival 適用
  - post-run designer 起動
- `src/environment/ssos/eclss/plant_sim/config.py`
  - plant_sim の設定正本
- `src/environment/ssos/eclss/plant_sim/model.py`
  - 乗員代謝、ARS、OGS + Sabatier、WRS の決定論的質量収支
- `src/environment/ssos/eclss/plant_sim/backend.py`
  - `EclssBackend` への adapter
- `src/scenario/agents/ssos_eclss_loop_team.py`
  - actor の runtime operation 判断
  - LLM / labeled_rule_base の運用コマンド生成
- `src/scenario/agents/ssos_post_run_design.py`
  - post-run designer
- `src/scenario/ssos_eclss_loop/design_proposals.py`
  - `design_proposals.json` の validate / apply / rule proposal

### 2.2 現行 plant_sim の設計対象

`scenario.yaml` 上の主な値:

- 乗員: `plant_sim.crew.size = 50`
- step: `plant_sim.time.step_seconds = 1200`
- ARS: `plant_sim.ars.capacity_kg_day = 4.50`
- OGS: `plant_sim.ogs.max_o2_kg_day = 9.25`
- WRS: `plant_sim.wrs.max_feed_l_per_operation = 10.0`
- survival: `plant_sim.survival.enabled = true`

ユーザー要望に基づき、設計変数は当面この3つに絞る。

- `plant_sim.ars.capacity_kg_day`
- `plant_sim.ogs.max_o2_kg_day`
- `plant_sim.wrs.max_feed_l_per_operation`

以下は当面、設計変数にしない。

- `plant_sim.ars.capture_efficiency`
- `plant_sim.sabatier.conversion_efficiency`
- `plant_sim.wrs.urine_recovery`
- `plant_sim.wrs.grey_recovery`
- crew 代謝レート
- threshold 類
- action payload の湿度・汚染物質など、plant_sim が無視している入力

理由は、これらは材料、触媒、詳細物理、安全基準、運用ポリシーに近く、今回の「装置サイズ・重量・コストに効く処理能力設計」と混ぜると設計問題がぼやけるため。

### 2.3 現行の運用コマンド

actor が出せる主な operation:

- `air_revitalisation`
  - ARS action
  - payload: `initial_co2_mass`, `initial_moisture_content`, `initial_contaminants`
- `oxygen_generation`
  - OGS action
  - payload: `input_water_mass`, `iodine_concentration`
- `water_recovery`
  - WRS action
  - payload: `urine_volume`
- `request_co2`
  - Sabatier feedstock 用サービス
- `request_o2`
  - O2 storage からの引き出し

注意点:

- parser は `water_recovery` を受け付けるが、`eclss_operational_action_contract()` の文面には `water_recovery` が含まれていない。LLM actor に WRS を使わせるなら修正が必要。
- `max_actions_per_step` は LLM action representative の人数上限であり、同一 step 内の同一 subsystem command 重複を禁止していない。
- LLM representative 1人が複数 command を返せるため、現状では「1 step に ARS を2回」のような重複が入り得る。
- `plant_sim.ars_operation_seconds = 4800` は ARS 1回の処理量計算には使われているが、ARS が80分間 busy になり、その間の追加 ARS command を拒否する guard は現行実装にない。
- labeled_rule_base は実装上、ARS / OGS / WRS を条件に応じて同一 step に1回ずつ追加する構造で、同一 subsystem の重複は基本的に起きない。

### 2.4 現行の設計提案

`design_proposals.json` の現行 `change_kind`:

- `action_profile`
  - actor policy の action payload を変更
- `service_config`
  - `request_co2` / `request_o2` の policy を変更
- `set_parameter`
  - 許可された threshold / policy のみ変更
- `graph_rewire`
  - ROS graph remap / gateway manifest

問題:

- `set_parameter` で plant_sim の処理能力本体を変更できない。
- labeled proposal は stress に応じて `ars_goal.initial_co2_mass` や `ogs_goal.input_water_mass` を増やすが、これは装置の処理能力ではなく運用 payload の調整である。
- post-run designer が見る情報は summary 中心で、時系列や理論必要量を自分で取得・計算する構造ではない。
- 評価関数は明示的な最適化目的として実装されていない。summary に `crew_remaining`, `crew_lost`, `final_health`, `peak_co2_storage_kg`, `min_o2_storage_kg`, `operational_command_count` などは出るが、制約付きスコアリングはない。

## 3. 現行パラメータの理論的な不足

50人、1 step 20分、1日72 step とすると、乗員需要は概算で以下。

- CO2 発生: `50 * 1.04 = 52.0 kg/day`
- O2 需要: `50 * 0.84 = 42.0 kg/day`
- 飲用水需要: `50 * 2.28 = 114.0 L/day`
- WRS feed 発生: `50 * (1.50 + 0.75) = 112.5 L/day`

ただし operation は command で起動されるため、実効処理量は operation 秒数と busy/cooldown 制約に依存する。

ARS:

```text
1 actionの最大CO2除去量
= ars.capacity_kg_day * ars_operation_seconds / 86400
```

現行値では `4.5 * 4800 / 86400 = 0.25 kg/action`。ただし ARS は80分、つまり `4800 / 1200 = 4 step` 作動する前提なので、同時稼働なしなら最大で18 action/dayとなる。この場合の実効能力は `0.25 * 18 = 4.5 kg/day` であり、50人の `52 kg/day` に大きく届かない。

現行実装はこの busy 制約をまだ持っていないため、毎 step ARS command を受け付けてしまう。その場合だけ `18 kg/day` 相当まで処理できるが、これは80分作動という前提と矛盾する。

OGS:

```text
1 actionの最大O2生成量
= ogs.max_o2_kg_day * ogs_operation_seconds / 86400
```

現行値では `9.25 * 1200 / 86400 = 0.128 kg/action`。毎 step OGS を動かしても `9.25 kg/day` 相当で、50人の `42 kg/day` に届かない。

WRS:

```text
1 actionの最大feed処理量
= wrs.max_feed_l_per_operation
```

50人の尿 + 凝縮水は `112.5 / 72 = 1.56 L/step` 程度。現行の `10 L/operation` は処理能力としては十分。ただし action payload の `wrs_goal.urine_volume = 2.0 L` と組み合わせた実効挙動は確認対象にする。

このため「能力を上げれば50人生存できる」は正しいが、現状は制約や最小化目標がないため、ただ大きくするだけで設計問題が終わってしまう。

## 4. 新しい設計思想

初期実装の設計エージェントは1人とする。

現行リポジトリの `agents.yaml` では post-run designer が既定で4人だが、今回の目的は「1人の設計エージェントが、自分で必要情報を集め、一定の思考を経て設計解へ到達できるか」を検証することにある。そのため、最初の再設計では `design.team.count = 1` とする。複数 designer による議論・統合は future phase として残す。

設計エージェントに固定手順を押し付けない。以下の流れは「典型的な成功パターン」ではあるが、実装でこの順番を強制しない。

```text
結果を読む
-> 時系列を見る
-> 特徴量を計算
-> 理論必要能力を計算
-> 仮説を立てる
-> 候補設計
-> 制約評価
-> 再シミュレーション
-> 比較
```

エージェントはまず自分で `task_plan` を作る。その後、tool catalog から必要な tool を選び、tool 結果を見て計画を更新する。実装側が固定するのは思考順序ではなく、次の guardrail である。

- 使える tool catalog
- 1回に呼べる tool は1つ
- 最大 tool iteration 数
- 最終提案には根拠を含める
- 最終提案前に Evidence Gate を通す
- 制約評価と候補再シミュレーションは最終案採用の必須 evidence にする

重要なのは、LLM に全情報を一括で渡さないこと。LLM は tool catalog を見て、必要な tool を選んで呼ぶ。tool 側は決定論的で、計算・集計・描画・再実行を担当する。

### 4.1 Expert Context Pack

Qwen 3B / 8B / 32B 級の LLM に「十分に判断できたか」を完全に自己判定させるのは危険である。小中規模モデルでは、summary だけを見て早い段階で最終案へ進む失敗が起きやすい。したがって、プロンプトには短い Expert Context Pack を入れる。

Expert Context Pack は、詳細な教科書知識ではなく、この設計問題で最低限守るべき専門的前提である。

```text
Expert Context Pack:
- 目的は crew_remaining 最大化。ただし無制限な能力増強は禁止。
- 設計変数は ARS capacity / OGS capacity / WRS feed capacity の3つだけ。
- recovery efficiency、Sabatier conversion、crew metabolism、threshold は設計変数ではない。
- ARS は CO2 除去能力、OGS は O2 生成能力、WRS は水循環能力に効く。
- OGS capacity を上げても input_water_mass が小さいと実効能力が出ない。
- WRS capacity を上げても urine_volume が小さいと実効能力が出ない。
- summary だけで判断してはいけない。時系列、critical dwell、shortfall、crew loss cause を見る。
- final proposal は再シミュレーションで検証された候補だけ採用できる。
```

これは思考手順の固定ではない。エージェントが設計エキスパートとして持つべき前提知識と、浅い自己完結を防ぐための最低条件である。

### 4.2 Evidence Gate

エージェントが `final_proposal` を返しても、そのまま受理しない。実装側で Evidence Gate を通し、必要な evidence が足りなければ final を reject して、足りない項目を tool-use loop に返す。

最小 evidence:

- baseline run artifact を読んだ
- CO2 / O2 / 水 / crew_alive の時系列を確認した
- ARS / OGS / WRS の理論必要能力を計算した
- 少なくとも1つの設計候補を作った
- 候補の制約影響を評価した
- 候補を再シミュレーションした
- baseline と candidate を比較した

この gate は deterministic に実装する。LLM 自身の「十分だと思う」という判断だけでは final に進めない。

## 5. 追加する Tool Use 基盤

### 5.1 実装方針

自前の JSON tool loop を実装する。理由は、現行 LLM provider が self-hosted vLLM / Ollama を想定しており、OpenAI 互換の native function calling が常に使えるとは限らないため。

LLM 出力契約:

```json
{
  "message": "what I learned or plan",
  "reasoning": "short reason",
  "tool_call": {
    "name": "tool_name",
    "arguments": {}
  }
}
```

最終出力契約:

```json
{
  "message": "final recommendation",
  "reasoning": "evidence-backed rationale",
  "final_proposal": {
    "changes": [],
    "expected_outcome": {},
    "constraint_evaluation": {}
  }
}
```

1 turn につき tool_call は最大1つ。tool loop の `max_tool_iterations` を設定し、無限実行を防ぐ。

### 5.2 Tool registry

追加候補:

- `load_run_artifacts`
  - 入力: `run_dir`, `files`
  - 出力: summary、scenario_config、agents_config、telemetry rows、health rows、events、messages
- `summarize_timeseries`
  - 入力: telemetry / health、対象列
  - 出力: min/max/final、first warning/critical、time in band、傾き、短不足累積
- `compute_eclss_features`
  - 入力: run artifacts
  - 出力: subsystem 別の stress 指標、crew loss cause、operation count、failure window、resource margin
- `compute_theoretical_capacity`
  - 入力: scenario_config、crew_size、operation cadence
  - 出力: ARS / OGS / WRS の理論必要能力、baseline との不足率
- `plot_eclss_timeseries`
  - 入力: telemetry / health、対象列
  - 出力: PNG path と簡易説明
- `propose_capacity_candidate`
  - 入力: target survival、margin、constraint profile、現在 design
  - 出力: ARS / OGS / WRS capacity 候補
- `evaluate_design_constraints`
  - 入力: capacity candidate、constraint profile
  - 出力: mass / cost / launch volume / feasibility / penalties
- `run_design_candidate`
  - 入力: base scenario config、candidate、run options
  - 出力: run_dir、summary
- `compare_design_runs`
  - 入力: baseline run と candidate runs
  - 出力: survivor count、constraint feasibility、resource margins、score ranking

### 5.3 Tool 実装場所

新規:

- `src/scenario/ssos_eclss_loop/design_variables.py`
- `src/scenario/ssos_eclss_loop/design_constraints.py`
- `src/scenario/ssos_eclss_loop/design_eval.py`
- `src/scenario/ssos_eclss_loop/design_tools.py`
- `src/scenario/agents/ssos_tool_use_design.py`

既存変更:

- `src/scenario/agents/ssos_post_run_design.py`
  - `agents.design.tool_use.enabled` が true の場合だけ tool-use agent を使う
- `src/scenario/ssos_eclss_loop/design_proposals.py`
  - plant_sim capacity 変更を proposal schema に追加
- `src/scenario/ssos_eclss_loop/scenario_run.py`
  - candidate run / evaluation report の保存に対応
- `src/scenario/agents/ssos_eclss_loop_team.py`
  - 1 step command 制約を enforce

## 6. 設計変数スキーマ

新しい proposal change_kind を追加する。

```json
{
  "change_kind": "capacity_profile",
  "payload": {
    "backend": "plant_sim",
    "fields": {
      "plant_sim.ars.capacity_kg_day": 13.5,
      "plant_sim.ogs.max_o2_kg_day": 42.0,
      "plant_sim.wrs.max_feed_l_per_operation": 2.0
    }
  }
}
```

互換性のため、既存の `action_profile`, `service_config`, `set_parameter`, `graph_rewire` は残す。

`capacity_profile` は `plant_sim` 用の装置設計変更と明確に定義する。`action_profile` は運用時の command payload 設定であり、ハードウェア能力とは区別する。

### 6.1 OGS の注意

OGS は `ogs.max_o2_kg_day` を上げても、actor policy の `ogs_goal.input_water_mass` が小さいと request 側で律速する。

そのため候補適用時には以下のどちらかを実装する。

推奨:

- `capacity_profile` 適用時に、必要なら `agents.actor.policy.ogs_goal.input_water_mass` を nameplate を使い切れる値に自動同期する。

同期式:

```text
ogs_goal.input_water_mass
>= ogs.max_o2_kg_day * ogs_operation_seconds / 86400 * WATER_PER_O2
```

代替:

- `action_profile` も同時 proposal として出す。

推奨は前者。設計能力の変更に対して、運用 payload が古いまま残って能力増強が無効化される事故を避けられる。

### 6.2 WRS の注意

`wrs.max_feed_l_per_operation` が十分でも `wrs_goal.urine_volume` が小さいと尿 feed が request 側で律速する。ただし grey water は remaining capacity の範囲で処理される。

候補適用時には、少なくとも以下を満たすよう同期する。

```text
wrs_goal.urine_volume >= expected_urine_l_per_step
```

余裕を持たせるなら `wrs_goal.urine_volume = wrs.max_feed_l_per_operation` とする。

## 7. 1 step 内の command 制約

ユーザー要望:

- 1 step あたり同一 subsystem の command は1回まで。
- ARS / OGS / WRS を同じ step に1回ずつ実行するのは許可。
- ARS を同じ step に2回実行するのは禁止。

実装:

`StepEclssOutcome.commands` を backend に適用する前に正規化する。

command group:

- `ars`: `air_revitalisation`, `request_co2`
- `ogs`: `oxygen_generation`, `request_o2`
- `wrs`: `water_recovery`

ただし `request_co2` と `air_revitalisation` を同じ `ars` group に入れるかは要検討。現行では `request_co2` は Sabatier feedstock 用 service で、ARS action とは別の意味を持つ。初期実装では以下を推奨する。

- subsystem action の重複禁止:
  - `air_revitalisation` は step 1回
  - `oxygen_generation` は step 1回
  - `water_recovery` は step 1回
- service call は別枠だが、同種 service は step 1回
  - `request_co2` は step 1回
  - `request_o2` は step 1回

重複処理:

- 最初の valid command を採用。
- 2つ目以降は適用せず、`/eclss/events/operational_rejected` に `reason=duplicate_command_this_step` を記録。
- LLM prompt / contract にも制約を明記。
- validator は deterministic にし、labeled / llm / tests で同じ挙動にする。

既存の `max_actions_per_step` は「何人の代表が action round に参加するか」の設定として残す。ただし実行 gate が最終的な安全装置になる。

### 7.1 Operation duration / busy guard

1 step 内の重複禁止だけでは不十分である。ARS は `ars_operation_seconds = 4800`、step は `step_seconds = 1200` なので、1回 command を受け付けたら4 step 分は作動中と扱う必要がある。

初期実装では、backend ごとに subsystem の busy 状態を持つ。

```text
busy_steps(subsystem) = ceil(operation_seconds / step_seconds)
```

既定値:

- ARS: `ceil(4800 / 1200) = 4 step`
- OGS: `ceil(1200 / 1200) = 1 step`
- WRS: `ceil(1200 / 1200) = 1 step`

挙動:

- `air_revitalisation` を step `t` で受け付けたら、ARS は `t, t+1, t+2, t+3` で busy。
- busy 中に追加の `air_revitalisation` が来たら、状態を変更せず `operational_rejected` として記録する。
- reject reason は `subsystem_busy`。
- event details には `subsystem`, `busy_until_step`, `remaining_steps` を入れる。
- `oxygen_generation` / `water_recovery` も同じ仕組みに乗せる。ただし既定では1 step作動なので、次 step では再実行可能。

MVPでは、operation の物質収支は command 受理時に一括で反映し、その後 busy 期間だけ同一 subsystem command を拒否する。これは現行 `PlantModel.run_ars()` の構造を大きく変えずに、80分作動の運用制約を表現するための最小変更である。

より物理的にする future phase では、ARS の除去量を4 step に分配し、telemetry 上も作動中に徐々に CO2 が下がるようにできる。ただし初期実装では、まず「80分以内の再コマンド拒否」を優先する。

実装場所:

- `PlantSimEclssBackend`
  - `operation_busy_until_step` または `operation_remaining_steps` を持つ
  - `advance_step()` で remaining を減らす
  - `send_air_revitalisation_goal()` などの冒頭で busy を判定する
- `LoopMockEclssBackend`
  - plant_sim と同じ semantics に寄せるなら同様の guard を追加
- `scenario_run.py`
  - backend に現在 step を通知するか、backend 側が `advance_step()` 回数から step を保持する

設計エージェントの理論計算 tool は、この busy cadence を必ず考慮する。

```text
max_actions_per_day = floor(86400 / operation_seconds)
effective_capacity_per_day = capacity_per_action * max_actions_per_day
```

ARS の場合、`capacity_per_action = capacity_kg_day * ars_operation_seconds / 86400` なので、operation が隙間なく回る限り `effective_capacity_per_day` は `capacity_kg_day` に一致する。

## 8. 制約モデル

`scenario.yaml` に design constraint section を追加する。ここでの数値は実機見積ではなく、設計探索用の初期モデルである。ただし、処理能力を上げると質量・体積・コストが増えるという関係は明示する。

```yaml
design_constraints:
  enabled: true
  objective:
    primary: maximize_crew_remaining
    secondary: minimize_resource_footprint
  budgets:
    # Soft caps for reporting, not a pre-simulation hard stop.
    max_total_mass_kg: 4000.0
    max_total_cost_musd: 500.0
    max_total_volume_m3: 14.0
  subsystem_bounds:
    ars:
      min_capacity_kg_day: 4.5
      max_capacity_kg_day: 80.0
    ogs:
      min_o2_kg_day: 9.25
      max_o2_kg_day: 80.0
    wrs:
      min_feed_l_per_operation: 1.0
      max_feed_l_per_operation: 20.0
  sizing_model:
    mode: rack_affine_linear_v1
```

初期実装では、実物値と誤解されないよう `rack_affine_linear_v1` として係数を scenario 側に明示する。NASA / ISS 実機値を名乗らない。

例:

```yaml
design_constraints:
  sizing_model:
    mode: rack_affine_linear_v1
    baseline:
      ars_capacity_kg_day: 4.5
      ogs_max_o2_kg_day: 9.25
      wrs_max_feed_l_per_operation: 10.0
    # estimated subsystem mass = fixed + variable * capacity / baseline_capacity
    mass_kg:
      ars:
        fixed: 180.0
        variable_at_baseline: 270.0
      ogs:
        fixed: 250.0
        variable_at_baseline: 450.0
      wrs:
        fixed: 300.0
        variable_at_baseline: 350.0
    # estimated subsystem volume = fixed + variable * capacity / baseline_capacity
    volume_m3:
      ars:
        fixed: 0.8
        variable_at_baseline: 1.2
      ogs:
        fixed: 1.0
        variable_at_baseline: 1.3
      wrs:
        fixed: 1.2
        variable_at_baseline: 1.3
    # rough hardware / integration cost, excluding launch
    hardware_cost_musd:
      ars:
        fixed: 15.0
        variable_at_baseline: 25.0
      ogs:
        fixed: 20.0
        variable_at_baseline: 45.0
      wrs:
        fixed: 18.0
        variable_at_baseline: 37.0
    launch_cost_musd_per_kg: 0.055
```

この係数は後で差し替え可能にする。初期段階の目的は、無制限な能力増強を防ぎ、設計エージェントに trade-off を考えさせること。

計算式:

```text
capacity_ratio = candidate_capacity / baseline_capacity

subsystem_mass_kg =
  fixed_mass_kg + variable_mass_kg_at_baseline * capacity_ratio

subsystem_volume_m3 =
  fixed_volume_m3 + variable_volume_m3_at_baseline * capacity_ratio

subsystem_hardware_cost_musd =
  fixed_cost_musd + variable_cost_musd_at_baseline * capacity_ratio

launch_cost_musd =
  total_mass_kg * launch_cost_musd_per_kg

total_cost_musd =
  hardware_cost_musd + launch_cost_musd
```

このモデルでは、能力を下げれば variable 部分は小さくなる。ただし fixed 部分は、ラック、筐体、制御器、配管、冗長系などの最低コストとして残る。

初期値での baseline footprint:

```text
ARS mass = 180 + 270 = 450 kg
OGS mass = 250 + 450 = 700 kg
WRS mass = 300 + 350 = 650 kg
total mass = 1800 kg

ARS volume = 0.8 + 1.2 = 2.0 m3
OGS volume = 1.0 + 1.3 = 2.3 m3
WRS volume = 1.2 + 1.3 = 2.5 m3
total volume = 6.8 m3

hardware cost = 40 + 65 + 55 = 160 MUSD
launch cost = 1800 * 0.055 = 99 MUSD
total cost = 259 MUSD
```

`launch_cost_musd_per_kg = 0.055` は ISS に届ける cargo / hardware burden の初期値として置く。単なる LEO 投入費ではなく、ISS への補給・輸送契約、打上げ、宇宙機、運用、統合を含む桁感を反映した値である。ユーザー想定の「1 kg あたり550万円」へ寄せるなら `0.037 MUSD/kg` 程度に下げればよい。

参考: NASA OIG の Commercial Resupply Services 監査レポートでは、CRS-1 / CRS-2 の cost per kilogram が概算で 63,200-71,800 USD/kg と示されている。初期値の 55,000 USD/kg は、この桁感より少し低めに置いた探索用パラメータである。

### 8.1 制約チェックの扱い

制約チェックは、candidate simulation の前に候補を機械的に落とすためのものではない。候補が予算超過していても、再シミュレーションすれば「過剰設計だが生存性は改善する」「この程度まで上げれば効果が出る」などの学びになる。

したがって制約評価は2段階に分ける。

1. Preflight validation
2. Constraint evaluation

Preflight validation は、シミュレーションしても意味がない候補だけを止める。

- JSON schema が壊れている
- NaN / Inf / negative
- 許可されていない design variable を変更している
- `crew.size` や代謝レートを変更している
- threshold を survival 回避のために緩めている
- backend が解釈できない値で simulation が起動できない

Constraint evaluation は、候補を止めずにラベル付けする。

- mass budget 超過
- cost budget 超過
- launch volume budget 超過
- subsystem bound 超過
- baseline 比で過剰に大きい

これらは `constraint_status = feasible | over_budget | out_of_bounds | invalid` のように記録する。`invalid` は実行しない。`over_budget` / `out_of_bounds` は、設定で禁止しない限り実行してよい。ただし最終採用時には feasible 候補を優先し、over-budget 候補を採用する場合は明示的な理由を要求する。

推奨設定:

```yaml
design_constraints:
  simulation_policy:
    run_invalid_candidates: false
    run_over_budget_candidates: true
    run_out_of_bounds_candidates: true
    require_feasible_final: true
```

この形にすると、制約違反候補もエージェントの学習材料になる。一方で、最終案が「打ち上げられない巨大装置」になる問題は `require_feasible_final` で防げる。

## 9. 評価関数

評価は lexicographic にする。生存者最大化を主目的にしつつ、同じ生存者数の候補同士では危険状態の滞在時間を減らし、さらに同等なら質量・体積・コストを最小化する。

最終案は simulation 後にだけ採用判定する。事前の constraint evaluation は「候補を理解するためのラベル」であり、`invalid` 以外は原則として simulation してよい。

final eligibility:

- `preflight_status == valid`
- candidate simulation が完了している
- Evidence Gate を通過している
- 変更対象が3つの design variable に限定されている
- baseline より生存者数を悪化させていない
- 全員生存候補が1つでもある場合、final は全員生存候補から選ぶ

```text
rank key =
(
  final_eligible,             # true を優先
  crew_remaining,             # 最大化
  -critical_step_count,       # 最小化
  -warning_step_count,        # 最小化
  -total_mass_kg,             # 最小化
  -total_volume_m3,           # 最小化
  -total_cost_musd            # 最小化
)
```

実装上は Python の昇順 sort と相性がよいよう、次の形にしてもよい。

```python
rank_key = (
    not final_eligible,
    -crew_remaining,
    critical_step_count,
    warning_step_count,
    total_mass_kg,
    total_volume_m3,
    total_cost_musd,
)
```

final status:

- `approved_final`: 全員生存、Evidence Gate 通過、valid candidate、かつ rank 最上位。
- `provisional_final`: 観測された最良候補だが、全員生存ではない、または soft cap / engineering bound を超えている。学習結果としては有用だが、自動採用しない。
- `rejected_final`: evidence 不足、invalid、simulation 失敗、または baseline より悪い。

`design_penalty` は説明用の補助指標として残す。採用判定の正本は上の lexicographic rank とする。

```text
design_penalty =
  w_mass   * added_mass_kg / max_added_mass_kg
+ w_cost   * added_cost_musd / max_added_cost_musd
+ w_volume * added_launch_volume_m3 / max_added_launch_volume_m3
```

candidate status:

- `invalid`: schema / 数値 / 対象変数が不正。simulation しない。
- `over_budget`: 予算超過。simulation はしてよいが、通常は final 採用不可。
- `out_of_bounds`: subsystem bounds 超過。simulation はしてよいが、通常は final 採用不可。
- `feasible`: 制約内。final 採用候補。

ランキングでは、全候補を比較対象に含める。ただし `require_feasible_final = true` の場合、最終 proposal には `feasible` 候補だけを採用できる。もし feasible 候補が存在しない場合は、最良の over-budget / out_of_bounds 候補を「参考解」として報告し、正式な `capacity_profile` proposal は出さないか、`requires_supervisor_approval: true` を付ける。

出力:

- `design_review_report.json`
- `candidate_runs/<candidate_id>/summary.json`
- `candidate_rankings.json`
- `design_proposals.json`

## 10. Tool-use designer の自律 planning loop

`ToolUseDesignAgent` は固定状態機械ではなく、自律 planning loop として実装する。

```text
START
  -> create/update task_plan
  -> choose one tool
  -> observe tool result
  -> update hypotheses and task_plan
  -> either choose next tool or request final_proposal
  -> evidence_gate
  -> FINALIZE or continue
```

guardrail として以下を置く。

- `max_tool_iterations`
- `max_candidate_runs`
- `allowed_tool_names`
- `required_before_final = ["load_run_artifacts", "compute_theoretical_capacity", "evaluate_design_constraints", "run_design_candidate", "compare_design_runs"]`
- final proposal は少なくとも1つの candidate run に裏付けられていること
- final proposal は Evidence Gate を通過すること

LLM が required tool を使わず final を返した場合は rejected とし、再プロンプトする。上限到達時は rule fallback を使う。

## 11. 既存 post-run design との統合

`agents.yaml`:

```yaml
design:
  team:
    count: 1
    id_prefix: eclss_designer
  tool_use:
    enabled: true
    max_tool_iterations: 12
    max_candidate_runs: 4
    require_candidate_validation: true
```

mode 解釈:

- `design.mode = none`
  - designer 無効
- `design.mode = labeled_rule_base`
  - 従来どおり rule proposal
  - 将来は rule-based capacity sizing も追加可
- `design.mode = llm`, `design.tool_use.enabled = false`
  - 従来の post-run LLM proposal
- `design.mode = llm`, `design.tool_use.enabled = true`
  - 新しい Tool Use designer。初期実装では1人。

互換性維持:

- 既存 tests が期待する graph proposal / action_profile proposal は壊さない。
- `design_proposals.json` の root fields は維持する。
- 新しい追加 fields:
  - `design_family: "capacity_sizing"`
  - `tool_trace_path`
  - `candidate_rankings_path`
  - `selected_candidate_id`
  - `constraint_evaluation`

## 12. 再シミュレーション設計

`run_design_candidate` は `SsosEclssLoopScenario.run()` を直接呼び、候補ごとに isolated output dir を作る。

例:

```text
<run_dir>/
  summary.json
  telemetry.jsonl
  health_metrics.jsonl
  messages.jsonl
  events.jsonl
  design_state.jsonl
  design_proposals.json
  design_review_report.json
  tool_trace.jsonl
  candidate_rankings.json
  candidate_runs/
    candidate_001/
      summary.json
      telemetry.jsonl
      ...
```

候補 run では designer を無効化する。

```yaml
agents:
  design:
    mode: none
```

理由: candidate 検証中にさらに post-run design を発火させると再帰的に膨らむため。

## 13. グラフ出力

`plot_eclss_timeseries` は、LLM に画像そのものを渡せる環境では PNG を返し、渡せない環境では数値 summary と画像 path を返す。

最低限プロットする系列:

- CO2 storage / high / critical
- O2 storage / low / critical
- product water reserve / low / critical
- crew_alive
- subsystem failure flags
- operation applied markers

初期実装では画像理解を必須にしない。LLM が画像を見られない場合でも、tool が同じ特徴量を text / JSON で返す。

## 14. Claude Code 実装タスク

### Phase 1: command 制約の修正

- `ssos_eclss_loop_team.py` に command dedupe / rejection gate を追加
- `eclss_operational_action_contract()` に `water_recovery` を追加
- `PlantSimEclssBackend` に operation duration / busy guard を追加
- ARS は `ars_operation_seconds / step_seconds = 4 step` の busy 中に再 command を拒否する
- tests:
  - LLM が同一 step に ARS 2件を返したら1件だけ適用、1件 reject
  - ARS / OGS / WRS 各1件は同一 step で許可
  - step 0 で ARS を受理したら step 1〜3 の ARS command は `subsystem_busy` で reject
  - step 4 では ARS command を再度受理できる
  - labeled_rule_base の既存挙動が壊れない

### Phase 2: capacity proposal schema

- `design_proposals.py` に `capacity_profile` を追加
- 許可 fields は3つだけ
- `apply_design_proposals()` で `plant_sim` config へ反映
- OGS / WRS action payload の自動同期を実装
- tests:
  - capacity 3変数が apply される
  - efficiency や crew rate 変更は reject
  - OGS capacity 増強時に `ogs_goal.input_water_mass` が不足しない

### Phase 3: constraint / evaluation

- `design_constraints.py`
  - constraint config parsing
  - sizing model
  - feasibility validation
- `design_eval.py`
  - `evaluate_run_outcome()`
  - `rank_candidates()`
- tests:
  - crew_remaining が mass penalty より優先される
  - full survival 同士では penalty が小さい方を選ぶ
  - invalid candidate は実行されない
  - budget 超過 candidate は実行可能だが final 採用不可として扱われる

### Phase 4: analysis tools

- `design_tools.py`
  - tool registry
  - artifact loaders
  - timeseries summary
  - theoretical capacity
  - plotting
  - candidate run
  - compare
- tests:
  - sample telemetry から warning / critical step 数を計算
  - 50人設定で ARS / OGS の不足を検出
  - candidate run は designer 無効で実行される

### Phase 5: ToolUseDesignAgent

- `ssos_tool_use_design.py`
  - JSON tool-call parser
  - tool loop
  - task_plan の生成・更新
  - Expert Context Pack の注入
  - required tool guard
  - Evidence Gate
  - trace logging
  - fallback
- `ssos_post_run_design.py`
  - tool_use enabled 時に委譲
- tests:
  - fake LLM が tool を順に呼んで final proposal を出せる
  - invalid tool name を reject して再試行
  - required evidence が足りない final proposal を reject して継続する
  - max iteration 到達時に fallback

### Phase 6: docs / dashboard

- docs/ja と docs/en に Tool Use design loop を追加
- dashboard に candidate comparison を追加すると有用だが、初期リリースでは必須ではない

## 15. 受け入れ条件

最小受け入れ条件:

- `backend=plant_sim`, `crew.size=50` で baseline run を読み、tool-use designer が容量不足を根拠付きで説明できる。
- designer が少なくとも `compute_theoretical_capacity` と `run_design_candidate` を使う。
- proposal が ARS / OGS / WRS のうち必要な処理能力だけを変更する。
- 能力増強が constraint budget を超えた場合でも、設定により candidate simulation は実行できる。
- final proposal は Evidence Gate を通過した候補だけを採用する。
- 全員生存の candidate が複数ある場合、最も軽い / 安い / 小さい候補を選ぶ。
- 同一 step 内の同一 subsystem command 重複が実行されない。
- ARS は80分作動、つまり4 step busy として扱われ、busy 中の追加 ARS command は reject される。
- 既存の `labeled_rule_base` smoke / unit tests が通る。

推奨受け入れ条件:

- tool trace を読むと、設計判断が「時系列観察 -> 特徴量 -> 理論計算 -> 候補 -> 再実行 -> 比較」の流れになっている。
- LLM が画像グラフを使わない場合でも、JSON 特徴量だけで同じ結論に到達できる。
- proposal の `why`, `what`, `how` が candidate run の実測値に紐づいている。

## 16. 最初に確認したい論点

制約モデルの初期値をどう置くかが、設計問題の性格を決める。

推奨は、まず実物値そのものではない `rack_affine_linear_v1` の仮係数で実装し、係数を YAML で差し替え可能にすること。これなら「いたずらに能力だけを上げる」挙動をすぐ防げる一方、実機値の正しさを過剰に主張せずに済む。

確認事項:

制約の初期実装は、固定部 + 能力比例部で質量・体積・コストが増える `rack_affine_linear_v1` として始めてよいか。候補は budget / mass / volume 超過でも simulation し、最終採用時には「生存者最大化を最優先、同等なら危険滞在時間、質量、体積、コストを最小化」の順で選ぶ。
