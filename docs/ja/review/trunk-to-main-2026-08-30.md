# trunk → main コードレビュー（2026-08-30）

対象: `origin/main...origin/trunk`（247 ファイル / +125,950 行、うち src・tests・scripts が 111 ファイル / +98,114 行）

前提: `python3 -m pytest --ignore=tests/e2e` は **993 passed / 4 skipped** で通り、`mkdocs build --strict` も通る。
つまり以下の指摘は「テストが落ちている」話ではなく、**テストが見ていない場所**の話である。

このレビューで挙げた指摘はすべて実際にコードを走らせて再現を確認している。
再現スクリプトは `docs/ja/review/trunk-to-main-2026-08-30-evidence.sh`。

---

## 総評

設計思想は良い。`physics_gate.py` / `integrity_guard.py` / `design_eval.py` の docstring は、
「得点より物理」「設計エージェントに自分の物差しを触らせない」という正しい問題意識を
はっきり言語化しており、ハッカソン 2 日でここまで書けているのは率直に驚く。

問題は、**その思想が実装で徹底されていない**ことである。しかも失敗の仕方に一貫した型がある。

> **通底する構造的欠陥: すべての安全ゲートが fail-open している。**
> 「測れなかった」「記録が無い」「ステータスが書かれていない」が、
> どのゲートでも例外なく **合格 / 有効 / 承認済み** として扱われる。

同じ型の欠陥が独立に 4 箇所ある（詳細は C-1〜C-4）。
1 箇所ならバグだが、4 箇所あるのは設計上の癖なので、個別修正より先に
**「不明は不合格」を全ゲート共通の既定値にする**方針決定が必要。

`main` に入れる前に C-1〜C-5 の解消を必須としたい。H 系は同時に直せるなら直す、
最低でも Issue 化して既知の制約として文書化してから入れるべき。

---

## CRITICAL

### C-1. 物理ゲートの質量保存則が、データが無いときに「合格」を出す

`src/scenario/ssos_eclss_loop/physics_gate.py:79-80, 210-275`

```python
def _number(value: Any) -> float:
    return float(value) if _finite(value) else 0.0
```

`_carbon_ledger` / `_oxygen_ledger` / `_water_ledger` は入出力の各項を `_number()` 経由で読む。
テレメトリにその項が**存在しない**場合、欠損は「流量ゼロ」に化ける。
結果、収支が 0 − 0 = 0 になり、**残差 0.0 で `passed`** が出る。

```text
carbon_ledger   passed  residual=0.0
oxygen_ledger   passed  residual=0.0
water_ledger    passed  residual=0.0
-> 流量を一切記録していない run に対して保存則が「成立」と証明されている
```

同モジュールの docstring（`physics_gate.py:14-17`）は自ら
「`skipped` は合格ではない。測れなかった量は未測定として報告する」と宣言しており、
`_totals_monotonic`（:176-177）と `_stoichiometric_residual`（:285-288）は
正しく `SKIPPED` を返す。**3 本の ledger だけがこの規約を破っている。**

なお `_capacity_violation`（:379）も同じ `_number()` 依存で、
`goal_scale` が欠けると許容量が 0 になり**偽の違反**を作る（向きが逆の同一バグ）。

影響: 「物理ゲートを通った」という主張が、物理を検証していない run にも付く。
このリポジトリの中心的な価値主張そのものが崩れる。

修正方針: ledger は必要項が 1 つでも欠けたら `SKIPPED`（→ 全体 `incomplete`）にする。
`_number()` による欠損→0 の暗黙変換は収支計算から外す。

補足（公平のため）: 実際の `plant_sim` run では残差 `-1.78e-15` 等の正常な値が出て
9 チェックすべて `passed` になることを確認した。**実運用の plant_sim 結果は
このバグでは汚染されていない。** これは潜在バグであり、既存結果の捏造ではない。
ただし `docs/en/design-loop-analysis.md:116` の
「O2 と CO2 の ledger は厳密にゼロ」という記述は現行コードの出力（`-1.78e-15`）と
一致しないので、どの版で得た数字か確認のうえ再導出すべき。

