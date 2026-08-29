# 設計エージェント — ARS / OGS / WRS の処理能力設計

> **範囲**: `ssos_eclss_loop` の **事後設計 (designer) 側だけ**。ランタイム運用 (actor) は [labeled_rule_base.md](labeled_rule_base.md)。
> 従来の summary 直読み designer は [post_run_design_agent.md](post_run_design_agent.md)（そのまま残す）。
> **由来**: 設計書「Tool Use中心のSSOS ECLSS設計エージェント再設計案」(2026-08-28)、および改良実装仕様書 (2026-08-29)。

## なぜ作り直したか

### 一度目: summary 直読みをやめた

従来の designer は、ラン後の `summary` と一部の状態だけを見て `design_proposals.json` を作っていた。人間のエキスパートがやる「必要な情報を自分で取りに行く」「時系列を解析する」「理論必要量を計算する」「候補設計を再シミュレーションで検証する」という工程が無く、しかも `set_parameter` では plant_sim の**処理能力そのもの**を変更できなかった。

### 二度目: LLM から手順の選択権を取り上げた

一度目の作り直しでは、LLM に tool catalog を渡して「次にどの tool を呼ぶか」を毎ターン選ばせていた。実測で次のことが起きた。

- 21 ターン回して候補は 1 本
- `evaluate_design_constraints` を 7 回呼んだ（うち 3 連続が 2 箇所）
- 全員生存に届いた設計 2 本は、LLM が壊れた後に決定論 fallback が作ったもの
- 過去の tool 結果を毎ターン渡し直していたため、6 ターン目にやったことを 15 ターン目に忘れる

原因は、LLM に「何を設計するか」と「作業手順をどう進めるか」を同時に任せていたこと。現在の分担はこうなっている。

```text
LLM     = 設計判断だけ
Python  = 調査・検証・シミュレーション・評価・比較・進行管理
```

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

1. **1 step あたり同一 subsystem のコマンドは 1 回まで。** ARS / OGS / WRS を同じ step に 1 回ずつは許可。ARS を同じ step に 2 回は禁止。2 件目以降は `/eclss/events/operational_rejected`（`reason=duplicate_command_this_step`）。実装は `SsosEclssLoopTeam.apply_outcome()` の**実行ゲート**で、mode に依存しない。
2. **operation duration / busy guard.** `ars_operation_seconds = 4800`、`step_seconds = 1200` なので、ARS は 1 回受理すると `ceil(4800/1200) = 4 step` 作動中になる。作動中の再コマンドは `reason=subsystem_busy` で拒否。OGS / WRS は既定 1 step。実際に何も処理しなかった回は装置を占有しない（WRS の `no_feed`、OGS の `no_water`）。実装は `PlantSimEclssBackend`。`plant_sim.operations.busy_guard_enabled: false` で切り戻せる。

この結果、ARS の実効能力は `capacity_kg_day × goal_scale`（1 日 18 action が上限）になり、50 人の `52 kg/day` にまったく届かないことが**ランに現れる**ようになった。

## 設計判断ループ

実装は `src/scenario/agents/ssos_tool_use_design.py`。

```text
決定論的な証拠収集（毎回・必ず）
   artifacts → 時系列 → 特徴量 → 理論必要能力 → プロット
        |
        v
   ┌─→ DesignState を組み立てる
   |        |
   |        v
   |   LLM に 1 回だけ問う
   |        |
   |        +── propose_candidate → 候補パイプライン（下記）→┐
   |        |                                                 |
   |        +── finish → 終了                                 |
   |                                                          |
   └──────────────────────────────────────────────────────────┘
        |
        v
   決定論的な最終ランキング
```

LLM が返す JSON は 2 種類だけ。

```json
{"decision": "propose_candidate",
 "rationale": "ARS と OGS が不足しているため両方を上げる",
 "fields": {"plant_sim.ars.capacity_kg_day": 23.92,
            "plant_sim.ogs.max_o2_kg_day": 48.3}}
```

