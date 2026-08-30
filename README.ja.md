# Engineering Agents — 生命維持システムの、閉じた設計ループ

[English README](README.md) · [ドキュメント](docs/ja/index.md) · [実験記録](docs/ja/results.md) · [エージェント設計](docs/ja/agent-design.md) · [実装仕様書](docs/ja/specs/index.md)

50人のエージェントが宇宙居住区にいる。空気・酸素・水のプラントは、**その50人を生かすには小さすぎる**。それでも彼らは生のテレメトリだけを見て、1 step ずつ運用する。ランが終わると——たいてい死者を出して終わる——設計エージェントがその残骸を読み、もっと大きなプラントの寸法を決め、再シミュレーションで検証し、その設計を次のランへ**実際のハードウェアとして**渡す。

そしてまた起きる。50回。

最後の一文が要点である。**設計ループは閉じている。**エージェントが提案したものが、次の世代のエージェントが生きる世界になる。だから悪い設計は低いスコアではない。30周あとの、まだ誰も始めていないランで出る50人の死である。

```
テレメトリ → 50人が判断 → プラントが進む → 乗員が生きるか死ぬか
    ↓
ラン成果物 → 設計エージェント → 候補 → 再シミュレーション → 物理監査 → 採点
    ↓
提案が次のランのハードウェアになる  ──────────────────────────────┐
    ↑                                                          │
    └──────────────────────────────────────────────────────────┘
```

---

## この世界設定の理由

宇宙の皮をかぶった汎用マルチエージェント砂場ではない。物理も数値も破綻の仕方も、実在の生命維持工学から取っている。