### C-2. 設計エージェントが自分の採点基準を動かせる。ゲートは検知するが何も止めない

- `src/scenario/ssos_eclss_loop/design_proposals.py:50-63` — `ALLOWED_SET_PARAMETER_TARGETS` が
  `thresholds.co2_storage_high_kg` 等を**適用可能**として許可
- `src/scenario/ssos_eclss_loop/integrity_guard.py:44-45` — 同じ `thresholds` を
  `SCORING_BAR`（＝これを変えた run は証拠として不適格）として分類
- `src/scenario/ssos_eclss_loop/unified_evaluation.py:237-243` — よって `status: invalid` が立つ

この 3 つが同一リポジトリ内で正面から矛盾している。AGENTS.md が「正典」と呼ぶ
2-run スモークをそのまま実行すると再現する:

```text
run 1 set_parameter targets: ['agents.actor.policy.co2_storage_high_kg',
                              'thresholds.co2_storage_high_kg']
run 2 CLI exit code: 0
run 2 evaluation status : invalid
run 2 invalid_reasons   : ['scoring_bar_modified']
```

つまりルールベース設計エージェントが自発的に採点閾値の変更を提案し、
文書化された適用パスがそれを適用し、リポジトリ自身が結果を `invalid` と判定し、
**CLI は警告ひとつ出さず exit 0 で「Done」と表示する。**

`integrity_guard.py` が防ぐために書かれた事象を、検知してから捨てている。

なお `src/scenario/jobs/iterate.py:303-304` は `--iterate` チェーンでは
`set_parameter` を一律破棄しており、対策はこちらにだけ存在する。
**対策が無いのは AGENTS.md が推奨している側のパス**である。

修正方針: `apply_design_proposals` 側で `integrity_guard.classify_path()` を使い、
`SCORING_BAR` に落ちる target を拒否する（`ALLOWED_SET_PARAMETER_TARGETS` から
`thresholds.*` を外すだけでも塞がる）。加えて `status: invalid` の run は
CLI が非ゼロ終了か、少なくとも赤字の警告を出すこと。
`iterate.py` の一律破棄は `agents.actor.policy.*`（ARM 相当・正当な設計自由度）も
巻き込んで捨てているので、同じく `classify_path()` ベースに寄せるのが筋。

### C-3. 監督者ゲートが、ステータス未記入の文書を「承認済み」として通す

`src/scenario/ssos_eclss_loop/design_proposals.py:324-325`

```python
status = proposals.get("final_status")
if status is not None and status != FINAL_STATUS_APPROVED:
```

`final_status` が**無い**文書は理由ゼロ＝無条件採用になる。
そして `labeled_rule_base` 設計パスは `final_status` を書かない:

```text
rule-path document (no final_status): NO REASONS -> auto-adopted
same doc marked provisional_final  : ['final_status=provisional_final']
```

docstring が「design doc §9 の『自動採用しない』をここで強制する」と書いている
その場所が、正典スモークで使われる設計モードに対して完全に無効化されている。
`design_eval.py` の適格性判定（`mark_final_eligibility` / `select_final_candidate`）も
このパスでは一切呼ばれない。実測で乗員 49/50 を失った run が、
適格性判定なしで 5 件の提案を出力した。

修正方針: `final_status` 欠落を「未評価」として拒否する（fail-closed）。
ルールベースパスにも `mark_final_eligibility` を通し `final_status` を必ず書く。

### C-4. `evidence_status()` は監査が走っていない run を「valid」と答える

`src/scenario/ssos_eclss_loop/integrity_guard.py:130-132`、
`src/scenario/ssos_eclss_loop/unified_evaluation.py:269`

```python
return "invalid" if integrity.get("scoring_bar_modified") else "valid"
...
integrity = integrity or {}
```

