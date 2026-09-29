# 拡張ガイド

実際に変えたくなる5つと、その継ぎ目がどこにあるか。どれもファイルを1つ足すか設定キーを1つ書き換えるかで済み、ループ本体に触る必要は無い。

| やりたいこと | 触る場所 | 触**らない**場所 |
| --- | --- | --- |
| プラントを別のシミュレータに差し替える | `EclssBackend` を満たすクラス1つ | エージェント、ツール、評価 |
| シナリオを足す | `src/scenario/` にディレクトリ1つ | CLI、runner |
| エージェントの決め方を変える | `agents.yaml` の `mode:` | Python コード |
| 世界のルールを変える | `scenario.yaml` | Python コード |
| 設計者に新しい変数を持たせる | `design_variables.py` ＋ `design_constraints.py` | 判断ループ |

---

## 1. 新しいプラント

`EclssBackend`（`src/environment/ssos/eclss/backend.py`）はメソッド9個の `Protocol` である。テレメトリ取得、アクション目標3つ、サービス4つ、故障スイッチ1つ。3実装が同梱されており、互いにまったく違う。継ぎ目が本物である証拠になっている。

| Backend | 中身 | 規模 |
| --- | --- | --- |
| `mock` | 算術的な動力学。化学は無い | `loop_mock_backend.py`、160行 |
| `plant_sim` | BVAD 代謝率に基づく決定論の質量収支 | `plant_sim/`、4モジュール |
| `ros2` | Docker 上の実 Space Station OS を ROS 2 の action / service / topic で駆動 | `ros2/bridge.py`、362行 |

backend より上は、どれが動いているかを知らない。エージェントは `air_revitalisation` を出す。それが算術の引き算になるか、量論の台帳記入になるか、ROS 2 のアクション目標になるかは `build_eclss_backend`（`scenario_run.py:160`）だけが決めている。

4つ目を足すには:

```python
class MyBackend:                                  # Protocol — 継承する基底クラスは無い
    def poll_telemetry(self) -> EclssTelemetrySnapshot: ...
    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult: ...
    # … あと6つ
```

そして `if backend_kind == "mine":` の分岐を1つ。以降 `--backend mine` が動く。候補の再シミュレーションの中でも動く。

## 2. 新しいシナリオ

シナリオは登録制ではなくファイルシステムから発見される（`runner.py` の `list_scenarios`）。`src/scenario/` 配下で `scenario.yaml` を持つディレクトリはそれだけでシナリオであり、`ea scenarios` に出る。中身は:

```
src/scenario/<name>/
  scenario.yaml     世界のルール、閾値、物理定数、評価
  agents.yaml       チーム規模、ペルソナ、LLM プロバイダ/モデル、ポリシー
  scenario_run.py   step ループ
```

`Scenario`（`src/core/scenario.py`）はメソッド5つの ABC（`name` / `load_config` / `build_simulator` / `build_team` / `run`）。`scrubber_degradation` と `ssos_eclss_loop` は CLI より下でコードを共有していない。2つ目は1つ目に触らずに追加された。

## 3. 別のエージェント

`agents.yaml` の `mode:` を側ごとに。コードは書かない。

| モード | 挙動 | 用途 |
| --- | --- | --- |
| `none` | エージェント無し。プラントが開ループで走る | 物理と方策を切り分ける |
| `labeled_rule_base` | 決定論の閾値方策 | 再現可能な回帰、候補再シミュレーション内の安い乗員 |
| `llm` | Ollama または vLLM | 本番の実験 |

オペレーター側と設計側は独立している。出荷時の既定は **ラベル付き actor ＋ LLM 設計者**。乗員が決定論なので、設計ループの計測が「設計の効果」に帰属し、「違う乗員が違う即興をした効果」に汚染されない。両方 `llm` にすれば LLM 乗員の下で LLM 設計者が回る。設定は対応しており、`candidate_actor_mode` はまさにその場合のためにある（ベースラインは高価な乗員のまま、候補は安い乗員で採点する）。

ペルソナはアーキタイプの**レンズ**（`persona.py:30`）である。**考え方**であって、シナリオ名も閾値も行動カタログも意図的に含まない。だから同じ顔ぶれが、見たことのないシナリオにそのまま移る。