- **プラントはスコアではなく質量収支である。** 乗員代謝は NASA **BVAD** の値（1人1日あたり CO₂ 1.04 kg / O₂ 0.84 kg / 水 2.28 kg）。酸素生成は量論に従って水を 1.126 kg/kg 消費する。Sabatier は捕集済み CO₂ を消費する。何も湧かない。[`plant_sim/model.py`](src/environment/ssos/eclss/plant_sim/model.py)
- **backend は実物のロボットスタックにできる。** `--backend ros2` は Docker 上の実 [Space Station OS](https://github.com/space-station-os/space_station_os) を ROS 2 の action / service / topic で駆動する。同じエージェント、同じコード経路、違うプラント。
- **設計には金と質量がかかる。** すべての候補がアフィン・ラック模型で価格付けされる。打上費 55 kUSD/kg は、NASA OIG の CRS 監査が報告する 63.2–71.8 kUSD/kg と同じ桁の探索用の値である。全員を生かすが 52 トンある設計は失敗であり、システムはそう言う。
- **乗員は死ぬ。** 減点項ではなく、名簿からエージェントが消える状態変化である。[`survival.py`](src/scenario/ssos_eclss_loop/survival.py)

シナリオは実在の工学的な問い——**50人の乗員に生命維持はどれだけ要り、いくらかかるのか**——であり、実在の、検証可能な答えを持つ。

---

## 創発を可能にしている設計

世界は小数点まで規定してある。エージェントには、それをどう扱うかをほとんど何も言わない。

**オペレーターが1ターンに受け取るもの**（[`build_llm_situation`](src/scenario/agents/ssos_eclss_loop_team.py#L1001)）:

```
step=17, co2_storage_kg=2.41, o2_storage_kg=5.88, product_water_reserve_l=61.2,
grey_water_collected_l=3.4, urine_buffer_l=6.1, captured_co2_kg=0.88,
ars_failure_enabled=False, ogs_failure_enabled=False, wrs_failure_enabled=False
```

に加えて状態語が4つ。プロンプト本文の中で**「施設監視層による記述的な所見であって、命令ではない」**と明記されている。

**渡していないもの:**

| 渡さないもの | 何が重要か |
| --- | --- |
| 閾値の数値 | `co2_storage_high_kg: 2.0` は健康状態の語とルールベース actor を動かす。LLM は `2.41` と `warning` という語だけを見て自分で決める |
| 行動しろという指示 | 契約の最後の一文「あなたとチームがこの step は待つと合意したなら commands は空にせよ」。**待つことが正規の選択肢** |
| 推奨コマンド | levers ブロックは各コマンドが**何であるか**と各フィールドが**何を意味するか**を書く。どれを、どれだけ、とは書かない |
| 投入量 | `air_revitalisation` を選ぶとは `initial_co2_mass` を自分で決めるということ。その数値が機械をスケールする |
| この step に同僚が言ったこと | 50体は前 step の討議に対して**同時に**考える。合意は step をまたいで作るしかない |

憲章は1段落で、その効力を持つ一文がこれである（[`persona.py:15`](src/core/agents/persona.py#L15)）:

> 主張は Telemetry（数値）と World state（記述的な健康状態）に基づけ。**安全上の規範的判断は ECLSS エンジニアであるあなたのものだ——隠された施設側の閾値を仮定するな。**

ペルソナは**考え方**（第一原理・システム・リスク）であり、シナリオ名も閾値も行動カタログも意図的に含まない。だから同じ顔ぶれが、見たことのないシナリオにそのまま移る。

その一方で、世界は誰が何を信じていようと強制する。1 step 1サブシステム1コマンド、稼働中の機械は 4800 秒仕事を受けない、50人は1日 52 kg の CO₂ を出す。

→ 詳細: **[エージェント設計 — 世界が決めることと、モデルが決めること](docs/ja/agent-design.md)**

---

## 設計エージェントと、それに**許していない**こと

設計側は別の場所に線を引いている。理由は実測された失敗である。モデルが「次にどのツールを呼ぶか」も選んでいたとき、あるランは同じ制約チェックに21ターンを使い、15分で候補を1本しか作らなかった。

```
LLM     = 設計判断だけ
Python  = 調査・検証・シミュレーション・評価・比較・ワークフロー管理
```

毎ターン、組み立て直された1ページを渡され、ちょうど2つのうち1つを返す。

```json
{"decision": "propose_candidate", "rationale": "...", "fields": {"plant_sim.ars.capacity_kg_day": 20.8}}
{"decision": "finish",            "rationale": "...", "selected_candidate_id": "candidate_003"}
```

ツールは選ばない。合否も判定しない。決めるのは**設計そのもの**——連続値の変数3つを、工学的範囲内のどこでも。勾配も最適化器も無い。

それ以外はすべて、全候補に対して固定順でコードが回す。**9つの決定論ツールがあり、LLM を呼ぶものは1つも無い**（[`design_tools.py`](src/scenario/ssos_eclss_loop/design_tools.py)）。設計を決める計算はすべてそこで行われるので、小さいモデルが数値を幻覚することはできない。

ループが閉じているぶん、3種類の嘘が実際に金額になる。だからそれぞれに関門がある。

| 関門 | 問うこと | ファイル |
| --- | --- | --- |
| **Evidence Gate** | この候補は本当に再シミュレーションされたか。採用フィールドは**そのランの記録**から来ているか | [`ssos_tool_use_design.py`](src/scenario/agents/ssos_tool_use_design.py) |
| **Physics Gate** | **テレメトリだけ**を読んで、在庫は非負か、累計は単調か、炭素・酸素・水の台帳は釣り合うか。9項目 | [`physics_gate.py`](src/scenario/ssos_eclss_loop/physics_gate.py) |
| **Integrity Guard** | このランは自分の採点基準・運転点・故障スケジュールを動かしたか | [`integrity_guard.py`](src/scenario/ssos_eclss_loop/integrity_guard.py) |

物理監査に落ちたランは**低く採点されるのではなく、採点されない**。integrity guard は、そのランが受け取る資格の無いスコアを拒否する。

---

## 記憶 — 3層、3つの別々の理由

| 層 | 何 | 大きさ | 理由 |
| --- | --- | --- | --- |
| **私的** | エージェントごと、ラン内。**モデル自身が書く**任意の `"memory"` フィールドを含む | 30件 | ログの垂れ流しではない。何を残す価値があるかはエージェントが決める |
| **討議** | 共有、ラン内 | 22件 | **50体の1 step にも満たない。**直近の同僚は引用できるが部屋全体は読めない。情報は伝播しなければならない |
| **連鎖** | ラン間: `compact_chain_memory.json` | **4096 バイト厳守** | 唯一の読み手が有限コンテキストのモデル。履歴ではなくメモであり、周回数と共に増えない |

連鎖の記憶は、実測された1つの事故のために存在する。

```
24周: ARS=20.8, OGS=42.0, WRS=1.8  → 50/50 生存, スコア 66.18
25周: WRS だけの部分提案            → 次のランはベースラインを設置 → 0/50
```

うまくいった設計は棄却されたのではない。**忘れられた。**各周は自分のランから状態を組み立て直す——それが周を監査可能にしている当のものであり、連鎖に記憶が無かった理由でもある。連鎖の記憶が持つのは4つだけ。全員生存した最良設計、前周に**実際に設置された**寸法、**各サブシステムがどこで乗員を生かせなくなるかを実測した値**、この連鎖が既に踏んだ失敗を最大5件。4 KB を超えたときは文章を切らず、最も価値の低い項目を丸ごと落とす。

この限界値は計算ではなく**実測**である。この区別を学ぶのに1本の走行を要した。以前はサブシステムごとに計算した下限を提示して「これを下回るな」と伝えていた。結果、その下限が答えになった——2つのガス系が計算下限に触れた周から、20周のあいだどちらも動かなくなった。この2つで質量の91%を占める。しかも3つのうち1つは値そのものが間違っていた。現在は `floor_probe.py` が、出荷時の機体を全員が戻ってくるまで大きくし、そこから各サブシステムを1つずつ乗員が失われるまで下げる。34回のシミュレーション、16秒、モデルへの問い合わせはゼロ。設計者が見るのは各区間の両端だけである。

```text
CO2除去    20.79 全員生存   20.45 で12名喪失
酸素生成   42.04 全員生存   41.35 で 2名喪失
水再生      1.98 全員生存    1.95 で 4名喪失
```

閾値も下限も指示も無い。20.45 で12名が死んだと見せられた者に、20.8 が限界だと教える必要は無い。

探索指示も載る。同じ生存段位で4周連続して 0.25 点の改善が無ければ、次の周は「同じところを回っている」と言葉で伝えられる。

→ [記憶設計の詳細](docs/ja/agent-design.md#4-記憶)

---

## 実際に何が起きたか

50周の連鎖を4本、同じ世界・同じ乗員で。その間に変更は3つ。以下の数値はすべて [`docs/data/`](docs/data) にコミットした周回ごとの指標から読んでいる。

| | 段階① 初期 | 段階② ＋連鎖の記憶 | 段階③ ＋採点表の基準変更 | 段階④ ＋監査パネル |
| --- | ---: | ---: | ---: | ---: |
| **最終生存者** | **34/50** | **50/50** | **50/50** | **50/50** |
| 0/50 の周 | 12 | 1 | 1 | 1 |
| 3項目そろった提案 | 38/50 | 50/50 | 50/50 | 50/50 |
| ユニーク設計数 | 39 | 11 | 17 | 9 |
| 最高 / 平均スコア | 66.18 / 61.71 | 66.36 / 65.94 | 84.23 / 83.34 | 84.03 / 82.59 |

*段階③④のスコアは①②と比較できない（採点関数そのものを変えたため）。④は③と同じ採点表。4本で比較できるのは生存者数・巻き戻り・提案の完全性・ユニーク設計数。*

![4段階の生存者数とスコア](docs/images/results/ssos_phase1_phase2_phase3_survival_score_trend.svg)

走らせた時間に見合う発見が4つ。

1. **段階①は探索の失敗ではなく、状態継承の失敗だった。**39のユニーク設計を探索しており、これは後の2段階より多い。24周目には全員生存の答えに到達している。ただ掴んでいられず、26周あとにより悪い状態で終わった。
2. **4 KB のメモ1枚が直した。**致命的な巻き戻りが12回から1回へ。以降の提案はすべて3サブシステムを名指ししている。代償として、探索が狭まりユニーク設計数が 39 から 11 に落ちた。
3. **採点表が測っていたものが間違っていた。**費用と質量の満点ラインが**出荷時ベースライン**にあり、それは全員が死ぬ設計である。生存可能な設計は必然的にそれより大きいので、すべて「高価」と印を付けられた。まったく違う2つの生存可能設計が 40点満点中 11.6 と 4.1 になり、採点表が両者を区別できなくなっていた。観測された最小の生存可能設計を基準に置き直して分解能が戻った。
4. **監査パネルは危険な下げを止め、探索も止めた。**段階④は17周目から `20.8 / 42.0 / 1.65` に固定され、段階③の WRS=1.25（45/50）にも 84.23 を取った 1.8–2.2 帯にも行っていない。ユニーク設計は 17 から 9 へ。

そして、まだ駄目なところも同じ場所に書く。段階②から④で総質量・総費用は**ほとんど改善していない**——点数が動いたのは採点が動いたからである。探索は1軸に留まり、そのあと凍った。モデル1つ・シード1つ・連鎖4本であり、統計的な研究ではない。

このうち2つはその後に原因が分かって修正された（`0aaec84`）。それが4つ目の発見であり、最も居心地が悪い。連鎖にはサブシステムごとに**計算した**下限が渡され、「これを下回るな」と伝えられていた。だからそこで止まった——2つのガス系が下限に触れた周から、20周のあいだどちらも動かない。この2つで質量の91%である。しかも3つのうち1つは値そのものが間違っていた。**下限はいま実測する**——全員が戻るまで機体を大きくし、各サブシステムを1つずつ乗員が失われるまで下げ、設計者には両端だけを見せて閾値は出さない。そして巻き戻り自体も配管のバグだった。提案が「そのランが飛ばしていた機体」ではなくシナリオファイルにマージされていたので、1つを名指しすると残り2つが戻っていた。**禁じるものが無くなったいま探索が広がるかどうかは未計測である。**それは次の連鎖であって、主張ではない。

→ **[実験記録の全文](docs/ja/results.md)**

### 上の主張はすべて再導出できる

一連の流れがリポジトリに入っており、最後の工程は `diff` である。

| | 場所 | 容量 |
| --- | --- | --- |
| **連鎖を走らせる** | [`scripts/run_design_chain.sh`](scripts/run_design_chain.sh) · [`.ps1`](scripts/windows/run_design_chain.ps1) | |
| **生ログ** — 4本とも丸ごと | [`experiments/runs/*.tar.gz`](experiments/runs) | 43 MB（展開後は各115 MB） |
| **解析スクリプト** — 標準ライブラリのみ。numpy 不要 | [`experiments/analysis/`](experiments/analysis) | 6本 |
| **解析後データ** — 1段階につき 50行 × 54列 | [`docs/data/`](docs/data) | |
| **図** | [`docs/images/results/`](docs/images/results) | |

```bash
cd experiments
for f in runs/*.tar.gz; do tar -xzf "$f" -C runs/; done
python3 analysis/analyze_ssos_iter.py --root runs/phase3-rescored --prefix phase3
diff outputs/phase3_iteration_metrics.csv ../docs/data/phase3_iteration_metrics.csv   # 差分なし
```

生ログは何も要約していない。`tool_trace.jsonl` には9つのツールの実際の引数と返り値が、`design_decision_state.json` にはモデルの応答が原文のまま、`candidate_runs/` にはモデルが名指しした全候補の再シミュレーションが入っている。**ある設計を、その根拠になったテレメトリから、それを提案した一文まで遡れる。** → [`experiments/README.md`](experiments/README.md)

---

## クイックスタート

**必要なもの:** Python 3.11+ と Git。Docker は `--backend ros2` のときだけ。Ollama / vLLM は `--agents-mode llm` のときだけ。

```bash
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -e ".[dev]"
ea doctor
```

<details>
<summary>Windows PowerShell</summary>

```powershell
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m tools.cli doctor
```

SSOS 実機ランには [Docker Desktop](https://www.docker.com/products/docker-desktop/) を **WSL 2** バックエンドで入れ、`scripts/*.sh` は Git Bash から実行する。詳細: [docs/ja/overview.md](docs/ja/overview.md)
</details>

**まず動かす（Docker も LLM も不要）:**

```bash
ea run ssos_eclss_loop --backend plant_sim --agents-mode labeled_rule_base --steps 40
ea results
```

**設計ループを回す（LLM が要る。Ollama で足りる）:**

```bash
ea run ssos_eclss_loop --iterate 10 --llm-provider ollama --llm-model qwen3:8b
```

**見る:**

```bash
python3 -m streamlit run src/tools/dashboard/app.py
```

| コマンド | 用途 |
| --- | --- |
| `ea run [SCENARIO]` | 1ラン、または `--iterate N` で連鎖 |
| `ea scenarios` | シナリオ一覧 |
| `ea results [RUN_ID]` | 最近のラン、または1つの `summary.json` |
| `ea doctor` | Python・依存・Docker/SSOS・Ollama・vLLM の確認 |

`ea` が `PATH` に無ければ `python3 -m tools.cli` を使う。

### シナリオ

| シナリオ | 何を模擬するか |
| --- | --- |
| `ssos_eclss_loop` | 50体が SSOS ECLSS（ARS/OGS/WRS）を運用し、そのあと設計エージェントが次の機体を寸法決めする |
| `scrubber_degradation` | Python モックプラント上の CO₂ スクラバ異常 |

### 結果の置き場所

```
src/experiments/results/<run_id>/
├── telemetry.jsonl                 step ごとのプラント指標
├── messages.jsonl                  全発話・推論・取得した思考
├── design_decision_state.json      モデルに見せたページと、その答え
├── design_proposals.json           次の周へ渡した寸法
├── evaluation.json                 採点表（軸ごと、points_lost 付き）
└── summary.json                    ランのメタデータ
```

連鎖では `<chain>/NN/` が周ごとに増え、`compact_chain_memory.json` と `chain_summary.json` が加わる。

---

## アーキテクチャ

```
tools/cli          ea run / scenarios / results / doctor      Typer
   │
scenario/          シナリオごとの step ループ、agents.yaml、scenario.yaml
   │               ssos_eclss_loop: 設計ツール、関門、評価、連鎖の記憶
   │
core/              Scenario ABC · Team · persona/memory · LLMClient ABC · JSON パース
   │
environment/       EclssBackend Protocol  ──  mock │ plant_sim │ ros2（実 SSOS）
```

継ぎ目はすべて差し替えであって、書き直しではない。

| 変更 | 費用 |
| --- | --- |
| 別のプラント | メソッド9個の `Protocol` を満たすクラス1つ ＋ `if` 分岐1つ。3実装が同梱（算術モック / 質量収支 sim / 実 ROS 2） |
| 新しいシナリオ | `scenario.yaml` を持つディレクトリ1つ。登録制ではなくファイルシステムから発見される |
| エージェント挙動の変更 | YAML の `mode: none │ labeled_rule_base │ llm`。オペレーター側と設計側は独立 |
| 世界ルールの変更 | `scenario.yaml`、またはコマンドラインで `--set plant_sim.crew.size=120` |
| 新しい設計変数 | `CapacityVariable` を1件 ＋ 寸法係数。ループ・ツール・関門・評価は変更不要（モデルへの契約はキー一覧から生成される） |

→ [拡張ガイド](docs/ja/extending.md) · [アーキテクチャ](docs/ja/architecture.md) · [API 契約](docs/ja/api-contracts.md)

---

## 技術メモ

**LLM の組み込み。** Ollama と vLLM を1つの `LLMClient` ABC の裏に。プロバイダ・モデル・温度・トークン予算は**側ごと**の設定で、出荷構成では50体のオペレーターに 9B、1体の設計者に 27B を別ポートで使う。

自ホストのサーバはネイティブ function calling を当てにできないので、プロトコルは素の JSON 契約である。[`core/llm/parsing.py`](src/core/llm/parsing.py) は具体的な90分の空振りが理由で存在する。**360 agent step すべてがパーサのフォールバック**だったのに「挙動変化」として読まれていた。だからパースは status を返す（`ok` / `partial` / `fallback` / `empty_response`）。`fallback` は明示的に**エージェントの判断として扱うなという意味**である。`extract_json_block` は**最後の**均衡した JSON を取る（思考してから答えるモデルは答えを末尾に置く）。`strip_thinking_tags` は `<think>` / `<thinking>` / `<thought>` と、`max_tokens` 打ち切りで閉じていないブロックを処理する。

プロバイダ側の reasoning（vLLM の `reasoning_content`、Ollama の `thinking`）は think タグ本文と統合して保存する。誰も辿り直せない設計は、レビューできる設計ではない。

**失敗時の扱い。** 読めない応答 → 同じ予算内で修復1回 → 検証済み候補をすべて保持する決定論フォールバック。**枠切れは正常な終わり方**であって異常ではない。

**並行実行と再現性。** 50体は128ワーカーのプールで1バッチとして討議する。セマフォはループ非依存の `threading.BoundedSemaphore`（`asyncio.Semaphore` は次 step の `asyncio.run` で壊れる）。step は同期で、全エージェントが同じスナップショットを見てから、プラントが1回進む。シミュレータに乱数は無い——同じ設定・同じコマンドなら軌跡は小数点まで同じであり、それが「候補の**予測**」と「次周の**実測**」を突き合わせられる理由である。

**テスト。** 849 passed / 4 skipped。

```bash
pytest tests --ignore=tests/e2e
```

煙テストではなく、敵対ケースを試す。`test_ssos_physics_gate.py`（244行）は監査に細工したテレメトリを食わせる（`test_broken_mass_balance_fails`, `test_negative_inventory_fails`, `test_stoichiometry_violation_fails`, `test_failed_subsystem_that_processed_work_fails`, `test_processing_beyond_installed_capacity_fails`）。`test_chain_final_answer.py`（313行）は連鎖が何を答えてよいかを固定する（`test_a_design_that_loses_occupants_is_never_the_answer`, `test_an_unaudited_design_is_never_the_answer`, `test_a_threshold_that_moves_partway_through_stops_the_ranking`, `test_nothing_found_is_reported_as_nothing_found`）。`test_ssos_chain_memory.py`（651行）は 4 KB 予算・削除順・停滞検知を覆う。

---

## ロードマップ

各項目は、3本の連鎖が**実測で**足りないと示したものである。

- **P0** — 連鎖の記憶機構に回帰テストを付ける。致命的な巻き戻り12回のうち11回を消したのに、壊れてもテストは1つも落ちない。
- **P1** — 主張された下限が消えたので4本目の連鎖を走らせ、探索が本当に水再生の外へ広がるかを確かめる。未計測であり、いちばん面白い問い。
- **P1** — 新スコア・旧スコアの再計算・総 M$・総 kg・生存者数を並べて出す。「採点が変わった」が二度と「設計が良くなった」と読めないように。
- **P2** — 探索中の安全下限（34周目は5人の命を使った）／判断ページから体積と `over_budget` を落とす／候補 ID と適用周を並べて表示する。

さらに先: 1人の設計者ではなくレビュー委員会。LLM 乗員の下の LLM 設計者。EPS の電力予算の下での ECLSS 設計（ROS 2 ブリッジは既にある）。能力以外の設計変数。そして居住区の外へ——機構は ECLSS 固有ではないが、ただで移植できないのは物理モデルであり、それが無ければ全体はただのチャットログになる。

→ [ロードマップ全文](docs/ja/roadmap.md)

---

## どう作ってきたか

非自明な変更はすべて、先に仕様書を書き、それに対して実装し、その仕様書自身の受け入れ条件で検証してきた。仕様書は**原文のまま**、後に置き換えられた部分も含めて保存してある。ループは3回作り直されており、それが無いと今の形は読めないからである。

| 仕様書 | 決めたこと | 状態 |
| --- | --- | --- |
| [Tool Use 中心の設計エージェント再設計案](docs/ja/specs/2026-08-28-tool-use-design-agent-redesign.md) | 自分で証拠を集め、再シミュレーションで検証する | §10 は下で置換 |
| [Design Decision Loop 改良仕様](docs/ja/specs/2026-08-29-design-decision-loop.md) | LLM から**手順**を取り上げる。各関門 | 実装済み |
| [Chain Memory 最小実装仕様](docs/ja/specs/2026-08-30-chain-memory.md) | 周をまたぐ 4 KB のメモ1枚 | 実装済み |
| [Scoring / 停滞探索 実装仕様](docs/ja/specs/2026-08-30-scoring-and-stagnation-exploration.md) | 費用・質量の基準を移す。堂々巡りを検知する | 実装済み |

→ [仕様書索引（仕様の節 → ソースファイル対応つき）](docs/ja/specs/index.md)

---

## ドキュメント

| | 日本語 | English |
| --- | --- | --- |
| クイックスタート | [docs/ja/index.md](docs/ja/index.md) | [docs/en/index.md](docs/en/index.md) |
| 概要 | [docs/ja/overview.md](docs/ja/overview.md) | [docs/en/overview.md](docs/en/overview.md) |
| **エージェント設計** | [agent-design.md](docs/ja/agent-design.md) | [agent-design.md](docs/en/agent-design.md) |
| **実験記録** | [results.md](docs/ja/results.md) | [results.md](docs/en/results.md) |
| **拡張ガイド** | [extending.md](docs/ja/extending.md) | [extending.md](docs/en/extending.md) |
| **ロードマップ** | [roadmap.md](docs/ja/roadmap.md) | [roadmap.md](docs/en/roadmap.md) |
| **実装仕様書** | [specs/index.md](docs/ja/specs/index.md) | [specs/index.md](docs/en/specs/index.md) |
| アーキテクチャ | [architecture.md](docs/ja/architecture.md) | [architecture.md](docs/en/architecture.md) |
| API 契約 | [api-contracts.md](docs/ja/api-contracts.md) | [api-contracts.md](docs/en/api-contracts.md) |
| CLI ガイド | [cli.md](docs/ja/cli.md) | [cli.md](docs/en/cli.md) |
| 設計エージェント（詳細） | [tool_use_design_agent.md](docs/ja/memo/ssos_eclss_loop/tool_use_design_agent.md) | [tool_use_design_agent.md](docs/en/memo/ssos_eclss_loop/tool_use_design_agent.md) |
| SSOS 接合 | [ssos/index.md](docs/ja/ssos/index.md) | [ssos/index.md](docs/en/ssos/index.md) |
| エージェントガイド | [AGENTS.md](docs/ja/AGENTS.md) | [AGENTS.md](docs/en/AGENTS.md) |

```bash
pip install -e ".[dev]" && mkdocs serve   # → http://127.0.0.1:8000/ja/
```

---

## ライセンス

[Apache License 2.0](LICENSE.txt) — Copyright 2026 One Piece Engineering