`evidence_status({})` → `valid`。呼び出し側が `integrity` を渡し忘れると、
`unified_evaluation.py:269` が空 dict で埋め、`scoring_bar_modified: False` が
**検査した事実なしに** summary に刻まれる。

実害の確認: コミット済み `src/experiments/results/evaluation.html` に埋まっている
公開済み run（`e001`〜`e003` 系 18 件、`status: scored`）は
`integrity` キー自体が存在しない。にもかかわらず `schema_version` は新旧どちらも `"2.0"` のままで、
消費側は「監査して問題なし」と「監査していない」を区別できない。

修正方針: `integrity` は必須引数にする（`None` なら例外）。
`evidence_status` は情報が無ければ `unknown` を返し、`unknown` を合格として扱わない。
スキーマ変更に合わせて `schema_version` を上げる。

### C-5. `--output-dir` が任意ディレクトリを無確認で再帰削除する

`src/scenario/jobs/resolve.py:98-101`、`src/core/event_log.py:52-55`

```python
run_dir = Path(output_dir)
if recreate_output and run_dir.exists():
    shutil.rmtree(run_dir)
```

`--output-dir` はユーザ入力をそのまま受ける公開フラグで、
`sanitize_run_id()` による保護（`--run-id` 側にはある）を通らない。

```text
before: 2 user files
after : thesis.txt present? NO-DELETED
after : nested/data.csv present? NO-DELETED
```

`ea run ... --output-dir ~/Documents` で `~/Documents` の中身が消える。
確認プロンプトも dry-run も、「run ディレクトリらしさ」の検査もない。

`--run-id` 側も `EventLog.prepare_run_dir` が無条件 `rmtree` なので、
同じ run-id での再実行は前回成果物を黙って破棄する。
AGENTS.md がわざわざ「Run 1 の出力が消えるので run-id を分けよ」と
注意書きしている事実自体が、この UX が誤っている証拠である。

修正方針: 既存ディレクトリが空でなく run 生成物（`summary.json` 等）を含まない場合は
削除を拒否する。上書きには明示的な `--force` を要求する。

---

## HIGH

### H-1. 採点表が、乗員の生存より「軽くて安い」を 2 倍重く評価している

`src/scenario/ssos_eclss_loop/evaluation.py:29-36`

```python
CREW_MAX = 20.0      # 乗員生存
COST_MAX = 20.0      # コスト
MASS_MAX = 20.0      # 質量
```

生存 20 点に対し、コスト＋質量で 40 点。実測（`plant_sim`, 30 steps, 既定設定）:

```text
乗員 49/50 を喪失した run が 59.17 / 100 を獲得
  actor_survival                0.4 / 20.0
  cost                         20.0 / 20.0
  mass                         20.0 / 20.0
```

死者 49 名の設計が、軽くて安いだけで 40 点を満額回収している。

さらに実効的な影響は大きい。`design_eval.py:219-240` の `candidate_rank_key` では
適格候補の中の順位付けを**得点のみ**で行う。適格候補は定義上全員生存なので
`actor_survival` は全候補 20/20 で**順位に一切寄与しない**。
結果、実際に順位を決める 80 点のうち **40 点（＝半分）が「小さく安いこと」**になる。

`design_eval.py:1-7` の docstring は
「どれだけ質量を節約しても人命は買えない」と宣言しており、
`_footprint_axis`（`evaluation.py:892-909`）の docstring 自身も
「既定の満点ラインは間違っていた。それは全乗員を失うベースライン機体だった」と認めている。
`full_at` 導入はレンジを詰めただけで、**ベースライン機体が 40/40 を取る事実は変わっていない**。

`docs/en/results.md:32-42` が記録している「round 25 で WRS 単独提案 → 次 run が
ベースラインに戻り 0/50」「最終 round は 34/50・55.41 で round 24 より悪化」という退行は、
この配点で説明がつく。**ループの探索が軽量・低コスト隅に引っ張られている。**

