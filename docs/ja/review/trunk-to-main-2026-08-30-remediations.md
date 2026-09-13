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
| M-4 / M-16 | C-2 で mock 物理ゲートは欠測を `skipped`/`incomplete` に。`_write_kept_fields` は `capacity_profile` だけ書く。 |
| M-8 | 通信例外は空文字のまま返す（呼び出し側契約は維持）。`LLMGeneration.error` に理由を残し、空応答と区別する。 |
| M-12 | `sweep_text` は全出現を見る。先頭の注記だけで後段の未注記主張を逃さない。 |
| M-15 | `floor_probe._crew` は `occupant_count` と同じ（`50.0` は通す、bool は拒否）。 |
| M-19 | `--quiet` は失敗時に run パス（`.` 含む）を出さない。 |
| M-20 | `--iterate` は env の backend を spec に写す。未設定は `Got None` ではなく `--backend` / `SSOS_ECLSS_BACKEND` を案内。 |
| M-22 | `test_ssos_host` は `tmp_path` に書く。実リポジトリの results を汚さない。 |
| M-24 | `--no-recreate` でも今の 1..N チェーン開始時に他人の `compact_chain_memory.json` は捨てる。 |
| M-27 | labeled の goal payload は未知キーを `TypeError` にせず `operational_rejected`。 |
| M-29 | `--write-spec` は親ディレクトリを作る。 |
| M-30 | 欠落 / 壊れた / 空 / 非オブジェクトの `summary.json` は捕捉して `exit_code=1`。ファイルは上書きせず、iterate はそこで止まる。空 dict を成功にはしない。 |
| M-34 | シード測定が 0 件なら `deterministic` は False。空ジェネレータの True にはしない。 |
| M-35 | 図タイトルは測定内容。超過残差を "inside tolerance" / "machine zero" と書かない。 |
| M-38 | 臨界プロファイルは数値ラベルで一致。空なら `empty_profiles` を記録。 |
| M-39 | `_num(...) or default` をやめ、正当な `0.0` を潰さない。欠測の survival は降下に使わない。 |
| M-40 | 空モデル集合では figure を作らず `ValueError`。例外時は `plt.close`。 |

## 残っていた穴（この PR）

| 穴 | 対応 |
| --- | --- |
| 二重物理ゲート | `_physics_gate` を削除。`evaluate_run` は `evaluate_physics(telemetry)` だけ。`finalize_run_evaluation` は上書きしない。分析残差は `carbon_ledger` / `oxygen_ledger` / `water_ledger` の `residual`。 |
| 三つの連鎖答え | `collect_chain_candidates` は飛んだ機体（`summary.json` + `scenario_config.yaml`）だけ。`chain_verdict` は選ばれた乗員数と最初の周回。`best_full_survival` は探索メモのまま。 |
| 監査ハイブリッド | veto は `rejected_final`。新しい field set は出さない。`iterate_apply_document` は `rejected_final` を `approve_provisional` でも載せない。 |
| `approve_provisional` 既定 | YAML と `resolve_iteration` の既定を `false`。閉ループ smoke は `--approve-provisional`。 |
| 残骸 | 死んだ `write_evaluation` / `catalog_text` を削除。`_traced_tool_call` は `getattr`。乗員数は `occupant_count`。 |

## 意図して触っていないもの

| ID | 理由 |
| --- | --- |
| C-10 | 41.7 MiB バイナリは履歴に残る。history rewrite はしない。 |
| H-1 | CREW/COST/MASS の重みはプロダクト判断。schema 2.1 のまま。 |
| H-4 | LAN IP デフォルトの変更は保留。 |
| H-12 | 公開データセット内のローカル絶対パスは保留。 |
| H-15 | actor 計画と実行ゲートの 1 step 上限はアーキテクチャ案件。 |
| M-2 | ruff/mypy を CI に足すと既存 36,000 行で赤になる。設定追加は別作業。 |
| M-5 | mock iterate の exit を変えるとチェーンの成功判定が変わる。計画表示の注記だけにした。 |
| M-9 / M-10 | 層・循環 import の切り直しはアーキテクチャ案件。 |
| M-11 | `measure_limits` を既定で足すと iterate が追加シミュレーションを走る。 |
| M-14 | `design_penalty` のクランプは順位を変える。 |
| M-23 / M-25 | 図の包括テストと出荷予算の変更は別作業。 |
| M-28 | `_fit` の削除順は探索脱出を動かす。挙動が変わる。 |
| M-31 | `.cursor/plans/` は docs から参照されている。削除はリンク切れになる。 |
| M-32 / M-33 / M-36 / M-37 | 公開数値・分類・KM 曲線を変える。 |

## 運用上の注意

- ライブラリの `apply_design_proposals` は `approve_provisional=False`。`ea run` も YAML 既定 `false`。通すなら `--approve-provisional`。
- ルールパスの mock run は乗員数が無いことが多く `provisional_final` になる。閉ループの `--apply-proposals` は `--approve-provisional` が必要。
- 既存の **run ディレクトリ** の再作成に `--force` は不要。run に見えない木だけ拒否する。
