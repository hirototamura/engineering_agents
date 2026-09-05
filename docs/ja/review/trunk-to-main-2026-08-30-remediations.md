# trunk→main レビュー指摘への対応（2026-08-30）

実装側の対応記録。レビュー本文は [trunk-to-main-2026-08-30.md](./trunk-to-main-2026-08-30.md)。

## 直したこと

| ID | 対応 |
| --- | --- |
| C-1 | 採点バー `set_parameter`（`thresholds.*` など）は提案に出さない。iterate も scoring-bar だけ落とす。無効な評価は記録し、自動採用しない（シミュレーション自体は完走する）。 |
| C-2 | 物理ゲートは欠測項を 0 埋めせず `skipped`。欠測があれば全体は `incomplete`。 |
| C-3 | `final_status` 欠落は未評価として拒否。ルールパス文書も stamp する。 |
| C-4 | integrity 未計測は `evidence_status=unknown`。未計測フラグは `null`。 |
| C-5 | run ディレクトリ以外の木は `--force` なしで消さない。評価ブラウザは run 内 `evaluation_browser.html`。 |
| C-6 | `--apply-proposals` は消す前に読み、run 内 `consumed_proposals.json` に写す（iterate の `applied_proposals.json` 手渡しとは別ファイル）。 |
| C-7 | TCL の観測終端は `last_sample + step_seconds`。部分採点は有限軸の和と `applicable_max`。 |
| C-8 | 容量の非数は落とさず拒否。ハッシュは元キー集合を含む。 |
| C-9 | 監査は順位行の `fields` を上書きしない。`audited_fields` を別記録。 |
| C-11 | 公開 ρ* は全グリッドの criticality fit。R² &lt; 0 の fit は出さない。 |
| C-12 | 実験キャッシュ鍵は `experiment_spec.json` の fingerprint。 |
| H-2 / H-3 / H-5 | ブラウザに cost/mass。契約書を schema 2.1 に合わせる。カタログ JSON をエスケープ。 |
| H-6 / H-7 | CLI は named flag が最後。team は pin した `backend.kind`。 |
| H-8 | 完走でも非情報の `stopped_reason` は非ゼロ。 |
| H-9 / H-10 / H-11 | 全 subsystem を境界チェック。帯境界を health と一致。`current_best` は採用ランキング前に eligibility。 |
| H-13 / H-14 / H-16 | 未閉じ `<think` で唯一の JSON を消さない。`partial` も修復。`fields` の型エラーを捕捉。 |
| H-17 / H-18 / H-19 / H-20 | `trunk`/`main` の push で CI。生存は `>= 1.0`。符号付き幅の logistic。正味は `steps` で割る。 |
| M-1 / M-3 / M-6 / M-7 / M-13 / M-17 / M-18 / M-21 / M-26 | 未知 `--set` 拒否。ランタイム依存を requirements へ。`audit.count: 0` を尊重。空 `summarise` に median。seed は deepcopy。chain スクリプトを実行可能に。非整数 `steps` は ValueError。CI を 3.11+3.12。vLLM max len をガード。 |
| M-30 | 欠落 / 壊れた / 空 / 非オブジェクトの `summary.json` は捕捉して `exit_code=1`。ファイルは上書きせず、iterate はそこで止まる。空 dict を成功にはしない。 |

## 意図して触っていないもの

| ID | 理由 |
| --- | --- |
| C-10 | 41.7 MiB バイナリは履歴に残る。history rewrite はしない。 |
| H-1 | CREW/COST/MASS の重みはプロダクト判断。schema 2.1 のまま。 |
| H-4 | LAN IP デフォルトの変更は保留。 |
| H-12 | 公開データセット内のローカル絶対パスは保留。 |
| H-15 | actor 計画と実行ゲートの 1 step 上限はアーキテクチャ案件。 |

## 運用上の注意

- ライブラリの `apply_design_proposals` は `approve_provisional=False`。`ea run` は YAML どおりデフォルトで通す。
- ルールパスの mock run は乗員数が無いことが多く `provisional_final` になる。閉ループは `--approve-provisional`（CLI デフォルト）が必要。
- 既存の **run ディレクトリ** の再作成に `--force` は不要。run に見えない木だけ拒否する。