```json
{"decision": "finish",
 "rationale": "candidate_002 が全員生存かつ最小",
 "selected_candidate_id": "candidate_002"}
```

**tool 名も、次の手順も、証拠が揃ったかの自己申告も、LLM の出力からは消えた。**

## DesignState — 履歴ではなく現状を渡す

実装は `src/scenario/ssos_eclss_loop/design_state.py`。判断のたびに Python 側で組み立て直し、LLM にはこれだけを渡す。

```json
{
  "baseline": {"crew_initial": 50, "crew_remaining": 0,
               "critical_step_count": 4, "physics_gate": "passed",
               "bottlenecks": ["ogs", "ars"]},
  "installed_capacity": {"plant_sim.ars.capacity_kg_day": 4.5},
  "theoretical_capacity": {"ars": {"required_kg_day": 52.0,
                                   "effective_capacity_kg_day": 4.5,
                                   "coverage_ratio": 0.0865}},
  "candidates": [{"candidate_id": "candidate_001", "crew_remaining": 50,
                  "critical_step_count": 0, "mass_kg": 4689.9,
                  "constraint_status": "over_budget", "physics_gate": "passed"}],
  "current_best": "candidate_001",
  "decisions_left": 3,
  "remaining_candidate_budget": 3,
  "decision_needed": "refine_or_finish"
}
```

過去の tool 結果一覧は入れない。**読み返す過去が無いので、忘れることもない。**実測でプロンプト長は 1 回目 4,333 文字 → 3 回目 5,334 文字で、ターンを重ねても伸びない。

ランごとに `design_decision_state.json` として最後の状態を残す（既存の step ごとの `design_state.jsonl` とは別物なので名前を分けてある）。

## 候補パイプライン（全自動）

LLM が `fields` を返した瞬間に、コード側が必ずこの順で実行する。

```text
設計変数の検証 → 制約評価 → 改ざん検出 → 再シミュレーション
              → 物理ゲート → 評価 → 全候補の比較 → DesignState 更新
```

LLM は「制約評価を呼ぶ」ことも「呼び忘れる」こともできない。選択肢に無い。

**同一設計は 1 回しかシミュレーションしない。** `fields` を正規化（既知キーのみ・ソート・小数第6位で丸め）して SHA-256 で識別する。書き方が違っても同じ機械なら同じ候補として扱い、2 回目は**判断 1 回は消費するが**（実際に使ったので）シミュレーションはしない。

## 判断回数

```yaml
tool_use:
  enabled: true
  max_candidate_runs: 4
  decision_loop:
    max_decisions: 5      # 候補 4 本 + 終了判断 1 回
    max_parse_retries: 1
```

旧 `max_tool_iterations: 24` は**廃止**。tool 呼び出しを数える予算だったので、同じ制約チェックを回し続けるモデルが 20 ターン使っても設計が進まなかった。

## 読めない返事の扱い

```text
空応答 / 壊れた JSON
    → 短い修復プロンプトで 1 回だけ言い直させる
    → それも駄目なら決定論 fallback
```

**fallback は既に検証済みの候補を捨てない。**回線が切れたという理由で検証済みの仕事を捨てるのは間違いなので、`current_best` と残り予算から続行する。証拠収集は最初の判断より前に済んでいるので、やり直さない。予算が残っていれば理論必要量 × margin (1.15 → 1.0 → 1.35) で候補を作り足す。

`decision_source` に `tool_use_rule_fallback:<理由>` が入るので、LLM が到達したのか fallback なのかは常に区別できる。

## Scoring Integrity Guard — 物差しを書き換えていないか

実装は `src/scenario/ssos_eclss_loop/integrity_guard.py`（仕様書 §11）。

良い設計を作る代わりに、採点基準そのものを緩めれば点は上がる。しきい値を緩める、酸素タンクを満タンで始める、乗員を減らす。物理は何も改善していないのにスコアだけ良くなる。これを塞ぐため、**1 step 目の前に**、ランが実際に使った設定とディスク上の元のシナリオを比較する。

