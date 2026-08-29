# Tool Use 設計エージェント — ARS / OGS / WRS の処理能力設計

> **範囲**: `ssos_eclss_loop` の **事後設計 (designer) 側だけ**。ランタイム運用 (actor) は [labeled_rule_base.md](labeled_rule_base.md)。
> 従来の summary 直読み designer は [post_run_design_agent.md](post_run_design_agent.md)（そのまま残す）。
> **由来**: 設計書「Tool Use中心のSSOS ECLSS設計エージェント再設計案」(2026-08-28)。

## なぜ作り直したか

従来の designer は、ラン後の `summary` と一部の状態だけを見て `design_proposals.json` を作っていた。人間のエキスパートがやる

- 必要な情報を自分で取りに行く
- 時系列を解析する
- 理論必要量を計算する
- 候補設計を**再シミュレーションで検証する**

という工程が無く、しかも `set_parameter` では plant_sim の**処理能力そのもの**を変更できなかった。`action_profile` で `ars_goal.initial_co2_mass` を増やすのは運用 payload の調整であって、装置のサイズ設計ではない。

新しい designer は **Tool Use 中心**にする。LLM に全情報を一括で渡さず、tool catalog だけを渡す。計算・集計・描画・再実行は決定論的な tool 側が担当する。

## 何が設計変数か（3つだけ）

| 設計変数 | 意味 | 単位 |
| --- | --- | --- |
| `plant_sim.ars.capacity_kg_day` | ARS の CO₂ 除去能力 | kg/day |
| `plant_sim.ogs.max_o2_kg_day` | OGS の O₂ 生成能力 | kg/day |
| `plant_sim.wrs.max_feed_l_per_operation` | WRS の 1 バッチ処理量 | L/operation |

**設計変数にしないもの**: 回収効率 (`ars.capture_efficiency`, `wrs.urine_recovery`, `wrs.grey_recovery`)、Sabatier 変換率、乗員代謝レート、health threshold。これらは材料・触媒・安全基準・運用ポリシーの話で、「装置サイズ・重量・コストに効く処理能力設計」と混ぜると設計問題がぼやける。

実装は `src/scenario/ssos_eclss_loop/design_variables.py`。`capacity_profile` proposal はこの 3 つ以外を書こうとすると **reject** される。

### 運用 payload の自動同期（重要）

OGS は `ogs_goal.input_water_mass` が小さいと、能力を上げても request 側で律速して**能力増強が無効化される**。WRS も `wrs_goal.urine_volume` で同じことが起きる。そのため `capacity_profile` 適用時に運用 payload を自動で引き上げる。

```text
ogs_goal.input_water_mass >= ogs.max_o2_kg_day * ogs_operation_seconds / 86400 * WATER_PER_O2
wrs_goal.urine_volume     >= 1 step あたりの尿発生量（バッチ上限でクランプ）
```

同期は**引き上げ方向のみ**。手で大きくした payload は縮めない。`payload.sync_action_payloads: false` で無効化できる。

## 1 step のコマンド制約と busy guard

設計の前提として、運用側に 2 つの制約を入れた（設計書 §7）。

1. **1 step あたり同一 subsystem のコマンドは 1 回まで。** ARS / OGS / WRS を同じ step に 1 回ずつは許可。ARS を同じ step に 2 回は禁止。2 件目以降は `/eclss/events/operational_rejected`（`reason=duplicate_command_this_step`）。
   実装は `SsosEclssLoopTeam.apply_outcome()` の**実行ゲート**で、mode に依存しない。`max_actions_per_step`（action round に参加する代表人数）は従来どおり残る。
2. **operation duration / busy guard.** `ars_operation_seconds = 4800`、`step_seconds = 1200` なので、ARS は 1 回受理すると `ceil(4800/1200) = 4 step` 作動中になる。作動中の再コマンドは `reason=subsystem_busy` で拒否（`details` に `subsystem` / `remaining_steps` / `busy_until_step`）。OGS / WRS は既定 1 step なので次 step で再実行できる。なお、実際に何も処理しなかった回は装置を占有しない: 供給のない WRS（`reason=no_feed`）と、水がない / 要求 0 の OGS（`reason=no_water`）はどちらも busy にならない。
   実装は `PlantSimEclssBackend`。`plant_sim.operations.busy_guard_enabled: false` で切り戻せる。

この結果、ARS の実効能力は `capacity_kg_day × goal_scale`（1 日 18 action が上限）になり、50 人の `52 kg/day` にまったく届かないことが**ランに現れる**ようになった。

## Tool catalog

`src/scenario/ssos_eclss_loop/design_tools.py`。すべて JSON を返し、例外を投げない（失敗は `{"error": ...}`）。