修正方針: 配点を宣言済みの原則に合わせる（生存の重みを footprint 合計より大きくする、
または footprint を得点軸から外して適格性判定内の制約に戻す）。
どちらを選ぶにしても、`docs/en/results.md` の結論は再導出が必要。

### H-2. 評価ブラウザが 100 点中 40 点を画面から落としている

`src/scenario/ssos_eclss_loop/evaluation_browser.py:9-16, 247-254`

```text
engine axes : [..., 'cost', 'mass', ...]     ← 8 軸
browser axes: [...]                          ← 6 軸
hidden      : ['cost', 'mass'] = 40.0 points
```

`AXIS_ORDER` に `cost` / `mass` が無く、`scorebar()` は
`AXIS_ORDER.filter(...)` で描画するため両軸が消える。
`compareTable()` も同じ順序を使うので、**質量とコストだけが違う 2 run は
比較画面上で完全に同一に見える。**

加えて `AXIS_META`（:248-253）の満点値がエンジンと食い違う:

| 軸 | AXIS_META | エンジン |
| --- | --- | --- |
| `actor_survival` | 50 | 20 |
| `actor_decision` | 10 | 5 |
| `physical_response` | 10 | 5 |

`fmt(axis.max_score ?? meta.points)`（:303）は `max_score` 欠落時に
`meta.points` へ落ちるため、`0.4 / 50` という**誤った分母**が表示され得る。

配点を変更した際に表示側を更新し忘れた典型。テストが JSON しか見ておらず、
HTML の軸リストと突き合わせていないため検出されていない。

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
「physics gate 失敗は `status: invalid`」という記述も実装と異なる
（`unified_evaluation.py:239` は `backend == "plant_sim"` のときだけ `invalid`）。

`docs/ja/eclss-evaluation-implementation.plan.md:31` も 50 点表記のまま。
**「API 契約」を名乗る文書が契約として機能していない。** 監査可能性を売りにする
プロジェクトとして、これは体裁の問題ではなく本質的な欠陥。

### H-4. 生成物 `evaluation.html` が git 追跡下にあり、run するたびリポジトリが汚れる

`.gitignore:48`（`!src/experiments/results/evaluation.html`）、
`src/scenario/ssos_eclss_loop/unified_evaluation.py:282`

```python
write_evaluation_browser(run_path.parent, default_run_id=run_path.name)
```

run ディレクトリの**親**（＝ `src/experiments/results/`）に書き込むため、
シミュレーションを 1 回走らせるだけで追跡ファイルが書き換わる。
`.gitignore` が明示的に除外解除しているので意図的だが、意図が誤っている。

コミット済みの中身には作者のローカル run-id 20 件と、
**研究室内 LAN のエンドポイント `http://10.10.0.108:8000/v1` / `:8001/v1`** が焼き込まれている。

同じ IP は `src/core/llm/vllm.py:26`（`DEFAULT_BASE_URL`）と
`src/scenario/*/agents.yaml` にも既定値として入っている。私有アドレスなので
機密ではないが、LAN 外では接続待ちで固まるため既定値としては不適切。

修正方針: `evaluation.html` を追跡対象から外す（`.gitignore:48` の除外解除を削除）。
必要なら `docs/` 配下に生成タスクとして再配置する。
`DEFAULT_BASE_URL` は `localhost` などに変え、LAN 固有値は環境変数 / YAML 側へ。

### H-5. run カタログ全体が inline `<script>` に無エスケープで埋め込まれている

`src/scenario/ssos_eclss_loop/evaluation_browser.py:50, 245`

```python
payload_json = json.dumps(catalog, ensure_ascii=False)
...
const CATALOG = {payload_json};
```

文字列値に `</script>` が含まれると script ブロックが早期終了する。実測:

```text
const CATALOG = {"run-a": {..."model": "</script><h1>INJECTED</h1><script>alert(1)//"}}};
-> 注入した HTML が JS 文字列リテラルの外に出た
```