| 分類 | 中身 | 扱い |
| --- | --- | --- |
| `scoring_bar` | しきい値、生存判定、乗員数、初期在庫、評価設定、採用予算 | **評価・設計証拠として `invalid`** |
| `operating_point` | ARS / OGS / WRS の能力、バックエンド | 記録のみ（設計ループの目的そのもの） |
| `arm` | agents の運用ポリシー | 記録のみ |
| `other` | 上記以外 | 記録のみ（分類できないという理由で消えないように） |

差分の検出は**部分木の走査**で行う（仕様書 §11.4）。フィールド名を列挙する方式だと、そのフィールドの隣に後から足されたものを取りこぼすため。しきい値の隣はたいてい別のしきい値である。

**仕様書より広く守っている点が 2 つある。**どちらも意図的。

- 仕様書 §11.1 は `simulation.initial_o2_storage_kg` だけを挙げているが、隣の CO₂ と水の初期量も同じ「ランの出だしの難易度」なので一緒に守る
- 評価設定 (`evaluation`) と採用予算 (`design_constraints`) も守る。予算に収まらない設計が予算の方を広げられては、採用判定が意味を失う

結果は `run_integrity.json` に、要約は `evaluation.json` の `integrity` に入る。

## Telemetry-only Physics Gate

実装は `src/scenario/ssos_eclss_loop/physics_gate.py`（仕様書 §12）。

`telemetry.jsonl` **だけ**を読む 9 項目の独立監査。シナリオ設定も agent 設定も行動ログも参照しない。「そのランを生んだ設定を見ないと判定できない」ものは独立した監査ではないし、設定を変更できる設計エージェントに対しては、物差しを動かす余地を残すことになる。

```text
simulator → telemetry → physics gate     （逆参照しない）
```

| # | チェック | 何を見るか |
| --- | --- | --- |
| 1 | `readings_present_and_finite` | 必要な測定値が存在し有限か |
| 2 | `inventories_non_negative` | 在庫が負になっていないか |
| 3 | `totals_monotonic` | 累積量が減っていないか |
| 4 | `carbon_ledger` | 炭素収支が閉じるか |
| 5 | `oxygen_ledger` | 酸素収支が閉じるか |
| 6 | `water_ledger` | 水収支が閉じるか |
| 7 | `stoichiometric_residual` | 電解と Sabatier が化学量論に従うか |
| 8 | `failure_quiescence` | 故障中の装置が処理していないか |
| 9 | `capacity_bounds` | 搭載能力を超えて処理していないか |

**各収支の期首在庫は、シナリオが宣言した初期値ではなくランの最初のテレメトリ行から取る。**これが設定非依存にできた要点。30 step の実ランで 3 収支とも 10⁻¹⁴ 台の丸め誤差で閉じる。

判定は 3 値。**測れなかった項目は `skipped` を返し、`skipped` は合格に数えない。**

```text
failed      1 項目でも failed
incomplete  failed は無いが skipped がある
passed      全項目 passed
```

採用資格があるのは `passed` のみ。監査項目より前に記録した既存ランは `incomplete` になる（設定を見れば「通っている」と言えてしまうが、それはこのゲートの仕事ではない）。

### テレメトリ追加

ゲートを設定非依存にするため、監査に必要な値をテレメトリに載せた（仕様書 §13）。累積総量・busy step・乗員数は元からあったので、追加したのは次の 3 つ。

- `installed_capacity` — 搭載能力と稼働周期のスナップショット
- `failure_state` — サブシステム別の故障状態
- `operations_this_step` — 各サブシステムがその step に実際に処理した量

`operations_this_step` のクリアは **step 境界**で行う。1 step のあいだにテレメトリは複数回ポーリングされるので、poll でクリアすると post_ops 行が書かれる前に消える（実装中に実測で見つけた）。拒否されたコマンドは何も記録しないので、監査が「実際には動いていない装置の仕事」を数えることはない。

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

制約チェックは 2 段階（設計書 §8.1）。

