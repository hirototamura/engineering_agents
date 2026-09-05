# trunk → main コードレビュー（2026-08-30）

対象: `origin/main...origin/trunk`（247 ファイル / +125,950 行、うち src・tests・scripts が 111 ファイル / +98,114 行）

前提: `python3 -m pytest --ignore=tests/e2e` は **993 passed / 4 skipped**、`mkdocs build --strict` も通る。
つまり以下は「テストが落ちている」話ではなく、**テストが見ていない場所**の話である。

指摘はすべて実際にコードを走らせて再現を確認した。未再現の推測は載せていない。
主要な再現スクリプトは `trunk-to-main-2026-08-30-evidence.sh`（同ディレクトリ）。

スコープ注記: コード検証は `34775aa` で実施した。マージ先の tip は `7c42dfc` だが、
`git diff --name-only 34775aa 7c42dfc` は `src/` と `tests/` を**一切含まない**（docs と
生成物のみ）ので、コードに関する指摘はすべて tip でも有効。
リポジトリ成果物に関する指摘（C-10, H-12）は `origin/trunk` の tip に対して計測した。

---

## 総評

設計思想は良い。`physics_gate.py` / `integrity_guard.py` / `design_eval.py` の docstring は
「得点より物理」「設計エージェントに自分の物差しを触らせない」「どれだけ質量を節約しても人命は買えない」
という正しい問題意識をはっきり言語化している。統計モジュールも scipy 相当を自前実装しながら
検算 8 項目すべて正しい（後述）。テストにも空assert・トートロジー・例外飲み込みが 1 件も無い。
ハッカソン 2 日でここまで書けているのは率直に驚く。

問題は**その思想が実装で徹底されていない**こと、しかも失敗の仕方に一貫した型があることだ。

> **通底する構造的欠陥 1: 安全ゲートが fail-open している。**
> 「測れなかった」「記録が無い」「ステータスが書かれていない」が、
> どのゲートでも例外なく **合格 / 有効 / 承認済み** として扱われる。（C-2, C-3, C-4）

> **通底する構造的欠陥 2: 検知した違反が、強制する場所に配線されていない。**
> 不正を検出する関数は存在し、正しく動き、JSON に結果も書く。
> しかしそれを読んで拒否する側が存在しない。（C-1）

> **通底する構造的欠陥 3: 記録が現実と一致しない。**
> 「何を適用したか」を指すパスの中身が別物になり（C-6）、
> 「どの設計値でこの結果が出たか」の対応がシミュレートしていない値とすり替わる（C-9）。
> 監査可能性を価値の中心に置くプロジェクトとして、ここは C-1 と同じ重さがある。

`main` に入れる前に C 系の解消を必須としたい。とくに **C-10（41.7 MiB のバイナリ）だけは
マージ後に修正できない**ので、これは順序として最初に決める必要がある。

内訳は CRITICAL 12 件・HIGH 20 件・MEDIUM 40 件。
サブシステム別の網羅は 5 系統に分けて実施した（設計ループ中核 / LLM・tool use /
CLI・ジョブ・iterate / 解析・レポート / アーキテクチャ・テスト・CI）。

**公開済みの数値について。** 「物理シミュレーションの結果」は概ね健全で、
実 `plant_sim` の物理監査も本物である（後述）。一方**その上の解析・報告層には
公開値に届く欠陥がある**: 同じ物理定数 ρ\* に 2 つの異なる値が公開されており（C-11）、
うち Markdown が引用している側は分割シードで ±35% 振れる。
公開表の balanced accuracy 列はどのモデルも予測していない事象を採点している（H-18）。
**論文・レポートを出す前に C-11 / H-18 / H-19 は再導出が必要。**

---

## CRITICAL

### C-1. 採点基準を書き換えた run が `approved_final` として自動採用される

これが本レビュー最大の問題。**不正検知の仕組みは完成していて、強制する配線だけが全て欠けている。**

因果の連鎖（すべて実測で確認）:

| # | 場所 | 起きること |
| --- | --- | --- |
| 1 | `design_proposals.py:50-63` | ルールベース設計エージェントが `thresholds.co2_storage_high_kg` の変更を提案 |
| 2 | 同 `ALLOWED_SET_PARAMETER_TARGETS` | 適用側がそれを許可された target として受け入れる |
| 3 | `integrity_guard.py:44-45` | ガードは同じ `thresholds` を `SCORING_BAR` と分類し検知する |
| 4 | `unified_evaluation.py:237-243` | `evaluation.json` に `status: "invalid"`, `invalid_reasons: ["scoring_bar_modified"]` を書く |
| 5 | `integrity_guard.py:130-132` | それを拒否に変える `evidence_status()` は **本番呼び出し元がゼロ（dead code）** |
| 6 | `design_eval.py:141` | 採用判定は `evaluation_status` を outcome に**コピーするだけで読まない** |
| 7 | 結果 | `final_eligible: True` → `final_status: approved_final`, `requires_supervisor_approval: False` |

```text
final_eligible      : True []
final_status        : approved_final
needs approval      : False
```

```text
$ rg -n "evidence_status" src/ --glob '*.py' | rg -v "def evidence_status"
  none -> dead code
```

エンドツーエンドでも確認済み。AGENTS.md が「正典」と呼ぶ 2-run スモークをそのまま実行すると:

```text
run 1 set_parameter targets: ['agents.actor.policy.co2_storage_high_kg',
                              'thresholds.co2_storage_high_kg']
run 2 CLI exit code: 0
run 2 evaluation status : invalid
run 2 invalid_reasons   : ['scoring_bar_modified']
```

`plant_sim` の 50 step 実行では、閾値を書き換えた run が
`score 57.685514` の満点付き `invalid` として残り、
乗員 50/50 を保った別ケースでは `approved_final` まで到達した。
**CLI は警告ひとつ出さず exit 0 で「Done」と表示する。**

なお `src/scenario/jobs/iterate.py:303-304` は `--iterate` チェーンでは
`set_parameter` を一律破棄しており、対策はこちらにだけ存在する。
**対策が無いのは AGENTS.md が推奨している側のパス**である。
（ただしこの一律破棄は `agents.actor.policy.*`（ARM 相当・正当な設計自由度）も
巻き込んで捨てているので、`classify_path()` ベースに寄せるのが筋。）

修正方針:
1. `ALLOWED_SET_PARAMETER_TARGETS` から `thresholds.*` を外す（最小の塞ぎ方）
2. 採用パス（`mark_final_eligibility`）で `evaluation_status == "invalid"` を不適格理由にする
3. `evidence_status()` を実際に呼ぶか、削除する（dead code のまま残すのが一番危険）
4. `status: invalid` の run は CLI が非ゼロ終了か、最低限赤字で警告する

### C-2. 物理ゲートの質量保存則が、データが無いときに「合格」を出す

`src/scenario/ssos_eclss_loop/physics_gate.py:79-80, 210-275`

```python
def _number(value: Any) -> float:
    return float(value) if _finite(value) else 0.0
```

3 本の ledger は入出力の各項を `_number()` 経由で読む。テレメトリにその項が
**存在しない**場合、欠損は「流量ゼロ」に化ける。収支が 0 − 0 = 0 になり、
**残差 0.0 で `passed`** が出る。

```text
carbon_ledger   passed  residual=0.0
oxygen_ledger   passed  residual=0.0
water_ledger    passed  residual=0.0
-> 流量を一切記録していない run に対して保存則が「成立」と証明されている
```

同モジュールの docstring（`:14-17`）は自ら
「`skipped` は合格ではない。測れなかった量は未測定として報告する」と宣言しており、
`_totals_monotonic`（:176-177）と `_stoichiometric_residual`（:285-288）は
正しく `SKIPPED` を返す。**3 本の ledger だけがこの規約を破っている。**

同じ `_number()` 依存で向きが逆の偽陽性もある。`_capacity_limits`（:361-371）で
`ars_operation_seconds` または `goal_scale` が欠けると許容量が 0 になり、
正常な運転が capacity 違反として報告される:

```text
complete telemetry             -> passed
ars_operation_seconds missing  -> failed  [{'processed': 1.0, 'allowed': 0.0}]
goal_scale missing             -> failed  [{'processed': 1.0, 'allowed': 0.0}]
```

