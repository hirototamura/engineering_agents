# trunk → main コードレビュー（2026-08-30）

対象: `origin/main...origin/trunk`（247 ファイル / +125,950 行、うち src・tests・scripts が 111 ファイル / +98,114 行）

前提: `python3 -m pytest --ignore=tests/e2e` は **993 passed / 4 skipped**、`mkdocs build --strict` も通る。
つまり以下は「テストが落ちている」話ではなく、**テストが見ていない場所**の話である。

指摘はすべて実際にコードを走らせて再現を確認した。未再現の推測は載せていない。
主要な再現スクリプトは `trunk-to-main-2026-08-30-evidence.sh`（同ディレクトリ）。

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

`main` に入れる前に C 系の解消を必須としたい。

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

---

## 検証したが問題が無かった点

再確認の重複を避けるため記録する。**この項目群は「見ていない」ではなく「見て問題なかった」。**

### 統計モジュールは数値的に正しい

`src/tools/analysis/statistics.py` は scipy を独立実装で置き換えているので重点的に検算したが、
全項目一致した。ここは fail-open の癖と正反対で、**欠損は NaN を返し数字を捏造しない**。

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

必須:

- [ ] C-1 `thresholds.*` を適用可能 target から除外／採用パスで `invalid` を拒否／`evidence_status` を配線か削除／CLI で可視化
- [ ] C-2 ledger・capacity の欠損データ時 `SKIPPED` 化
- [ ] C-3 `final_status` 欠落を fail-closed に
- [ ] C-4 `integrity` 必須化と `unknown` 導入、`schema_version` 更新
- [ ] C-5 破壊的削除に確認要求／生成レポートを run ディレクトリ内に
- [ ] C-6 適用した文書を `applied_proposals.json` として保存
- [ ] C-7 TCL の 1 step ズレ修正、部分採点を捨てない集計に
- [ ] C-8 `normalize_fields` / `candidate_hash` の衝突修正
- [ ] H-3 `api-contracts.md` を実装に同期

強く推奨:

- [ ] H-1 配点を宣言した原則に合わせ直す（プロダクト判断・テストも変わる）と `results.md` の再導出
- [ ] H-2 `AXIS_ORDER` / `AXIS_META` をエンジンから導出し二重定義をやめる
- [ ] H-4 `evaluation.html` を追跡から外す、`DEFAULT_BASE_URL` を LAN 非依存に
- [ ] H-5 script 埋め込みのエスケープ
- [ ] H-6 / H-7 フラグ優先順位の是正、環境変数依存の除去、テストの hermetic 化
- [ ] H-8 最終イテレーション中断時の終了コード
- [ ] H-9 / H-10 / H-11 制約チェックの穴、帯定義の一元化、`current_best` の整合
- [ ] M-2 CI に lint ジョブ追加

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