| tool | 何をするか |
| --- | --- |
| `load_run_artifacts` | summary / config / 各 JSONL の件数と head・tail |
| `summarize_timeseries` | 列ごとの min/max/final、warning・critical 滞在 step、初回逸脱 step、傾き、累積不足 |
| `compute_eclss_features` | subsystem 別ストレス、コマンド適用・拒否の理由別内訳、乗員損失原因、故障窓、最終在庫 |
| `compute_theoretical_capacity` | 乗員需要 vs 名目能力。**busy cadence と goal scale を必ず考慮**し、不足率と必要 nameplate を返す |
| `plot_eclss_timeseries` | PNG を `design_plots/` に描く。**画像理解は必須にしない**（同じ特徴量を数値でも返す） |
| `propose_capacity_candidate` | 理論値 + margin から候補 capacity を組む（シミュレーションはしない） |
| `evaluate_design_constraints` | 質量・体積・コスト・bounds・budget のラベル付け |
| `run_design_candidate` | 候補で**再シミュレーション**（候補ラン内では designer を無効化） |
| `compare_design_runs` | baseline と全候補を目的関数でランキングし、採用候補を決める（引数なし。evidence 完了判定は台帳から読む。モデルからは渡せない）|

## 制約モデル（`rack_affine_linear_v1`）

`scenario.yaml` の `design_constraints:`。**実機見積ではなく探索用の初期モデル**であることを明示している。

```text
capacity_ratio = candidate_capacity / baseline_capacity
subsystem_mass   = fixed + variable_at_baseline * capacity_ratio
subsystem_volume = fixed + variable_at_baseline * capacity_ratio
subsystem_cost   = fixed + variable_at_baseline * capacity_ratio      # hardware のみ
launch_cost      = total_mass_kg * launch_cost_musd_per_kg
total_cost       = hardware_cost + launch_cost
```

baseline footprint は 1800 kg / 6.8 m³ / 259 MUSD（hardware 160 + launch 99）。`launch_cost_musd_per_kg = 0.055` は NASA OIG の CRS 監査（63.2–71.8 kUSD/kg）より少し低めに置いた**探索用**の値。

制約チェックは 2 段階（設計書 §8.1）:

- **Preflight**: schema 破損・NaN/Inf/負値・設計変数外の変更 → `invalid`。**シミュレーションしない**。
- **Constraint evaluation**: budget / bounds 超過は候補を止めず `over_budget` / `out_of_bounds` と**ラベルするだけ**。「過剰設計だが生存性は改善する」も学びなので走らせる。ただし 2 つのラベルは採用段階で扱いが違う。`out_of_bounds` は物理的に製造できない機体なので採用しない（`require_in_bounds_final: true`）。`over_budget` は金の話なので採用対象にはなり、`provisional_final` として人間に上げる（`require_feasible_final: false`。予算も硬い門にしたければ `true`）。
- 一部のサブシステムだけを指定した候補も、ステーション全体として価格計算される。指定しなかったサブシステムは **現在インストールされている**容量で計算する（サイジングモデルの初期値ではない）。どちらを使ったかは評価結果の `capacity_source` に出る。

## 評価: まず合格ライン、その中で危険帯の滞在が短い機体、その中で最小

生存はランキングのキーではなく**合格条件**。1 人でも失う設計はそもそも採用できないので、
質量削減と人命が天秤に載ること自体が起きない。合格した設計の中では、CRITICAL 滞在が
短い方が質量より優先する。軽いが危険帯にいる機体が、重いが安全な機体に勝つことはない。

```python
final_eligible = (
    preflight_valid                     # schema / 数値 / 設計変数の範囲
    and simulated                       # 主張ではなく再シミュレーション済み
    and evidence_complete               # レビューが証拠を揃えている
    and crew_remaining == crew_initial  # 合格ライン
    and constraint_status != "out_of_bounds"   # 実際に製造できる
)

rank_key = (
    not final_eligible,     # 採用可能な候補を先に
    -crew_remaining,        # 不合格候補どうしの並び順にしか効かない
    critical_step_count,    # 合格候補の中では CRITICAL 滞在が短い方が勝つ
    warning_step_count,
    total_mass_kg,          # その次に最小の機体
    total_volume_m3,
    total_cost_musd,
)
```

ランキング自体が目的関数なので、**モデルはこれを上書きできない**。`final_proposal` で別の
`candidate_id` を指名しても `parse_notes` に記録されるだけで採用は動かない。どの候補を作って
走らせるかは designer の判断、どの検証済み候補を採るかは計算。

`scenario.yaml` の `design_constraints.objective` はこの目的関数を記述するもので、シナリオ
ロード時に検証する。実装されていない値が書かれていればシミュレーション開始前に落ちるので、
設定と挙動が食い違ったまま走ることはない。