修正方針: ledger と capacity は必要項が 1 つでも欠けたら `SKIPPED`（→ 全体 `incomplete`）。
`_number()` による欠損→0 の暗黙変換を収支計算から外す。

**公平のための補足**: 実際の `plant_sim` run では残差 `-1.78e-15` 等の正常値が出て
9 チェックすべて `passed`・`skipped` ゼロになることを確認した。
**これは潜在バグであり、既存 plant_sim 結果を無効化するものではない。**
ただし `docs/en/design-loop-analysis.md:116` の「O2 と CO2 の ledger は厳密にゼロ」は
現行コードの出力（`-1.78e-15`）と一致しないので、どの版で得た数字か確認のうえ再導出すべき。

### C-3. 監督者ゲートが、ステータス未記入の文書を「承認済み」として通す

`src/scenario/ssos_eclss_loop/design_proposals.py:324-325`

```python
status = proposals.get("final_status")
if status is not None and status != FINAL_STATUS_APPROVED:
```

`final_status` が**無い**文書は理由ゼロ＝無条件採用になる。
そして `build_design_proposals_from_run`（`labeled_rule_base` パス）は `final_status` を書かない:

```text
rule-path document (no final_status): NO REASONS -> auto-adopted
same doc marked provisional_final  : ['final_status=provisional_final']

applied with approve_provisional=False; thresholds now: {'co2_storage_high_kg': 1.8}
```

docstring が「design doc §9 の『自動採用しない』をここで強制する」と書いているその場所が、
正典スモークで使われる設計モードに対して完全に無効化されている。
`design_eval.py` の適格性判定もこのパスでは一切呼ばれない。
実測で乗員 49/50 を失った run が、適格性判定なしで 5 件の提案を出力した。

修正方針: `final_status` 欠落を「未評価」として拒否する（fail-closed）。
ルールベースパスにも `mark_final_eligibility` を通し `final_status` を必ず書く。

### C-4. `integrity` 情報が無い run が「監査済み・問題なし」として記録される

`integrity_guard.py:130-132`、`unified_evaluation.py:269`

```python
return "invalid" if integrity.get("scoring_bar_modified") else "valid"
...
integrity = integrity or {}
```

`evidence_status({})` → `valid`。呼び出し側が `integrity` を渡し忘れると
空 dict で埋められ、`scoring_bar_modified: False` が**検査した事実なしに** summary に刻まれる。

実害: コミット済み `src/experiments/results/evaluation.html` に埋まっている
公開済み run 18 件（`status: scored`）は `integrity` キー自体が存在しない。
にもかかわらず `schema_version` は新旧どちらも `"2.0"` のままなので、
消費側は「監査して問題なし」と「監査していない」を区別できない。

修正方針: `integrity` を必須引数にする。情報が無ければ `unknown` を返し、
`unknown` を合格として扱わない。スキーマ変更に合わせて `schema_version` を上げる。

### C-5. 破壊的なファイル操作が 3 種類ある

**(a) `--output-dir` が任意ディレクトリを無確認で再帰削除する**

`src/scenario/jobs/resolve.py:98-101`

```python
run_dir = Path(output_dir)
if recreate_output and run_dir.exists():
    shutil.rmtree(run_dir)
```

`--output-dir` は公開フラグで、`--run-id` 側にある `sanitize_run_id()` 保護を通らない。

```text
before: 2 user files
after : thesis.txt present? NO-DELETED
after : nested/data.csv present? NO-DELETED
```

`ea run ... --output-dir ~/Documents` で中身が消える。確認プロンプトも dry-run も無い。

**(b) run が自分の `--output-dir` の外にファイルを書き、既存ファイルを潰す**

`unified_evaluation.py:282` の `write_evaluation_browser(run_path.parent, ...)` は
run ディレクトリの**親**に `evaluation.html` を書く。`--output-dir` を指定しても
その 1 階層上に書き込むため、そこにあったユーザの `evaluation.html` が消えた。

**(c) 同じ `--run-id` での再実行が前回成果物を黙って破棄する**

`src/core/event_log.py:52-55` の無条件 `rmtree`。AGENTS.md がわざわざ
「Run 1 の出力が消えるので run-id を分けよ」と注意書きしている事実自体が、
この UX が誤っている証拠である。

修正方針: 既存ディレクトリが run 生成物（`summary.json` 等）を含まない場合は削除を拒否。
上書きには明示的な `--force` を要求する。生成レポートは run ディレクトリ内に書く。

### C-6. `--apply-proposals` の入力ファイルが実行中に破棄され、出力で上書きされる

C-5(c) の帰結だが影響が別種なので分けて挙げる。
proposals を読み込んだ後に run ディレクトリが `rmtree` され、
run 終了時に**同じパスへ新しい提案が書かれる**。

```text
input file content BEFORE : [{'fields': {'initial_co2_mass': 5.625}}]
CLI exit: 0
content at that path AFTER: [{'fields': {'initial_co2_mass': 7.03125}}]
identical to what was applied? False
summary.apply_proposals_path -> .../r1/design_proposals.json
```

`summary.json` は `apply_proposals_path` を記録するが、
**そのパスの中身はもう適用されたものではない。**
監査可能な設計証拠を売りにするプロジェクトとして、これは致命的。
「何を適用したか」を後から再構成できない。

修正方針: 適用した文書の実体を run ディレクトリ内に
`applied_proposals.json` としてコピーする（`--iterate` 側は既にやっている）。

### C-7. ミッション全体を生き延びた設計が、off-by-one で最下位に落ちる

3 つの独立した挙動が積み重なって、**ループが最良の設計を積極的に捨てる**。

**(a) TCL の右打ち切りが 1 step 足りない** — `evaluation.py:463`

```python
end_time = _time_s(canonical[-1], step_seconds)
```

最終**サンプル**の時刻を使うため、N step の run では `(N-1) × step_seconds` になる。
既定 `reference_seconds = 57600` は 48 step 分のミッション時間そのものだが:

```text
steps= 48  mission covered= 57600s  last sample=56400.0  -> right_censored  score=None
steps= 49  mission covered= 58800s  last sample=57600.0  -> scored          score=10.0
```

参照期間をちょうど完走した run が打ち切り扱いになる。

**(b) 1 軸でも None なら総合点が丸ごと None になる** — `evaluation.py:1060-1064`

```python
complete = all(_finite_number(score) for score in scores)
total = sum(float(score) for score in scores) if complete else None
```

実測できた 84 点を捨てて `total: None`, `status: incomplete` にする。

**(c) 未採点は最下位にソートされる** — `design_eval.py:239`

```python
-(score if score is not None else -1.0),
```

合成結果:

```text
rank 1  B_worse_but_scorable       key=(False, -50, -40.0)
rank 2  A_survives_full_mission    key=(False, -50, 1.0)
```

**参照ミッションを完走した設計が、完走しなかった劣る設計の下に並ぶ。**
目的関数が不連続で、最も良い領域に穴が空いている。
`docs/en/results.md` が記録する探索の退行を疑うなら、まずここを見るべき。

修正方針: (a) 比較対象をミッション終了時刻（`最終サンプル + step_seconds`）にする。
(b) 採点済み軸の合計と適用可能満点を併記し、部分採点を捨てない。
(c) 未採点を最下位に固定する前に (a)(b) を直す。

### C-8. 提案のハッシュが衝突し、別の設計が「重複」として一度も試験されない

`src/scenario/ssos_eclss_loop/design_state.py`

`normalize_fields` が非数値を捨てるため、文字列値の提案は `{}` に正規化される。
LLM が JSON で数値を引用符付きで返すのはごく普通に起こる。

```text
normalize_fields({'plant_sim.ars.capacity_kg_day': '20'}) = {}
candidate_hash({'plant_sim.ars.capacity_kg_day': '20'}) = 44136fa355b3678a
candidate_hash({'plant_sim.ogs.max_o2_kg_day': '40'})   = 44136fa355b3678a
candidate_hash({})                                      = 44136fa355b3678a
a and b collide: True
```

`find_duplicate` はこれを既出とみなしシミュレーションを抑止する。
**互いに無関係な設計案が 1 つに潰れ、しかも黙って消える。**

修正方針: `normalize_fields` は数値化できない値を捨てずに拒否（エラー）する。
`candidate_hash` は正規化前のキー集合も含める。

