# 実装仕様書アーカイブ

このディレクトリは、`ssos_eclss_loop` の設計エージェントを作るときに実際に使った**実装仕様書の原文**を置いてある。書き直していない。当時決めたこと、当時分かっていなかったこと、そのまま残してある。

なぜ残すのか。このリポジトリの中心は「エージェントが設計を提案し、その提案をシミュレーションで検証し、次の提案へ渡す」という再帰ループであり、そのループ自体が何度も作り直されている。**どこで何が壊れて、何を根拠に作り直したか**が分からないと、今のコードがなぜこの形なのかが読めない。仕様書はその履歴そのものである。

各仕様書は「背景 → 非目的 → 変更対象 → スキーマ → 受け入れ条件 → 実装ステップ」の順で書かれており、`## 受け入れ条件` はほぼそのままテストになっている。

---

## 一覧

| # | 仕様書 | 日付 | 何を決めたか | 実装状態 |
| --- | --- | --- | --- | --- |
| 1 | [Tool Use 中心の設計エージェント再設計案](2026-08-28-tool-use-design-agent-redesign.md) | 2026-08-28 | 設計エージェントを「summary を読んで提案する」から「道具で証拠を集めて再シミュレーションで検証する」へ作り替える。設計変数、制約モデル、評価関数、1 step の command 制約をここで定義した | 実装済み。ただし §10 の自律 planning loop は #2 で置き換え |
| 2 | [Design Decision Loop 改良仕様](2026-08-29-design-decision-loop.md) | 2026-08-29 | LLM から「次にどの道具を呼ぶか」を取り上げる。判断ループ、DesignState、候補パイプライン自動化、Integrity Guard、Telemetry-only Physics Gate | 実装済み |
| 3 | [Chain Memory 最小実装仕様](2026-08-30-chain-memory.md) | 2026-08-30 | 周回をまたぐ記憶を 4 KB 一枚で持つ。良い設計が次周で忘れられて全滅する事故への対処 | 実装済み |
| 4 | [Scoring / 停滞探索 実装仕様](2026-08-30-scoring-and-stagnation-exploration.md) | 2026-08-30 | 費用・質量の満点ラインを「生存できる最小設計」寄りに移す。スコアが動かなくなったら探索モードへ切り替える | 実装済み |

---

## 仕様書とコードの対応

### 1. Tool Use 中心の設計エージェント再設計案 (2026-08-28)

**動機**: 当時の事後設計エージェントは、ラン終了後の `summary.json` と一部の状態だけを読んで `design_proposals.json` を書いていた。人間のエンジニアがやる「必要な情報を取りに行く」「時系列を解析する」「理論値を計算する」「候補を再シミュレーションで検証する」が一つも無かった。

**実装**:

| 仕様書の節 | コード |
| --- | --- |
| §5 Tool 基盤 / §5.2 Tool registry | `src/scenario/ssos_eclss_loop/design_tools.py` — 9 個の決定論ツール |
| §6 設計変数スキーマ | `src/scenario/ssos_eclss_loop/design_variables.py` |
| §7 1 step 内の command 制約 / §7.1 busy guard | `src/scenario/agents/ssos_eclss_loop_team.py`、`src/environment/ssos/eclss/plant_sim/model.py` |
| §8 制約モデル (`rack_affine_linear_v1`) | `src/scenario/ssos_eclss_loop/design_constraints.py`、`scenario.yaml` の `design_constraints:` |
| §9 評価関数 | `src/scenario/ssos_eclss_loop/design_eval.py` |
| §12 再シミュレーション設計 | `design_tools.py` の `run_design_candidate` |

**コミット**: `bee61ba` `33c7722` `beb96d6` `6cf8ac7` `8c59d78` `dac8bf1`

**この仕様書のうち置き換えられた部分**: §10「Tool-use designer の自律 planning loop」。実走行で、モデルが同じ制約チェックを 21 ターン繰り返して候補を 1 本しか作らないまま 15 分を使う挙動が観測された。仕様書 #2 がこの節を丸ごと置き換えている。

---

### 2. Design Decision Loop 改良仕様 (2026-08-29)

**動機**: #1 の実装は、LLM に「何を設計するか」と「作業手順をどう進めるか」を同時に持たせていた。手順まで任せると、ループを前に進める力がどこにも無い。

**決めたこと**: `LLM = 設計判断だけ` / `Python = 調査・検証・simulation・評価・比較・workflow 管理`。モデルは毎ターン 1 枚の現状を渡され、「この設計を試して」か「終わり」だけを返す。