`design_penalty`（質量・コスト・体積の正規化和）は**説明用**であり、採用判定の正本ではない。

final status:

| status | 意味 |
| --- | --- |
| `approved_final` | 全員生存 + Evidence Gate 通過 + bounds 内 + budget 内 + rank 最上位 |
| `provisional_final` | 選ばれた設計だが、全員生存でない、または budget 超過。`requires_supervisor_approval: true` を付けて報告する |
| `rejected_final` | evidence 不足、invalid、候補が 1 つも作られなかった |

### 採用は別の行為

`design_proposals.json` は status に関わらず書き出す（記録として要る）。採用側に門がある:
`--apply-proposals` は `final_status` が `approved_final` でない文書、または
`requires_supervisor_approval` が付いた文書を**理由付きで拒否する**。それでも採る場合は人間が
`--approve-provisional` を渡す。ファイルを渡されたことは承認ではなく、予算超過の設計に金を
払うと決めることが承認である。

## Evidence Gate

LLM が `final_proposal` を返しても、そのままは受理しない。次が揃うまで **reject して不足項目を返し、ループを続ける**。

1. baseline artifact を読んだ
2. 時系列を確認した
3. 理論必要能力を計算した
4. 候補を作った
5. 候補の制約影響を評価した
6. 候補を再シミュレーションした
7. baseline と候補を比較した

判定は deterministic（`DesignToolkit.missing_evidence()`）。LLM の「十分だと思う」だけでは final に進めない。Qwen 3B/8B/32B 級では summary だけ見て早期に結論を出す失敗が起きやすいため、prompt には **Expert Context Pack**（この問題で最低限守るべき専門的前提）も入れている。思考手順は固定しない。

## 出力

```text
<run_dir>/
  design_proposals.json      # capacity_profile 提案（design_family: capacity_sizing）
  design_review_report.json  # 設計レビュー全体（evidence / 候補 / 選定理由）
  candidate_rankings.json    # baseline + 全候補のランキング
  tool_trace.jsonl           # 1 turn 1 行の完全な監査ログ
  design_plots/*.png
  candidate_runs/candidate_001/…   # 候補ごとの独立したラン
```

`design_proposals.json` の追加フィールド: `design_family` / `final_status` / `selected_candidate_id` / `requires_supervisor_approval` / `expected_outcome` / `constraint_evaluation` / `evidence` / `tool_trace_path` / `candidate_rankings_path`。root の既存フィールドは維持しているので、`--apply-proposals` はそのまま使える。

## 設定

`agents.yaml`:

```yaml
design:
  team:
    count: 1                      # Tool Use designer は 1 人（設計書 §4）。複数人の議論は future phase
  tool_use:
    enabled: true                 # false で従来の summary 直読み designer に戻る
    max_tool_iterations: 24
    max_candidate_runs: 4
    candidate_actor_mode: inherit # 候補ラン内の actor mode。LLM 乗員のときは labeled_rule_base が安い
    plots_enabled: true
```

mode の解釈:

| `design.mode` | `tool_use.enabled` | 動作 |
| --- | --- | --- |
| `none` | — | designer 無効 |
| `labeled_rule_base` | — | 従来の rule proposal |
| `llm` | `false` | 従来の post-run LLM proposal |
| `llm` | `true` | **Tool Use designer** |

## フォールバック

LLM が居ない / JSON を 3 回続けて壊す / `max_tool_iterations` に到達した場合は、決定論的な fallback が同じ evidence 収集を実行する（理論サイジング → 制約評価 → 候補ラン → 比較）。**ラン結果として必ず検証済みの設計が出る**。`decision_source` に `tool_use_rule_fallback:<理由>` が入るので、LLM が到達したのか fallback なのかは常に区別できる。

## 実行

```powershell
ea run ssos_eclss_loop --backend plant_sim --steps 72 --actor-mode labeled_rule_base --design-mode llm
```

`design.mode = llm` は lab vLLM（`agents.yaml` の `design.llm.base_url`）に接続する。VPN が必要。1 turn あたり数十秒〜2 分（32B + thinking）かかるため、24 turn の予算を使い切るレビューは 20〜50 分程度を見込む。候補の再シミュレーション自体は 1 本あたり 1 秒程度。

## 既知の帰結

50 人・現行の budget（4000 kg / 500 MUSD / 14 m³）では、**全員を支える設計は budget を超える**。ARS だけで 52 kg/day の除去が要り、`rack_affine_linear_v1` では 3000 kg 級になるため。したがって designer は `provisional_final` + `requires_supervisor_approval: true` を返すのが正しい挙動になる（設計書 §9 の「参考解として報告」）。budget を上げるか乗員を減らすかは人間の判断であり、エージェントが勝手に threshold を緩めることは preflight で禁止している。