カタログには LLM 生成テキスト、`--set` 由来のモデル名、run-id など
外部由来の文字列が入る。JS 側の `esc()`（:265-271）は描画時の対策で、
この埋め込みより後段なので効かない。

影響は主にレポート破損（LLM が `</script>` を含む散文を書いた瞬間にページが壊れる）だが、
生成 HTML を共有する運用なら XSS でもある。

修正方針: 埋め込み前に `<`, `>`, `&`, U+2028/2029 を `\uXXXX` へ退避する。

---

## MEDIUM

### M-1. 綴り間違いの `--set` が無警告で黙殺される

`src/tools/cli/overrides.py:50-61` の `_assign_dotted_key` は
どんなパスでも無条件に新規作成し、スキーマ照合をしない。

```text
$ ea run ... --set simulation.stepz=99
CLI exit code: 0
steps actually simulated: 3   （99 は警告なく捨てられた）
```

検証ループのツールとしては危険度が高い。操作者は値を変えたつもりで、
run は旧値のまま進み、得られた証拠が誤った設定に紐付けられる。

修正方針: 既知の設定パスと照合し、未知パスは既定でエラー
（意図的な新規キーには `--set-new` 等の明示手段を用意）。

なお `_coerce_value`（:64-80）は `"false"` を真の `False` に変換しており、
よくある「文字列 "false" が truthy になる」罠は踏んでいない。ここは正しい。

### M-2. 静的解析が CI に一切ない

`pyproject.toml` / `requirements.txt` / `.github/workflows/` に
ruff・flake8・black・isort・mypy・pyright の設定・実行が**ゼロ**。
Python 約 36,000 行に対して型チェックもリンタも無い状態で `main` に入る。

`.github/workflows/docs.yml` は `mkdocs build --strict`、
`ssos-e2e.yml` は pytest を回しているので、CI の骨格自体はある。
lint ジョブを 1 つ足すコストは小さい。

### M-3. `requirements.txt` が壊れている

`pyproject.toml` の依存に対し `typer` / `rich` / `streamlit` の 3 つが欠落。
`pip install -r requirements.txt` で入れた環境では
`python3 -m tools.cli` が `ModuleNotFoundError` になる。

README / docs は `pip install -e ".[dev]"` を案内しており
`requirements.txt` を参照していないので実害は限定的だが、
機能しないファイルが残っているのは誤解の元。削除か同期のどちらかにすべき。

### M-4. `mock` バックエンドで物理ゲートが「failed」と報告される

`mock` run の `summary.json` は `physics_gate_status: failed` /
`physics_gate_passed: false` を記録する。原因は `plant_sim` 前提の
`readings_present_and_finite` と `carbon_ledger` が、フィールド不在を
`SKIPPED` ではなく `FAILED` として扱うため（C-1 と同根）。

`_admissibility`（`unified_evaluation.py:239`）は `plant_sim` 以外では
これを不適格理由にしないので最終判定は壊れない。しかし
**AGENTS.md が正典スモークとして指定している構成が
「物理ゲート失敗」と記録される**のは、ダッシュボード読者に対して誤報である。

修正方針: バックエンドが該当量を持たない場合は `SKIPPED` → 全体 `incomplete`。

### M-5. `--iterate` が mock では原理的に成立せず、それが実行後にしか分からない

`--iterate 3` を mock で実行すると 5 本のシミュレーションを回した末に:

```text
verdict: INCONCLUSIVE
status: rejected_final
reason: no candidate was simulated anywhere in the chain
```

5 本走らせた後で「どこにも候補が無かった」と言う。exit code は 0。
mock では候補評価機構が働かないなら、実行前に弾くか警告すべき。

### M-6. `summarise()` が空入力で戻り値のキー集合を変える

`src/tools/analysis/statistics.py:520-532`

```text
non-empty keys: ['max', 'mean', 'median', 'min', 'n', 'sd']
empty keys    : ['max', 'mean', 'min', 'n', 'sd']
summarise([])["median"] -> KeyError 'median'
```