### C-9. 監査で却下された設計値が、別の機体で測った結果と対にして記録される

`src/scenario/ssos_eclss_loop/design_ensemble.py:425-431`

```python
    if selected is not None:
        selected = dict(selected)
        selected["fields"] = dict(kept_fields)
        for index, row in enumerate(ranked):
            if row.get("candidate_id") == selected_id:
                ranked[index] = selected
```

`kept_fields` は、監査エージェントが却下したキーを **installed 値に差し替えた**ハイブリッドである。
それを **ranked 行そのものに書き戻す**。ranked 行は `design_tools.py:1247` 経由で
`candidate_rankings.json` / `design_review_report.json` に直列化され、`_ranking_row`（:1255-1279）は
`fields` を `crew_remaining` / `physics_gate_passed` / `evaluation_compact` の**隣に並べる**。

しかしそれらの数値は**差し替え前の fields で走らせたシミュレーション**の結果である。
差し替え後の値で再シミュレーションは行われない。

```
実際にシミュレートされた値 : wrs.max_feed_l_per_operation = 12.0
candidate_rankings.json の記録: wrs.max_feed_l_per_operation = 10.0
同じ行の crew_remaining     : 50/50 physics_gate_passed: true final_eligible: true
```

`chain_selection.collect_chain_candidates` はこの `candidate_rankings.json` を読むため、
`chain_final_answer.json` が**存在しない機体の性能**をチェーンの答えとして提示する。
`--apply-proposals` はその fields を、別の機体の `expected_outcome` を添えて出荷する。

既存テスト（`test_rejected_items_are_pinned_to_installed`）は
`merged["changes"][0]["payload"]["fields"]` しか見ておらず、ranking 行を検証していない。

修正方針: 差し替えた fields で再シミュレーションするか、
ranked 行には**シミュレートした fields のみ**を残し、監査後の値は
`changes` 側だけに置いて「未検証」と明示する。

### C-11. 同じ解析の 2 つの公開成果物が、同じ物理定数に別の値を載せている。しかも片方はシード雑音

`src/tools/analysis/report.py:193-195`（表・全格子）vs `:449-451, 497`（散文・**訓練半分のみ**）

同じ ρ\* というラベルで、独立に計算された 2 つの値が別の読者に届いている。

```text
HTML レポート     : ARS (CO2 removal)  0.199  0.128  1.95  0.869
Markdown 散文     : ρ*_ARS ≈ 0.17    （docs/en/design-loop-analysis.md:136）
```

さらに悪いことに、散文が引用している 0.17 の枝は
`_predictive_models(..., seed: int = 20260829)`（:404）で選ばれた**任意の半分**に対する当てはめである。
同じ手続きを他の 200 通りの分割で回すと:

```text
published (seed 20260829): ARS rho* = 0.172515
across 200 other split seeds:
  mean=0.197334  sd=0.027115  min=0.124339  max=0.252743
  range = 0.128404 = 65.1% of the mean
  published value sits -0.92 sd from the across-split mean
```

**公開された 0.17 は、レポートが一切言及していない分布の下側の裾**にある。
そして分割平均 0.197 は、HTML の表の 0.199 とほぼ一致する。

`report.py:399-401` のコメントは
「three is stable across splits without smearing the transition」と述べているが、
**実測はその主張を否定している。**
ρ\* は `report.py:464` の "Liebig on margin" 特徴量にも入るので、モデル比較も同じ不安定性を継ぐ。

修正方針: ρ\* の定義を 1 つに統一する（全格子の枝を正典にするのが自然）。
分割依存の量を公開するなら、複数分割にわたる平均と sd を併記する。

### C-12. 実験キャッシュがグリッド添字だけを鍵にしており、新しいラベルと古い物理が対になる

`src/tools/analysis/experiments.py:149-152`

```python
    run_dir = Path(root) / spec.run_id
    marker = run_dir / ("chain_summary.json" if spec.iterate else "summary.json")
    if cache and marker.is_file():
        return RunOutcome(spec, run_dir, 0, cached=True)
```

`run_id` は格子上の位置から作られる（`f"{prefix}-a{i:02d}-o{j:02d}"`）だけで、
`capacity` / `overrides` / `steps` / `seed` は**一切キャッシュ鍵に入らない**。
`campaign.build_specs(quick=True)` は各格子を `(first, middle, last)` に間引くので、
同じ `run_id` が**まったく別の設計**を指す。

```text
run_id         quick (ars, ogs)   full (ars, ogs)   same?
grid-a01-o01   (26.0, 30.0)       (8.0, 14.0)       False
--> 9 個の共通 run_id のうち 8 個が別の設計を指す

full spec grid-a01-o01 asks for: ars = 8.0
execute(...) -> cached=True returncode=0  （シミュレータは呼ばれない）
  ars          = 8.0   <- ラベル。位相図のセルと周辺スライスがこれを使う
  capacity_ars = 26.0  <- 設定。rho_ars はこれから作られる
  steps        = 5     <- spec.steps は 72 だった
```

位相図のセル・臨界スライス・生存グループがすべて誤った座標に帰属し、
`returncode=0` で警告も出ない。

**出荷済みデータセットについては、ラベルと設定が全件一致することを確認した**ので、
公開値はこのバグで汚染されていない。ただし**汚染されていても何も知らせない**構造である。

修正方針: `run_id` に加えて spec の内容ハッシュ（capacity / overrides / steps / seed）を
キャッシュ鍵に含める。

### C-10. 41.7 MiB のバイナリ run アーカイブが履歴に永久追加される

```text
experiments/runs/phase1-no-chain-memory.tar.gz  11209899
experiments/runs/phase2-chain-memory.tar.gz     10632031
experiments/runs/phase3-rescored.tar.gz         10868504
experiments/runs/phase4-multiagent.tar.gz       11053652
TOTAL: 43764086 bytes = 41.74 MiB   （4 件すべて本 diff で A = 追加）
.git 全体: 46M
```

**リポジトリ履歴の約 9 割がこの 4 ファイル**になる。diff もレビューもできず、
git 履歴は追記専用なので、**マージ後に消すには履歴の書き換えが必要**になる。
以後すべての `git clone` が恒久的にこのコストを払う。

他の指摘は後から直せるが、これだけは直せない。**マージ前に決着させる必要がある唯一の項目。**

修正方針: Git LFS、リリースアセット、または外部ストレージ（run の再生成手順を添えて）。

---

## HIGH

### H-1. 採点表が、乗員の生存より「軽くて安い」を 2 倍重く評価している

`src/scenario/ssos_eclss_loop/evaluation.py:29-36`

```python
CREW_MAX = 20.0      # 乗員生存
COST_MAX = 20.0      # コスト
MASS_MAX = 20.0      # 質量
```

実測（`plant_sim`, 48 step, 既定設定）— **乗員全滅でも 58.31 点**:

```text
crew 0 / 50  |  TOTAL 58.307607 / 100
  actor_survival            0.0 / 20.0
  cost                     20.0 / 20.0
  mass                     20.0 / 20.0
```

さらに実効的な影響が大きい。`design_eval.py:219-240` は適格候補の順位付けを
**得点のみ**で行う。適格候補は定義上全員生存なので `actor_survival` は
全候補 20/20 で**順位に一切寄与しない**。
結果、実際に順位を決める 80 点のうち **40 点（＝半分）が「小さく安いこと」**になる。

`design_eval.py:1-7` は「どれだけ質量を節約しても人命は買えない」と宣言し、
`_footprint_axis`（`evaluation.py:892-909`）の docstring 自身も
「既定の満点ラインは間違っていた。それは全乗員を失うベースライン機体だった」と認めている。
`full_at` 導入はレンジを詰めただけで、**ベースライン機体が 40/40 を取る事実は変わっていない**。

なお `tests/scenario/test_ssos_eclss_loop_evaluation.py:313`
`test_the_baseline_machine_scores_full_marks_on_what_it_costs()` が
この挙動を期待値として固定している。つまりこれは事故ではなく意図的な設計判断であり、
**バグ修正ではなくプロダクト判断として決め直す必要がある**（テストも同時に変わる）。

### H-2. 評価ブラウザが 100 点中 40 点を画面から落としている

`src/scenario/ssos_eclss_loop/evaluation_browser.py:9-16, 247-254`