| 仕様書の節 | コード |
| --- | --- |
| §5 Design Decision Loop | `src/scenario/agents/ssos_tool_use_design.py` |
| §6 DesignState | `src/scenario/ssos_eclss_loop/design_state.py` |
| §7 Candidate Pipeline 自動化 | `ssos_tool_use_design.py`（固定順で 8 ツールを回す） |
| §8 LLM 呼び出し回数 / §9 Parse Failure | `agents.yaml` の `design.tool_use.decision_loop`、`src/core/llm/parsing.py` |
| §11 Scoring Integrity Guard | `src/scenario/ssos_eclss_loop/integrity_guard.py` |
| §12 Telemetry-only Physics Gate | `src/scenario/ssos_eclss_loop/physics_gate.py` |
| §13 Telemetry 追加 | `src/environment/ssos/eclss/plant_sim/backend.py` |
| §14 Evaluator 統合 | `src/scenario/ssos_eclss_loop/unified_evaluation.py` |
| §15 Design Ranking | `design_eval.py` の `rank_candidates` / `rank_rationale` |

**コミット**: `21681b7` `09756bd` `9befbb9` `34b5306` `c331d42` `8dd7944` `67f3bd0` `b828332`

**仕様書に無く、後から足したもの**: 連鎖全体からの最終回答 (`chain_selection.py`, `67f3bd0`)。1 周ごとの勝者は決まっていたが、50 周を 1 つの答えにまとめる部分が仕様書に書かれていなかった。

---

### 3. Chain Memory 最小実装仕様 (2026-08-30)

**動機**: 50 周の実走行を解析したところ、1 周の中では証拠が欠けなく集まっているのに、**周をまたぐと過去の成功設計が保持されていなかった**。

代表例が仕様書の冒頭に書いてある。

```
iteration 24: ARS=20.8, OGS=42.0, WRS=1.8, crew=50/50, score=66.18
iteration 25: WRS 中心の部分提案 → 次の周で ARS=4.5, OGS=9.25 に戻り crew=0/50
```

良い設計は棄却されたのではない。**忘れられた**。

**実装**: `<chain_dir>/compact_chain_memory.json` 一枚（4 KB 上限）。全員生存した最良設計、直前に実際に設置された寸法、各サブシステムの計算下限（`0aaec84` 以降は実測値）、この連鎖が既に踏んだ失敗パターンだけを持つ。読み手が有限コンテキストの言語モデルなので、サイズは実装詳細ではなく設計制約である。

| 仕様書の節 | コード |
| --- | --- |
| スキーマ / サイズ制限 / 更新ロジック | `src/scenario/ssos_eclss_loop/chain_memory.py` |
| `load_run_artifacts` の返却追加 | `design_tools.py` の `load_run_artifacts` → `chain_memory_compact` |
| Prompt 追加案 | `design_state.py` の `build_design_state` → 判断ページの `chain_memory` |
| 更新タイミング | `src/scenario/jobs/iterate.py` |

**コミット**: `c0dcb4f`

**この仕様書が明示的にやらないと書いたこと**: vector DB を入れない。raw telemetry を context に入れない。agent loop 全体を再設計しない。最適化アルゴリズムを新設しない。

**この仕様書が未解決として残し、後で閉じた点**: chain memory は**見せるだけで適用しなかった**。部分提案が省いたフィールドを落とす挙動そのものは残っており、仕様書はそれを誤魔化さず明記していた。実走行では「見せる」だけで巻き戻りは初回以外消えている（[実験記録](../results.md)）。その後 `0aaec84` が運搬側そのものを修正し、あわせてこの仕様書が導入した計算下限を実測値に置き換えた。

---

### 4. Scoring / 停滞探索 実装仕様 (2026-08-30)

**動機**: #3 で巻き戻りは止まった。次に見えたのは 2 つ。

1. 費用・質量の満点ラインが**全員死ぬベースライン**に置かれていたので、生存できる設計が軒並み低く採点されていた（40 点満点で 11.57 点など）
2. スコアがほぼ動かないまま、WRS の同じ近傍を往復していた

**実装**:

| 仕様書の節 | コード |
| --- | --- |
| Footprint 評価仕様（満点ライン設定） | `src/scenario/ssos_eclss_loop/evaluation.py`、`scenario.yaml` の `evaluation.footprint` |
| designer-facing context の整理 | `design_state.py`（体積と over_budget を単独では見せない） |
| Stagnation Exploration | `chain_memory.py` の `_detect_stagnation` / `_exploration_directive`、`scenario.yaml` の `iteration.exploration` |
| survival tier | `chain_memory.py` の `survival_tier` |

**コミット**: `d57ad2d` `4124475`

**効果**: 生存可能設計の Cost/Mass が 5〜6 点台から 14 点台へ。ユニーク設計数が 11 から 17 へ。詳細は[実験記録](../results.md)。

---

## 読む順番

初めて読むなら、仕様書より先に [設計エージェント](../memo/ssos_eclss_loop/tool_use_design_agent.md)（今のコードの説明）を読んだほうが早い。仕様書は「なぜそうなっているか」を掘るときに読む。

- 今のループの形を知りたい → [設計エージェント](../memo/ssos_eclss_loop/tool_use_design_agent.md)
- 何が起きたか実測を見たい → [実験記録](../results.md)
- エージェントに何を見せて何を決めさせているか → [エージェント設計](../agent-design.md)