## 4. 別の世界ルール

`scenario.yaml` が世界であり、単位と出典が行ごとに注記してある。以下はすべて生きたつまみである。

```yaml
plant_sim:
  crew:
    size: 50                        # 乗員数
    co2_kg_day_person: 1.04         # BVAD
    activity_factor: 1.0            # 1=通常, 4=運動, 0.7=睡眠
  time:
    step_seconds: 1200              # 1つの判断がどれだけの価値を持つか
    ars_operation_seconds: 4800     # 使ったあと機械が何秒使えなくなるか
thresholds:
  co2_storage_high_kg: 2.0          # 「warning」が始まる位置
design_constraints:
  budgets: {max_total_mass_kg: 4000.0, max_total_cost_musd: 500.0}
  subsystem_bounds:
    ars: {min_capacity_kg_day: 4.5, max_capacity_kg_day: 80.0}
inject_failures: false              # 時刻指定の ARS/OGS/WRS 故障
iteration:
  count: 50                         # 連鎖の周回数
  exploration: {stagnation_window: 4, min_score_delta: 0.25}
```

どれも問題の**パラメータ**ではなく**性格**を変える。`activity_factor` を 4 にすれば乗員は運動中で、需要は4倍になり、余裕のあった設計が余裕を失う。`step_seconds` を下げれば判断回数は増えるが1回の重みは減る。`ars_operation_seconds` を上げれば「機械を拘束するかどうか」が本当の判断になる。`crew.size` を 4 にすれば問題が反転する——出荷ベースラインが生存可能になり、設計課題は「どれだけ大きく」から「どれだけ小さく」に変わる。

ファイルを書き換えずにラン単位で上書きもできる。

```bash
ea run ssos_eclss_loop --set plant_sim.crew.size=120 --set plant_sim.crew.activity_factor=4.0
```

## 5. 新しい設計変数

現在、設計者が寸法を決められるのは3つだけで、この制限は意図的である。`design_variables.py` のドックストリング曰く「回収効率、Sabatier 変換、乗員代謝、健康閾値は**明示的に設計変数ではない**——それらは材料・安全・方針の選択であり、寸法決定問題をぼかす」。

4つ目（例: 船内容積）を足すには:

1. `design_variables.py` に `CapacityVariable` を1件（キー、サブシステム、ドット表記の設定パス、単位、説明）
2. `design_constraints.py` / `scenario.yaml` の `sizing_model` に質量・体積・費用の係数と工学的範囲
3. 大きい機械を実際に使うために運転 payload も上げる必要があるなら `sync_action_payloads` を拡張する（OGS/WRS の先例: ネームプレートだけ上げても、actor が従来のバッチ量を要求し続ければ何も起きない）

判断ループ、ツール、physics gate、評価はすべて `CAPACITY_KEYS` を読むので変更不要。モデルに見せる契約もそこから生成される（`DECISION_CONTRACT` が `list(CAPACITY_KEYS)` を埋め込む）ので、新しい変数は自動的にモデルへ伝わる。

---

## 意図的に変えにくくしてあるもの

上の表への正直な釣り合いとして。

- **採点表の軸**は `evaluation.py` に書かれており設定ではない。重みと基準線は設定だが、8本目の軸を足すのはコード変更である。そうあるべきで、integrity guard は「基準が動いたこと」を検知するために存在するのだから、動かすなら見えなければならない。
- **記憶の3層構造**（私的 / 討議 / 連鎖）は構造である。サイズは設定、層は設定ではない。
- **`scenario.yaml` の目的関数はロード時に検証される。** `primary: require_full_survival` は `design_eval` が実際に実装している目的と突き合わされ、他の値は拒否される。設定を書き換えるだけで挙動から乖離することはできない。

---

## 関連

- [アーキテクチャ](architecture.md) — レイヤ図
- [API 契約](api-contracts.md) — 各層が書く JSONL スキーマ
- [エージェント設計](agent-design.md) — 自由度がどこで始まりどこで終わるか
- [ロードマップ](roadmap.md) — 次に何をやるか、なぜそれが必要と測れたか