```text
engine axes : [..., 'cost', 'mass', ...]     ← 8 軸
browser axes: [...]                          ← 6 軸
hidden      : ['cost', 'mass'] = 40.0 points
```

`scorebar()` も `compareTable()` も `AXIS_ORDER` で絞るため、
**質量とコストだけが違う 2 run は比較画面上で完全に同一に見える。**

加えて `AXIS_META`（:248-253）の満点値がエンジンと食い違う:

| 軸 | AXIS_META | エンジン |
| --- | --- | --- |
| `actor_survival` | 50 | 20 |
| `actor_decision` | 10 | 5 |
| `physical_response` | 10 | 5 |

`fmt(axis.max_score ?? meta.points)`（:303）は `max_score` 欠落時に
`meta.points` に落ちるため `0.4 / 50` という**誤った分母**が表示され得る。

エンジン側は `cost`/`mass` の満点 20 をテストしているのに（同テスト :143-144）、
HTML の軸リストとエンジンの軸集合を突き合わせるテストが無いため検出されていない。

### H-3. `api-contracts.md` の採点数値がほぼ全項目で実装と不一致

`docs/en/api-contracts.md:552-583`

| 項目 | api-contracts.md | 実装 |
| --- | --- | --- |
| actor survival 満点 | 50 | 20 |
| actor decision 満点 | 10 | 5 |
| device response 満点 | 10 | 5 |
| actor 無し時の総点 | 80 | 90 (`NO_ACTOR_MAX`) |
| `schema_version` | `1.0` | `2.0` |
| `cost` 軸 (20 点) | 記載なし | 存在 |
| `mass` 軸 (20 点) | 記載なし | 存在 |

`physics_gate.checks` の形も `[{"name","passed"}]` と書かれているが、
実際は `{"name","status","reason","details"}` の 9 チェックで `status` は三値。
「physics gate 失敗は `status: invalid`」も実装と異なる
（`unified_evaluation.py:239` は `backend == "plant_sim"` のときだけ）。
`docs/ja/eclss-evaluation-implementation.plan.md:31` も 50 点表記のまま。

**「API 契約」を名乗る文書が契約として機能していない。**

### H-4. 生成物が git 追跡下にあり、研究室 LAN のアドレスが焼き込まれている

`.gitignore:48`（`!src/experiments/results/evaluation.html`）が明示的に除外解除している。
`unified_evaluation.py:282` が run ごとにこれを書き換えるため、
**シミュレーションを 1 回走らせるだけで作業ツリーが汚れる**（レビュー中に何度も再現した）。

コミット済みの中身には作者のローカル run-id 20 件と、
**研究室内 LAN の `http://10.10.0.108:8000/v1` / `:8001/v1`** が入っている。
同じ IP は `src/core/llm/vllm.py:26`（`DEFAULT_BASE_URL`）と
`src/scenario/*/agents.yaml` にも既定値として入っている。
私有アドレスなので機密ではないが、LAN 外では接続待ちで固まるため既定値として不適切。

### H-5. run カタログ全体が inline `<script>` に無エスケープで埋め込まれている

`evaluation_browser.py:50, 245`

```python
payload_json = json.dumps(catalog, ensure_ascii=False)
...
const CATALOG = {payload_json};
```

```text
const CATALOG = {"run-a": {..."model": "</script><h1>INJECTED</h1><script>alert(1)//"}}};
-> 注入した HTML が JS 文字列リテラルの外に出た
```

カタログには LLM 生成テキスト・`--set` 由来のモデル名・run-id など外部由来の文字列が入る。
JS 側の `esc()`（:265-271）は描画時の対策で、この埋め込みより後段なので効かない。
LLM が散文に `</script>` を書いた瞬間にレポートが壊れる。共有運用なら XSS。

### H-6. 明示的な CLI フラグが設定ファイルに負ける

```text
$ ea run ... --steps 3 --override-file ov.yaml   # ov.yaml: simulation.steps: 99
asked --steps 3, actually ran: 99 steps
```

明示フラグが最優先されるべき優先順位が逆転している。

### H-7. 環境変数 `SSOS_ECLSS_BACKEND` が明示的な `--backend` を部分的に上書きする

```text
SSOS_ECLSS_BACKEND=None   simulation backend='mock'  team.config.backend.kind='mock'  team sees plant_sim=False
SSOS_ECLSS_BACKEND='ros2' simulation backend='mock'  team.config.backend.kind='ros2'  team sees plant_sim=True
```

シミュレータは `mock` なのにチームは `plant_sim` だと思う、という不整合状態が作れる。
同一コマンドの結果も変わった（ops 172 → 171, score 58.467705 → 58.472805）。
環境変数で結果が変わる以上、再現性の保証が崩れる。

同種の問題として**テストスイートが環境変数に汚染される**:

```text
$ EA_RESULTS_ROOT=/tmp/ambient-root python3 -m pytest tests/tools/test_ssos_host.py -q
4 failed, 14 passed
```

（レビュー中に実際にこの汚染を踏み、チェーンの出力先が想定外の場所になった。）

### H-8. 最終イテレーションで中断したチェーンが exit 0 を返す

失敗が成功として報告される。CI やスクリプトから回す前提なら致命的。
`--iterate` の他の位置での失敗は正しく非ゼロを返すことは確認済み。

### H-9. 設計制約のチェックに、候補が触れなかった subsystem の穴がある

```text
installed ogs = 5000 (bounds max 80); candidate names only ARS
capacity_by_subsystem : {'ars': 5.0, 'ogs': 5000.0, 'wrs': 10.0}
constraint_status     : over_budget   bound_violations: []
```

`bound_violations` が空。総質量制約（244,623 kg > 4,000 kg）で偶然引っかかっているが、
**境界チェック自体は候補が名前を挙げた subsystem しか見ていない。**
部分的な提案（LLM は普通に出す）で境界外の機体が境界内と報告され得る。

### H-10. 同じ帯の定義が 2 箇所にあり、境界でズレる

```text
thresholds: co2_storage_high_kg = 2.0
co2 value=2.0    health.py=warning    evaluation._status=safe
o2  value=6.0    health.py=warning    evaluation._status=safe
```

`health.py` は境界値を warning、`evaluation.py` は safe と判定する。
**アクターが反応した事象が、採点では起きなかったことになる。**
`actor_decision` 軸はまさに「反応の適切さ」を測る軸なので、直接影響する。

### H-11. `design_state.current_best` が採用ランキングと食い違う

```text
design_state.current_best  -> B
adoption ranking           -> [('A', True), ('B', False)]
```

設計エージェントに見せる「現在の最良」が、採用側が拒否する候補を指す。
エージェントは採用され得ない設計を基準に次を考える。

### H-12. 公開データセットに開発者のローカル絶対パスが 306 箇所埋まっている

```text
docs/data/phase{1,2,3}_iteration_findings.json / _metrics.csv, docs/data/report03_emergence.json
experiments/outputs/ 同名 7 件
files: 14 | occurrences: 306

"apply_proposals_path": "/home/one-piece/hiroto/engineering_agents/src/experiments/results/..."
```

これは**公開した解析データセットの provenance 列**である。
つまり「どの設計文書を適用した run か」を辿る列が、
**元の 1 台のマシン以外では解決できない**。再現性を売りにする論文データとして成立しない。

なお `docs/data/` と `experiments/outputs/` は大半が互いのコピーで、
バイト一致の重複が 27 グループ・648 KiB ある（同一 SVG が最大 3 箇所）。
再生成時にどれかが更新漏れになれば静かに乖離する。

### H-13. 回答本文に `<think` という文字列があるだけで、応答全体が破棄される

`src/core/llm/parsing.py:55-58, 79`

```python
_UNCLOSED_THINKING_RE = re.compile(
    r"<(?:think|thinking|thought)>.*$",
    re.DOTALL | re.IGNORECASE,
)
```

閉じタグ処理の**後に無条件で**走り、`re.DOTALL` なので
最初に残った `<think>` から**末尾まで全部消す**。JSON 文字列リテラルの内側でも消す。

```text
raw      : {"decision": "propose_candidate", "rationale": "before I <think> harder, size ARS to 25", "fields": {...}}
stripped : '{"decision": "propose_candidate", "rationale": "before I '
status   : fallback | error: no balanced JSON object found
```