- **Preflight**: schema 破損・NaN/Inf/負値・設計変数外の変更 → `invalid`。**シミュレーションしない**。
- **Constraint evaluation**: budget / bounds 超過は候補を止めず `over_budget` / `out_of_bounds` と**ラベルするだけ**。「過剰設計だが生存性は改善する」も学びなので走らせる。ただし採用段階で扱いが違う。`out_of_bounds` は物理的に製造できないので採用しない（`require_in_bounds_final: true`）。`over_budget` は金の話なので採用対象にはなり、`provisional_final` として人間に上げる（`require_feasible_final: false`）。
- 一部のサブシステムだけを指定した候補も、ステーション全体として価格計算される。指定しなかったサブシステムは**現在インストールされている**容量で計算する。どちらを使ったかは `capacity_source` に出る。

## 評価: まず合格ライン、その中で危険帯の滞在が短い機体、その中で最小

生存はランキングのキーではなく**合格条件**。1 人でも失う設計はそもそも採用できないので、質量削減と人命が天秤に載ること自体が起きない。

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

ランキング自体が目的関数なので、**モデルはこれを上書きできない**。`finish` で別の `candidate_id` を指名しても `parse_notes` に記録されるだけで採用は動かない。どの候補を作って走らせるかは designer の判断、どの検証済み候補を採るかは計算。

`design_penalty`（質量・コスト・体積の正規化和）は**説明用**であり、採用判定の正本ではない。**評価スコア（100 点満点）もランキングには使わない。**

### 何で順位が決まったかを記録する

目的関数は辞書式なので、**最初に差が付いたキーで勝負が決まり、その下のキーは一切参照されない**。実測でこうなった。

```json
{"decided_by": "warning_step_count",
 "winner": "candidate_001", "winner_value": 65,
 "runner_up": "candidate_002", "runner_up_value": 69,
 "not_compared": ["total_mass_kg", "total_volume_m3", "total_cost_musd"]}
```

警戒帯の滞在が 4 step 短いというだけで、**494 kg 重く 75 MUSD 高い機体が採用され、質量は比較すらされていない**。目的関数は仕様どおり据え置きだが、これは人が見て判断すべきトレードなので、`candidate_rankings.json` の `selection.rank_rationale` に残す。

### final status

| status | 意味 |
| --- | --- |
| `approved_final` | 全員生存 + Evidence 完備 + bounds 内 + budget 内 + rank 最上位 |
| `provisional_final` | 選ばれた設計だが、全員生存でない、または budget 超過。`requires_supervisor_approval: true` を付けて報告する |
| `rejected_final` | evidence 不足、invalid、候補が 1 つも作られなかった |

### 採用は別の行為

`design_proposals.json` は status に関わらず書き出す（記録として要る）。採用側に門がある:
`--apply-proposals` は `final_status` が `approved_final` でない文書、または
`requires_supervisor_approval` が付いた文書を**理由付きで拒否する**（ライブラリ既定）。
`ea run` のシミュレーション既定は `--approve-provisional` オンで、人間の介在をなくすため
LLM 設計提案を自動承認する（INFO を出す）。監督ゲートを戻すには
`--no-approve-provisional`。ファイルを渡されたことは承認ではなく、予算超過の設計に金を
払うと決めることが承認である。

## 評価は 1 ランに 1 回だけ

以前は 1 つのランに評価が 2 回書かれていた。設計前に統合評価が `evaluation.json` を書き、設計後に生の設定でもう一度書いて**上書き**していたため、設計エージェントが見た値と人が開くファイルの値が食い違っていた。72 step の baseline で `actor_decision` 10.000 対 6.744、`physical_response` 3.469 対 9.945、合計 23.17 対 26.39。

現在は統合評価が 1 回だけ書く。`summary.json` の `evaluation_score` と `evaluation_compact.score` と `evaluation.json` の `scores.total` は必ず一致する。

## 出力