空入力の分岐だけ `median` を返さない。`src/tools/analysis/report.py:263-271` は
戻り値をそのまま集計 dict に格納するため、データが 1 件も無い条件の集計で
下流が `KeyError` になる。空でも `median: nan` を返せば済む。

### M-7. `VllmClient` が全例外を空文字列に潰す

`src/core/llm/vllm.py:296-308` の `except Exception` は
ネットワーク障害・認証エラー・タイムアウトを区別せず
`LLMGeneration(text="")` を返す。ログには出るが呼び出し側は
「モデルが空を返した」と「サーバに繋がらなかった」を判別できない。
LLM 設計モードの結果解釈に直接影響する。

---

## 検証したが問題が無かった点

再確認の重複を避けるため記録しておく。

- **`--run-id` のパストラバーサル対策は正しい。** `sanitize_run_id`
  （`src/scenario/jobs/resolve.py:25-33`）が `..` `/` `\` を拒否する。
  `'../../etc'` `'a/b'` `'..'` すべて `ValueError`。
- **mock run は決定的。** 同一設定 2 回の `telemetry.jsonl` がバイト一致。
- **実 `plant_sim` の物理監査は本物。** 9 チェック全て `passed`、`skipped` ゼロ、
  残差 `carbon -1.78e-15` / `oxygen -1.78e-15` / `water -5.68e-14`。
  C-1 は潜在バグであり、既存 plant_sim 結果を無効化するものではない。
- **`--set` の真偽値変換は正しい。** `false` → `False`（文字列のままにならない）。
- **`mkdocs build --strict` は通る。** nav 未登録ページ 3 件等は INFO レベル。
- **`design_eval.py` の順位付けロジック自体は健全。** 適格性を最優先し、
  `rank_rationale` でどの基準が決めたかを記録する設計は良い。
  問題は基準の中身（H-1）であって構造ではない。
- **`occupant_count`（`design_eval.py:175-192`）の型処理は丁寧。**
  `bool` を弾き、`50.0` を受け、端数を `None` にする扱いは正しい。
- **統計モジュール `src/tools/analysis/statistics.py` は数値的に正しい。**
  scipy を独立実装で置き換えている箇所なので重点的に検算したが、全項目一致した。
  ここは fail-open の癖と正反対で、**欠損は NaN を返し数字を捏造しない**。

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

---

## マージ前チェックリスト

必須（`main` を汚さないための最低線）:

- [ ] C-1 ledger の欠損データ時 `SKIPPED` 化
- [ ] C-2 `thresholds.*` を適用可能 target から除外＋`invalid` run の CLI 可視化
- [ ] C-3 `final_status` 欠落を fail-closed に
- [ ] C-4 `integrity` を必須化、`unknown` を導入
- [ ] C-5 `--output-dir` / `prepare_run_dir` の破壊的削除に確認を要求
- [ ] H-3 `api-contracts.md` を実装に同期（数値・schema_version・軸一覧）

強く推奨:

- [ ] H-1 配点の再検討（宣言した原則と一致させる）と `results.md` の結論再導出
- [ ] H-2 `AXIS_ORDER` / `AXIS_META` をエンジンから導出し、二重定義をやめる
- [ ] H-4 `evaluation.html` を追跡から外す、`DEFAULT_BASE_URL` を LAN 非依存に
- [ ] H-5 script 埋め込みのエスケープ
- [ ] M-2 CI に lint ジョブ追加

回帰テストとして追加したいもの:

- [ ] 流量フィールド欠損テレメトリで ledger が `passed` を返さないこと
- [ ] `thresholds.*` を含む提案の適用が拒否されること
- [ ] `final_status` 無しの文書が自動採用されないこと
- [ ] `evaluation.json` の軸集合と `AXIS_ORDER` が一致すること
- [ ] `api-contracts.md` の満点値と `evaluation.py` の定数が一致すること