モデルが誤動作する必要はない。設計プロンプトは根拠を散文で書かせるので、
自分の思考について言及した瞬間に応答が消え、決定論フォールバックに落ちる。

### H-14. `max_tokens` で切られた応答が、修復パスを完全に迂回する

`src/core/llm/parsing.py:122-179`、`src/scenario/agents/ssos_tool_use_design.py:750`

```python
        if parsed.status in {"fallback", "empty_response"}:
            return None, elapsed, generation, parsed
```

完成前に切られると最上位オブジェクトが不均衡になるため、`extract_json_block` は
**入れ子の `fields` オブジェクト**を「最後の均衡ブロック」として返す。
それは JSON として妥当なので `parse_json_response` は `partial` を返す。
`_ask` は `fallback` / `empty_response` だけを使用不能とみなすので、`partial` は正常回答として扱われる。

```text
extract_json_block   -> {"plant_sim.ars.capacity_kg_day": 25.0}
status               : partial   error: missing required: decision
llm calls made       : 1
repair prompt issued : False
decision_source      : tool_use_rule_fallback:unknown_decision
```

**`max_parse_retries` が存在する理由そのものである最頻の失敗モードで、一度も発火しない。**

### H-15. アクター計画部と実行ゲートが 1 step あたりの上限で矛盾している

`src/scenario/agents/ssos_eclss_loop_team.py:110-123`（計画）vs `:256-274`（ゲート）

`interleave_labeled_actions` は不足量から `max_actions_per_step` まで同一 subsystem を繰り返すが、
`apply_outcome` は **1 step 1 subsystem 1 コマンドしか通さない**。繰り返しは構造上すべて捨てられる。
出荷既定は `max_actions_per_step: 6`（`scenario.yaml:243`）。実測（`plant_sim` 60 step）:

| `max_actions_per_step` | duplicate 却下 | `validity_quality` | `operational_command` メッセージ |
| --- | --- | --- | --- |
| **6（出荷既定）** | **89** | **0.349** | **172** |
| 1 | 0 | 0.263 | 19 |

**計画したコマンドの 65% が「無効な判断」として採点される。**
メッセージログも約 9 倍に膨らみ、これは設計エージェントと人間が読む記録そのものである。

正確に書くと、軸の合計点は `=6` の方が高い（3.372 vs 1.908 / 5.0）。
`=1` では o2 のエピソードに応答できず `latency_quality` が 1.0 → 0.5 に落ちるためで、
**「6 が悪い」ではなく「計画部とゲートの契約が食い違っており、
どちらの設定でも `actor_decision` 軸が測りたいものを測れていない」**が結論。
`scenario.yaml:239` が記述している計画部の契約を、ゲートが満たしていない。

### H-16. LLM が返した `fields` の型が違うと、シミュレーション完了後に run が落ちる

`ssos_tool_use_design.py:496, 706-708`、`design_state.py:57,60`

```python
            toolkit, trace, parsed.get("fields") or {}, decision=decision
```

`or {}` は falsy は防ぐが**型は見ない**。`"fields": ["plant_sim.ars.capacity_kg_day"]`（配列）で
`fields[key]` が `TypeError`、数値なら `sorted(fields)` が落ちる。
`_run_candidate_pipeline` / `_decision_loop` / `propose` のいずれも捕捉せず、
呼び出し側 `scenario_run.py:622` にも `try` が無い。

```text
fields=['plant_sim.ars.capacity_kg_day'] -> UNCAUGHT TypeError
```

その時点でシミュレーション・評価・物理ゲートは**すべて完了して代金を払い終えている**。
LLM の書式ミス 1 つで run 全体が生トレースバックで失われる。

### H-17. CI が `push` で走らないため、`trunk` と `main` は一度もテストされていない

`ssos-e2e.yml:3-20` のトリガは `pull_request` / `workflow_dispatch` / 週次 `schedule` のみ。
`docs.yml` は `push: branches: [main]` を持つが docs ビルドだけ。

```text
$ gh run list --branch trunk --limit 10
completed  success  Graph Update: pip in /.  Dependency Graph  trunk  ...
```

`trunk` で走った実績があるのは Dependabot のグラフ更新のみ。
PR では 993 テストが走るので feature ブランチは守られているが、
**統合ブランチ自体と、マージ後の `main` は検証されない。**
マージ解決を誤っても誰も気付かない。

### H-18. `balanced_accuracy` がどのモデルも予測していない事象を採点している

`src/tools/analysis/report.py:479-488`

```python
    truth = observed >= 1.0
...
            "balanced_accuracy": balanced_accuracy(
                list(truth[test]), list(pred[test] >= 0.5)
            ),
```

ラベルは「乗員 50 名全員生存」（`observed >= 1.0`）だが、
判定閾値は**予測された生存率**に 0.5 で当てている（「半分以上生存」）。**別の事象である。**

結果、`docs/en/design-loop-analysis.md:130-134` の公開表では
2 つの列が互いに矛盾している:

```text
model                                published BA
Liebig on margin                           0.9020
series (product)                           0.9118
Liebig on response  ← 太字の勝者            0.9020
```

太字の勝者が、隣に印刷されている列で負けている。
太字自体は held-out R²（0.936）が根拠なので誤りではないが、
**balanced accuracy の列は測るべき事象を測っていない**ので、
2 列を並べて読ませる表として成立していない。

### H-19. ロジスティック当てはめは増加関数しか表現できず、R² のゲートも無い

`src/tools/analysis/statistics.py:252-260`

```python
    lo_w, hi_w = math.log(span / 500.0), math.log(span * 2.0)
```

`width = exp(log_w)` は常に正なので、`1/(1+exp(-(x-x0)/w))` は単調増加しか取れない。
減少応答には表現可能な当てはめが存在せず、格子探索は最も悪くない平坦曲線を返し、
**`x0` はそのまま公開される**。

```text
truth : x0=0.5 width=0.05 (decreasing)
fitted: x0=0.5000 width=2.9356 r_squared=-0.1102
```

これが実データに効いている。公開された ARS の臨界プロファイルは単調でない:

```text
profile y = [0.38, 0.24, 0.76, 0.58, 0.76, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]   （降下 2 回）
published: max_slope 1.95   r_squared 0.869   rmse 0.0966
OGS（真に単調）        :   r_squared 0.987   rmse 0.0471
-> ARS の残差は OGS の 2.1 倍 = 乗員 50 名中 4.8 名分
```

`LogisticFit` の docstring は `1/(4w)` を「peak susceptibility」と呼んでいる。
遷移域で 2 回降下するプロファイルから「感受性 1.95」を報告するのは、
**データが持っていない鋭さをデータに帰属させている。**
`report.py:202-205` の `fits` は R² も単調性もチェックしていない。

### H-20. `per_step()` が正味収支を `steps - 1` で、運転収支を `steps` で割っている

`src/tools/plant_sim_sensitivity.py:80-96`

```python
        m = max(1, self.metabolism_steps)
        ops = max(1, self.steps)
...
            co2_ops_kg=self.co2_ops_kg / ops,
            co2_net_kg=self.co2_net_kg / m,
```

`run_campaign` は step 0 で代謝を飛ばす（`if step > 0`, :215）が、
サブシステム動作は全 `steps` step で発火する（:221/224/230）ので
`metabolism_steps == steps - 1`。
`steps` step 分蓄積した正味タンク変化を `steps - 1` で割っている。
列見出しは "Simulated Δ tank / step"、軸は `kg / step` で、
**割っていない 2 本の nameplate 列と y 軸を共有している。**

```text
steps  mode  | plotted net/step   correct net/steps   overstated
    2  ars   |      -0.527778          -0.263889        100.00%
   20  ars   |       0.064327           0.061111          5.26%
   50  ogs   |      -0.163265          -0.160000          2.04%
```

アプリ既定は `steps=20`（`plant_sim_sensitivity_app.py:115`）なので、
**出荷既定で全正味レートを 5.26% 過大表示**し、スライダ下端では 2 倍になる。

隣の列の副題（`:351`「Ending tank = initial + (Δ tank/step × steps)」）は
自分の描画値を再現せず、`steps=20, mode=ogs` では
**物理的に不可能な負の O₂ 在庫**（−0.286）を導く。