```text
<run_dir>/
  summary.json
  scenario_config.yaml / agents_config.yaml

  run_integrity.json           # 採点基準の改ざん検出（分類つき全差分）
  physics_gate.json            # テレメトリのみの物理監査 9 項目

  evaluation.json              # integrity / physics_gate の要約を内包
  evaluation.html

  design_decision_state.json   # 最後の DesignState
  design_proposals.json        # capacity_profile 提案
  design_review_report.json    # 設計レビュー全体
  candidate_rankings.json      # baseline + 全候補のランキングと順位根拠
  tool_trace.jsonl             # 人間向け監査ログ（LLM への入力ではない）
  design_plots/*.png
  candidate_runs/candidate_001/…   # 候補ごとの独立したラン（同じ成果物一式）
```

`tool_trace.jsonl` は designer の記憶ではなくなった（記憶は DesignState）。人が後から読む記録として残している。

### 記録に何が残るか

| event | 中身 |
| --- | --- |
| `llm_turn` | 1 回の問いと答え。`message` / `reasoning` / `thinking` / `raw_excerpt` |
| `decision` | その答えの解釈。`choice`（`propose_candidate` か `finish`）と `rationale` |
| `tool_call` | コードが回した処理。`source` がどの段階のものかを言う |
| `candidate_evaluated` | 候補 1 本の検証結果と、その時点の暫定 1 位 |

**発話は切り詰めない。** 以前は 400 字で切っていたので、なぜその寸法にしたのかが後から読めなかった。
記録を残す唯一の理由がそれなので、丸ごと残す。

`thinking` は provider によって置き場所が違う（専用フィールド / パース結果 / 本文中の `<think>` タグ）ので、
3 つとも見て 1 つにまとめている。

`source` はモデルではなく**どの段階が呼んだか**を言う。モデルはもう道具を選ばないので、
モデルの呼び出しとして記録すると嘘になる。`evidence`（最初の読み取り）/ `pipeline`（候補 1 本の検証）/
`rule_fallback`（決定論フォールバックの寸法出し）の 3 つ。

`design_review_report.json` の `thinking_turns` と `design_proposals.json` の `deliberation_messages` にも
同じものが 1 ターン 1 行で入る。以前は最後の結論しか残らず、そこに至った議論が消えていた。

## 設定

```yaml
design:
  team:
    count: 1                      # 単独エンジニア。複数人の議論は future phase
  tool_use:
    enabled: true                 # false で従来の summary 直読み designer に戻る
    max_candidate_runs: 4
    decision_loop:
      max_decisions: 5
      max_parse_retries: 1
    candidate_actor_mode: inherit # 候補ラン内の actor mode
    plots_enabled: true
```

| `design.mode` | `tool_use.enabled` | 動作 |
| --- | --- | --- |
| `none` | — | designer 無効 |
| `labeled_rule_base` | — | 従来の rule proposal |
| `llm` | `false` | 従来の post-run LLM proposal |
| `llm` | `true` | **設計判断ループ** |

## 実行

```powershell
ea run ssos_eclss_loop --backend plant_sim --steps 72 --actor-mode labeled_rule_base --design-mode llm
```

`design.mode = llm` は lab vLLM（`agents.yaml` の `design.llm.base_url`）に接続する。VPN が必要。**CLI は起動前に疎通確認するので、届かない場合は `ENVIRONMENT_ERROR` で止まる**（決定論 fallback には CLI からは落ちない）。

1 判断あたり数十秒〜2 分（27B + thinking）。判断は最大 5 回なので、1 レビューは概ね 5 分前後。候補の再シミュレーション自体は 1 本あたり 1 秒程度。

## 既知の帰結

50 人・現行の budget（4000 kg / 500 MUSD / 14 m³）では、**全員を支える設計は budget を超える**。ARS だけで 52 kg/day の除去が要り、`rack_affine_linear_v1` では 3000 kg 級になるため。したがって designer は `provisional_final` + `requires_supervisor_approval: true` を返すのが正しい挙動になる（設計書 §9 の「参考解として報告」）。budget を上げるか乗員を減らすかは人間の判断であり、エージェントが勝手に threshold を緩めることは preflight と Integrity Guard の両方で塞いである。

**結論は再現するが、経路と設計値は再現しない。**評価に使うなら反復して中央値・最悪値を見る必要がある。