---

## MEDIUM

| # | 内容 | 場所 |
| --- | --- | --- |
| M-1 | 綴り間違いの `--set` が無警告で黙殺される（`--set simulation.stepz=99` → exit 0、steps は 3 のまま）。検証ツールとして危険 | `tools/cli/overrides.py:50-61` |
| M-2 | 静的解析が CI に一切ない。ruff・black・mypy・pyright すべて設定ゼロで Python 約 36,000 行 | `pyproject.toml`, `.github/workflows/` |
| M-3 | `requirements.txt` に `typer`・`rich`・`streamlit` が欠落。これで作った環境では CLI が `ModuleNotFoundError` | `requirements.txt` |
| M-4 | `mock` バックエンドで物理ゲートが `failed` と報告される（C-2 と同根）。最終判定は壊れないが、正典スモークが「物理ゲート失敗」と記録されるのは誤報 | `physics_gate.py` |
| M-5 | `--iterate` が mock では原理的に成立しないのに、5 本走らせた後で `rejected_final` / 「候補がどこにも無かった」と報告し exit 0 | `jobs/iterate.py` |
| M-6 | `audit.count: 0` が falsy 判定で既定の 3 に化ける（`int(raw.get("count") or len(...))`） | `design_ensemble.py:88` |
| M-7 | `summarise([])` だけ `median` キーを返さないため下流が `KeyError` | `tools/analysis/statistics.py:520-532` |
| M-8 | `VllmClient` が全例外を空文字列に潰し、通信断とモデルの空応答が区別できない | `core/llm/vllm.py:296-308` |
| M-9 | `core` が `environment` を import（宣言した層規則違反）。152 モジュール・933 import を AST 走査した結果、上向き import はこの 2 件のみ | `core/agents/types.py:8`, `core/scenario.py:10` |
| M-10 | `scenario` 内に 8 モジュールの循環 import。関数内 import（`design_tools.py:1169`, `scenario_run.py:750`）で回避しており、コメントも自認している | `scenario/` |
| M-11 | `measure_limits` が既定 `False` で本番呼び出し元も渡さないため、`floor_probe` は CLI から一度も動かない（機能が死んでいる） | `jobs/iterate.py:493,610` |
| M-12 | `ClaimsRegistry.sweep_text` が語句の**最初の出現**しか見ない。先頭に注記があれば以降の未注記主張を見逃す | `core/storage/claims.py` |
| M-13 | `_apply_seed_override` が呼び出し側の overrides dict を破壊的に変更し、nested dict を共有する | `jobs/executor.py` |
| M-14 | `design_penalty` が文書化された ~[0,1] を通常経路で外れる（`+5.512`, `-0.111`） | `design_constraints.py` |
| M-15 | `floor_probe._crew` が float/bool の乗員数を拒否する一方 `design_eval.occupant_count` は受ける。同じ量の扱いが 2 通り | `floor_probe.py` |
| M-16 | `_write_kept_fields` が `fields` キーを持つ全 change の payload を change_kind に関係なく上書きし、`apply_design_proposals` が例外を投げる | `design_tools.py` |
| M-17 | `scripts/run_design_chain.sh` が実行権限なし（mode 100644）。`./scripts/run_design_chain.sh` は exit 126 | `scripts/` |
| M-18 | 不正な `--set` 値がクリーンなエラーにならずトレースバック（`ValueError: invalid literal for int()`）で exit 1 | CLI |
| M-19 | `--quiet` が run 失敗時にも stdout に `.` を出す（run ディレクトリ名のように見える） | `tools/cli/output.py` |
| M-20 | `SSOS_ECLSS_BACKEND` 未設定時の `--iterate` エラーが `Got None` と表示され原因が分からない | `tools/cli/commands/iterate.py` |
| M-21 | CI が Python 3.11 のみをテストする一方 AGENTS.md は 3.12 を宣言。**開発する版はテストされず、テストする版は使われない**。matrix 無し、上限も無し | `.github/workflows/*` |
| M-22 | 5 つのテストが `tmp_path` を受け取りながら**実リポジトリ配下に書き込む**（`src/experiments/results/...`）。`.gitignore` が隠すので気付かれない。順序依存で並列実行不可 | `tests/tools/test_ssos_host.py:132,162,180,203,226` |
| M-23 | `figures.py` は 324 文・**行カバレッジ 99%** だが `tests/` からの参照が 1 件も無い。`test_analysis_report.py` が副作用で図を描くだけで何も検証していない。**空のグラフを出す退行でも 99% のまま緑**。`campaign.py`(54%)・`copy.py`・`core/storage/{artifacts,session}.py`・`evaluation_html.py` も同様。`preflight_remote_llm.py`(214 文) と `analysis/__main__.py`(93 文) は 0% | `tools/analysis/` |
| M-24 | `--no-recreate` のチェーンが**別チェーンの記憶**を設計 LLM のプロンプトに持ち込む。`update_compact_chain_memory` が既存 `chain_dir` の内容にマージするため、チェーン B の round 1 がチェーン A の停滞履歴を根拠に推論する | `chain_memory.py:669`, `iterate.py:531` |
| M-25 | 出荷既定の予算では `max_decisions` / `max_llm_calls` に到達不能。`max_candidate_runs: 1` が最初の提案で埋まり decision 2 が尋ねられない。ペルソナは「毎回検証してからまた聞く」と約束している | `agents.yaml:89,101-103` |
| M-26 | `VLLM_MAX_MODEL_LEN` の `int()` が例外ハンドラの**外**で走るため `generate()` が例外を投げる。`LLMClient.generate` は「エラー時は空文字列」と文書化されており全呼び出し元がそれに依存 | `core/llm/vllm.py:128-132` |
| M-27 | labeled モードの YAML goal payload が dataclass コンストラクタに無検査で渡る（LLM 経路は `_normalize_numeric_fields` で防御済み）。キー 1 つの綴り間違いが設定エラーではなくシミュレーション中の `TypeError` になる | `ssos_eclss_loop_team.py:938-943` |
| M-28 | `chain_memory._fit` の削除順序が docstring と逆。`known_bad_patterns` より先に `recent_points` を全消しし、`recent_field_sets`（最大ブロック）には触らない。窓退避経路（:774-783）が `best_score_before_window` に畳み込む処理も飛ばすので、停滞検出が `warming_up` に張り付き探索脱出が発火しなくなる | `chain_memory.py:622-640` |
| M-29 | `--write-spec` の出力先ディレクトリが無いと `parent.mkdir` 無しで `FileNotFoundError` トレースバック | `jobs/spec.py:51-52` |
| M-30 | `executor._read_summary` に JSON ガードが無く、しかも `execute_run` の `try` の**外**で呼ばれるため、壊れた `summary.json` が未捕捉例外としてチェーン全体を落とす。`ssos_host._read_summary:268-277` は同じケースを正しく処理しているので、両者を揃えるべき | `jobs/executor.py:69,103-107` |
| M-31 | `.cursor/plans/` にエージェントの作業メモ 15 KB がコミットされている（`skills/`・`agents/` は共有設定として妥当だが `plans/` は一時物） | `.cursor/plans/` |
| M-32 | `controllability` の gain が**隣接差分**なのに docstring と軸ラベル（`\|dS/d ln x\|`）は**中心差分**と称している。非一様 log 格子ではノイズの大きい方。公開値 1.165 に対し中心差分なら 0.672（+73%差）。`test_analysis_loop_dynamics.py:112` が隣接挙動を固定しており、**テストが矛盾を捕らえるどころか固定している** | `loop_dynamics.py:408-409,463-467` |
| M-33 | 「O2 制約を緩和した gain」列が出荷列の**コピー**。緩和対象 `plant_sim.ogs.max_o2_kg_day` を掃引値が上書きするため、OGS 軸の緩和掃引が出荷掃引と行単位で同一（公開表は `1.165 \| 1.165`）。周囲の散文は独立した測定として読ませる。**結果ではなく同語反復** | `experiments.py:296-299`, `campaign.py:77,162` |
| M-34 | `deterministic: all(s == 0.0 for s in ... if s is not None)` は**空ジェネレータで True**。シードデータが 0 件でも「決定的」を主張する。`statistics.py` の docstring は不確実性モデル全体をこの主張に載せている。公開値自体は 6 シード・2 キーで実際に裏付けられているが、3 キーのうち `mean_normalized_severity` は全行で欠落しており**黙って無視されている** | `report.py:126-134` |
| M-35 | `fig_mass_balance` がタイトルに結論をハードコード（"residuals sit at machine zero in all runs"）し、許容値超過の残差を "0x inside tolerance" と表示する。500 倍の違反でもこの表示。`fig_saturation` / `fig_crew_scaling` も同様に結論をタイトルに埋めている | `figures.py:121,135-136` |
| M-36 | 打ち切り観測のマークが**最後のイベント時刻**に描かれる（`KaplanMeierCurve` は打ち切り時刻を保持していない）。実測で 48 件中 18 件が 23.67 h まで追跡されているのに、曲線と打ち切りマークが 3.00 h で止まる（**7.9 倍早い**）。読者が観測窓を判断できない | `figures.py:406-409`, `statistics.py:360-397` |
| M-37 | `classify()` が `saturating` を `oscillating` より先に判定し、`delta` は**両端しか見ない**。振動して出発点に戻る軌跡が `saturating` になる。最終値の 1e-6 の違いで原型が反転する。出荷 3 チェーンは反転が無いので公開結論は今は正しいが、実際に探索する最初のチェーンで効く | `loop_dynamics.py:275-287` |
| M-38 | 臨界プロファイルが `where={"ogs": max_ogs}` で**生ラベル**に一致判定するため、`ars`/`ogs` ラベルが欠けると両プロファイルが空になり、`fits` が `{}` で臨界表が**無言で空白**になる（C-12 の陳腐化キャッシュがまさにこれを作る） | `report.py:92` |
| M-39 | `_num(...) or <default>` が正当な `0.0` を既定値に潰す。`survival_fraction` が 1 行欠けるだけで `ars_axis_worst_descent` が 0.24 → 1.0 に化け、**存在しない全乗員喪失の降下を捏造**する（文書が「worst single descent 0.24」として引用している統計量）。現行データでは発火しない潜在バグ | `report.py:159,361` |
| M-40 | 図生成関数がすべて検証前に figure を確保するため、例外時に `to_svg` の `plt.close` に到達せず**図がリークする**（空モデル集合で `ValueError` + リーク 1 件を実測）。`pcolormesh(shading="nearest")` はセル境界を線形中点で計算した後に `set_xscale("log")` を当てるので、対数表示でセルが点の中心に来ない（左右幅が最大 1.33 倍差）。`limiter_rates()` は `totals` を捨てて `by_reason` だけから作るため「動作しなかった」と「動作したが制限されなかった」を混同し、消費側は欠落を `0.0` に丸める | `figures.py:170-186,483`, `artifacts.py:330-336` |

---

## 検証したが問題が無かった点

再確認の重複を避けるため記録する。**この項目群は「見ていない」ではなく「見て問題なかった」。**

### 統計モジュールの**推定量そのもの**は数値的に正しい

`src/tools/analysis/statistics.py` は scipy を独立実装で置き換えているので重点的に検算したが、
全項目一致した。ここは fail-open の癖と正反対で、**欠損は NaN を返し数字を捏造しない**。

ただし**重要な限定**が付く。正しいのは推定量であって、
**その上に載るモデル選択・レポート層には実際の欠陥がある**（C-11, C-12, H-18〜H-20, M-32〜M-40）。
「統計は大丈夫」と読まないでほしい。正しいのは下の層だけである。
`fit_logistic_response` も、格子探索の実装は正しいが**増加関数しか表現できない**という
モデル側の制約があり（H-19）、呼び出し側に R² のゲートが無い。

| 検算項目 | 結果 |
| --- | --- |
| `summarise` の標準偏差 | `ddof=1`（標本 SD）で `2.13809` = 教科書値 |
| `cliffs_delta` | `-0.166667` = 総当たり計算と一致 |
| `_chi2_sf_1df` | 3.841459→0.050000、6.634897→0.010000（臨界値と 6 桁一致） |
| `kaplan_meier` | `[1.0, 0.75, 0.375]` = 手計算と一致（打ち切り処理も正しい） |
| `log_rank_test` の分散 | 超幾何分布の `d·(nₐ/n)·(n_b/n)·(n−d)/(n−1)` で正しい |
| `permutation_test` | `(hits+1)/(perm+1)` 補正あり・シード固定で再現 |
| `bootstrap_mean` | シード固定で完全再現（公開数値が再現可能） |
| 退化入力 | `n=0`→NaN、分散ゼロの `pearson`→NaN（0 を返さない） |

  ノンパラメトリック手法（Cliff's delta・並べ替え検定・Kaplan-Meier）の選択も、
0 と満員に張り付く出力分布に対して妥当。docstring が
「決定的シミュレータの反復に誤差棒を作らない」と明言しているのも正しい判断。
`central_difference` 自体も真に中心差分で非一様格子を正しく扱う（誤っているのは
それを使っていない `loop_dynamics` 側 = M-32）。

なお公開されている決定性の主張（`n_seeds: 6`, spreads 2 キーが 0.0）は
**実データで裏付けられている**。M-34 は「データが無くても True になる」という
潜在的な fail-open と、3 キーのうち 1 つが黙って無視されている点の指摘であり、
公開値が誤っているという話ではない。

### 解析側で確認して問題が無かった点

- **出荷データセットは内部整合している。** 全データセットで spec ラベル
  （`ars`, `ogs`, `multiplier`, `crew_size`, `scale`）が run 設定から復元した物理パラメータと一致。
  **C-12 は公開キャンペーンでは発火していない。**
- **モデル順位自体は頑健。** ρ\* とは違い、`Liebig on response` は 200 分割中 188 で
  held-out R² の argmax であり、公開値 0.936 は平均±sd（0.925±0.055）の内側。
  **不安定なのは ρ\* であってモデル選択の結論ではない。**
- **公開された ruggedness とベースライン被覆率は正確に再現する。** 独立再計算で
  18 descents / 110 transitions = 16.4%、worst 0.24、
  ρ_ARS = 4.5/(50·1.04) = 0.0865、ρ_OGS = 9.25/(50·0.84) = 0.2202、ρ_WRS = 6.4 すべて一致。
- **`discarded_fraction` の対応付けは正しい。** 提案数と適用数の off-by-one を疑ったが、
  `applied_proposals.json` は提案した run のディレクトリに置かれるため各反復が 5 提案 3 適用で、
  公開値 0.40 は per-iteration の絞り込み率 2/5 に正確に一致する。
- **物理残差の `max()` は安全。** `report.py:141` は絶対値を取らないが、
  `artifacts.py:228` が上流で `abs()` を適用済みなので負の残差は届かない。
- **`fig_crew_scaling` の凡例と系列は一致している。** `_num` は bool を正しく弾くので
  `physics_gate_passed: True` が 1.0 として平均されることもない。
- **`evaluation_html.py` は H-5 の影響を受けない**（`_esc` / `html.escape` で退避している）。
  無エスケープなのは `evaluation_browser.py` だけ。

### テストの質は高い

976 テスト関数を機械走査した結果:

| 種別 | 件数 |
| --- | --- |
| 常に真の assert / assert True | **0** |
| assert が無いテスト | **0** |
| 本体が `pass` だけ | **0** |
| mock の呼び出し確認だけ | **0** |
| try/except で失敗を飲み込む | **0** |
| 無条件 skip | **0** |

「弱い assert のみ」40 件はほとんどが protocol 適合や `is None` の妥当な確認。
**この規模のハッカソンコードでこの結果は例外的に良い。**

### 秘密情報・デバッグ残骸は無い

機械的に掃いて**すべてゼロ**だった。

| 検査 | 結果 |
| --- | --- |
| `sk-…` / `ghp_…` / `AKIA…` / `xox[bap]-` / `(api_key\|secret\|token\|password)\s*[:=]\s*"…"` | テストの固定文字列 1 件のみ（`test_ssos_tool_use_design.py:629`） |
| `TODO` / `FIXME` / `HACK` / `XXX` / `WIP` in `src/` | 0 |
| `breakpoint()` / `import pdb` / `pdb.set_trace()` | 0 |
| コメントアウトされたコードブロック（3 行以上連続） | 0 |
| ライブラリコード内の `print()` ロギング | 0（CLI エントリポイントに限定） |
| Windows / macOS 絶対パス（`/Users/…`, `C:\Users\…`） | docs 以外に 0 |
| `.gitignore` と追跡ファイルの矛盾 | 0（negation ルールのみ） |
| CI の暗黙成功（`continue-on-error` / `\|\| true`） | 0。`run_ssos_regression.sh:122` のパイプも `set -euo pipefail` で正しく伝播 |

### 設計エージェント経路は決定的

同一のフェイク LLM で designer + 3 auditor を 2 回走らせ、
`candidate_rankings.json` / `changes` / `audit` / `message` / `selection` が**バイト一致**。
`design_ensemble.py:341` の `pool.map` はスレッド完了順に関わらず roster 順を保つ。
設計経路に `random` / `time` / `uuid` 由来の値は無い。`SessionStore.append` はロックを持ち、
`VllmClient._session` は `threading.local`。**並列 LLM ラウンドの再現性は保たれている。**

### `docs/en/cli.md` は正確

Click/Typer のパラメータツリーを introspect して照合（help テキストの scrape ではない）。

- コマンド: 実装 `{doctor, job, results, run, scenarios}` = 文書と完全一致
- `ea run` のフラグ: 文書化された 26 個すべて実在（`--no-approve-provisional` 等の否定形も含む）
- 環境変数: 表の 9 個すべてが実際に `src/` または `scripts/` から読まれている

未文書のものが少数ある（`ea results --limit`、`--install-completion`、
`SSOS_CONTAINER_NAME` など 6 個の環境変数）が、誤りではなく欠落。

### AGENTS.md の正典スモークはそのまま動く

`AGENTS.md:49-53` のコマンドを一字も変えずに実行して両方 exit 0。
Run 1 が `design_domain: ssos_graph` / `changes: 3` を出力し、
Run 2 が `Applied from: cloud-smoke-run1` を表示し、Run 1 の 14 ファイルは無傷。
**`--run-id` を分ける注意書きも正しく、実際に必要。**

### その他

- **`--run-id` のパストラバーサル対策は正しい。** `sanitize_run_id`
  （`jobs/resolve.py:25-33`）が `..` `/` `\` を拒否。`'../escape'` は CLI でも弾かれる。
- **mock run は決定的。** 同一設定 2 回の `telemetry.jsonl` がバイト一致。
- **実 `plant_sim` の物理監査は本物。** 9 チェック全 `passed`、`skipped` ゼロ、
  残差 `carbon -1.78e-15` / `oxygen -1.78e-15` / `water -5.68e-14`。
- **設計→検証の受け渡し自体は動く。** iteration 2 が iteration 1 の設計を実際に積む
  （`01/applied_proposals.json` の `initial_co2_mass: 5.625` → `02/agents_config.yaml` の `ars_goal: 5.625`）。
- **`--set` の真偽値変換は正しい。** `false` → `False`（文字列のままにならない）。
- **`environment/` に LLM / Persona ロジックは無い。** 該当 import・文字列マーカーともゼロ。
  `integrations/one_piece` の呼び出し元も `scenario` のみで規則どおり。
- **`mkdocs build --strict` は通る。** nav 未登録 3 件等は INFO レベル。
- **失敗したイテレーションは（最終回以外は）非ゼロ終了を伝播する。**
- **`design_eval.py` の順位付け構造は健全。** 適格性を最優先し `rank_rationale` で
  決定基準を記録する設計は良い。問題は基準の中身（H-1）と配線（C-1）。
- **`occupant_count`（`design_eval.py:175-192`）の型処理は丁寧。**
  `bool` を弾き `50.0` を受け端数を `None` にする扱いは正しい。

---

## マージ前チェックリスト

**最優先（マージ後には直せない）:**

- [ ] C-10 41.7 MiB の `experiments/runs/*.tar.gz` を LFS / リリースアセット / 外部ストレージへ。**履歴に入ったら書き換えなしには除去できない**

必須:

- [ ] C-1 `thresholds.*` を適用可能 target から除外／採用パスで `invalid` を拒否／`evidence_status` を配線か削除／CLI で可視化
- [ ] C-9 監査で差し替えた fields を、再シミュレーションせずに outcome と対で記録しない
- [ ] C-2 ledger・capacity の欠損データ時 `SKIPPED` 化
- [ ] C-3 `final_status` 欠落を fail-closed に
- [ ] C-4 `integrity` 必須化と `unknown` 導入、`schema_version` 更新
- [ ] C-5 破壊的削除に確認要求／生成レポートを run ディレクトリ内に
- [ ] C-6 適用した文書を `applied_proposals.json` として保存
- [ ] C-7 TCL の 1 step ズレ修正、部分採点を捨てない集計に
- [ ] C-8 `normalize_fields` / `candidate_hash` の衝突修正
- [ ] C-11 ρ\* の定義を 1 つに統一し、分割依存量は複数分割の平均±sd で公開する（HTML と Markdown の食い違い解消）
- [ ] C-12 キャッシュ鍵に spec の内容ハッシュを含める
- [ ] H-3 `api-contracts.md` を実装に同期

強く推奨:

- [ ] H-1 配点を宣言した原則に合わせ直す（プロダクト判断・テストも変わる）と `results.md` の再導出
- [ ] H-2 `AXIS_ORDER` / `AXIS_META` をエンジンから導出し二重定義をやめる
- [ ] H-4 `evaluation.html` を追跡から外す、`DEFAULT_BASE_URL` を LAN 非依存に
- [ ] H-5 script 埋め込みのエスケープ
- [ ] H-6 / H-7 フラグ優先順位の是正、環境変数依存の除去、テストの hermetic 化
- [ ] H-8 最終イテレーション中断時の終了コード
- [ ] H-9 / H-10 / H-11 制約チェックの穴、帯定義の一元化、`current_best` の整合
- [ ] H-12 公開データの provenance 列から絶対パスを除去（相対パス化）、`docs/data` と `experiments/outputs` の重複解消
- [ ] H-13 / H-14 / H-16 LLM 応答処理: 未閉タグ除去を JSON 文字列に踏み込ませない、`partial` を修復対象に含める、`fields` の型検証
- [ ] H-15 計画部と実行ゲートの 1 step 上限契約を一致させる
- [ ] H-17 テストワークフローに `push` トリガを追加（`trunk` / `main` を守る）
- [ ] H-18 balanced accuracy の判定事象をラベルと一致させる（または列を落とす）
- [ ] H-19 ロジスティックに減少方向を許すか、R² / 単調性ゲートを入れて `max_slope` の公開を止める
- [ ] H-20 `per_step()` の除数を揃える、隣列の副題の式を実際の描画値に合わせる
- [ ] M-2 CI に lint ジョブ追加（層規則も機械的に強制できる）
- [ ] M-21 / M-22 Python 3.12 を CI matrix に追加、`EA_RESULTS_ROOT` の `monkeypatch.delenv` と `tmp_path` 未使用 5 件の修正
- [ ] M-32 / M-33 gain の差分定義を docstring に合わせる（テストも）、緩和列の同語反復を解消

回帰テストとして追加したいもの:

- [ ] 流量フィールド欠損テレメトリで ledger が `passed` を返さないこと
- [ ] `thresholds.*` を含む提案の適用が拒否されること
- [ ] `evaluation_status: invalid` の候補が `approved_final` にならないこと
- [ ] `final_status` 無しの文書が自動採用されないこと
- [ ] 参照期間をちょうど完走した run が採点されること（TCL 境界）
- [ ] 文字列値フィールドを持つ別々の提案が別の `candidate_hash` を持つこと
- [ ] `evaluation.json` の軸集合と `AXIS_ORDER` が一致すること
- [ ] `api-contracts.md` の満点値と `evaluation.py` の定数が一致すること
- [ ] 環境変数が設定された状態でも全テストが通ること（hermeticity）
- [ ] ρ\* が分割シードを変えても公開精度内で安定すること（不安定なら公開しない）
- [ ] 減少応答に対する `fit_logistic_response` の挙動（R² が負なら公開させない）
- [ ] 間引いた格子で同じ `run_id` が別 spec のキャッシュを再利用しないこと
- [ ] `summarise([])` が `median` を返すこと、シード 0 件で `deterministic` が True にならないこと
