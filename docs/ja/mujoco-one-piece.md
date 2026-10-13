# MuJoCo・One-Piece設計反復

One-Pieceが版付きの要求・KDP・詳細パラメータ・証拠・判断を管理し、Engineering Agentsが設計変更を提案してシミュレーションする。ECLSSは既存の独立シナリオとして維持する。

## 小さな変更範囲

ハードウェアは既存の6変数（一辺、印刷質量基準、ホイール質量、外径比、内外径比、厚さ）と登録済みモータ選択。ソフトウェアはLQRの姿勢・角速度・運動量のQ重み3群とyawゲインだけを変更する。各Q群は基準の0.25〜4倍、yawは0〜0.12。R、センサー、周期、物理刻み、駆動制約、評価器は変更対象に含めない。

小campaignごとに制御器を固定し、全経路で保存したKを使う。機械と制御を同時に変える場合は旧／新機械と旧／新制御の4組を同条件で比較する。新しいCPU/GPU照合は固定刻みで行い、半刻み確認を行わない。過去の半刻み確認は出典付き履歴として残す。

CPUとMJXは、正本の停止条件 `contact_loss_stop_s`、`slip_stop_speed_m_s`、`slip_stop_duration_s`、`pivot_drift_stop_mm` を共通に参照する。legacy source manifestは元コードの出典を示し、ENは評価器の修正を含む現在の実装ハッシュを記録する。修正によって過去の結果を書き換えない。

## ENPIREに対応する流れ

1. **EN — 環境**：One-Pieceから特定版のモデル・要求・試験条件を取得し、リセット、制約、判定器、実行コードの構成を固定する。各試行で初期状態を復元する。
2. **PI — 改善案**：関連する要求・KDPと過去の結果を読み、反証可能な仮説と許可範囲内の最小設定差分を作る。
3. **R — 実行**：MuJoCo CPUで実行し、GPU指定時はMJXでも同条件を実行する。合否は数値チェッカーが決める。
4. **E — 進化**：失敗指標と採否理由を読み、仮説、優先KDP、探索幅からなる設計探索ポリシーを新しい版にする。次のPIはその版と記録済み結果を読み直す。

このMVPは論文の実機・任意コード改善・学習済み重み更新を実装したものではない。ENPIREの環境固定と証拠による改善構造を、限定された設計設定の探索へ適用する。設計探索ポリシーの変更が評価条件の変更にならないようにする。

要求、評価条件、採用baselineの確定は人間が行う。自動のkeep/rejectは開発試験内の判断である。GPU未実行は未実行と記録し、CPUだけでGPU確認済みとしない。過去に公開された確認結果を次の設計へ渡す場合は開発試験の学習情報とする。

## 記録と再開

各実行は構成digest、親候補、仮説、設定差分、制御器、条件・seed、テレメトリ、失敗、採否、探索ポリシー版を記録する。One-Pieceが一時的に使えない場合はoutboxに保持し、再送しても同じ記録を重複生成しない。次の反復では送信済みの記録を再取得する。

既定上限は5反復、新規候補20件、30分、改善なし3反復。実行は予算境界で停止し、終了理由を残す。評価対象の子実行からさらに設計者を呼び出さない。

## オフライン受入

既存2,048候補・前回46候補の31通過／9失敗／6保留を取り込み、保存済みKによるCPU再現とFake LLMの2反復を確認する。Fake LLMでも実際のCPU物理シミュレーションへ提案を再投入する。実LLMの改善能力、新しいGPU経路の実機動作、物理忠実度は別の確認事項である。

## 実行

両リポジトリを隣にcloneし、One-Pieceの[証拠パック](https://github.com/hirototamura/one-piece/tree/main/projects/balancing-cube)を復元する。共有契約はJSON Schema 1.0、Pythonパッケージ0.1.1に固定している。One-PieceはまだPyPI公開を前提にしないため、ローカルのcheckoutをインストールする。

```sh
python -m pip install -e ../one-piece -e '.[mujoco]'
ea run balancing_cube --backend mujoco_cpu --design-mode none \
  --set ssot.path=../one-piece/projects/balancing-cube/store
python scripts/verify_cube_loop.py \
  --store ../one-piece/projects/balancing-cube/store --output results/cube-offline-check
```

`none`は比較基準をCPUで探索・確認する。Fake LLMの受入スクリプトは実際のCPUで2反復し、One-Pieceへの保存と再取得を検査する。既定のsnapshot `cube.simulation.snapshot@fixed-dt-mvp-2` は `D-000544-52890` の版を比較基準として指定する。LQR設計時の線形化モデルと保存済みKは元の構成を維持する。比較基準の指定は採用baselineの確定ではない。

実LLMの反復は `--design-mode llm --iterate 2 --llm-provider ollama` を使う。GPUは任意の `.[gpu]` とCUDA環境を別途用意し、`--backend mjx_gpu` を指定する。今回、新しい実LLM・GPU実行は確認していない。outbox再送は `MechanicalBridge(store_path).outbox(run_dir).flush()` で行える。送信が未完了なら次のPIへ進まない。

時間予算はHTTPタイムアウトとケース境界で検査する。実行中のnative solver/JIT呼出しは強制終了せず、次の境界で不完全な証拠を保持して止める。

参考：[ENPIRE論文](https://arxiv.org/html/2606.19980v2)、[公式autoresearch境界](https://github.com/NVlabs/ENPIRE/blob/main/enpire/policy/autoresearch_instruction.md)、[One-Pieceシステムモデル](https://github.com/hirototamura/one-piece/blob/main/docs/ja/SYSTEM_MODEL.md)。

## レビュー対応

`fixed-dt-mvp-2` はv1の担当先と数値試験のトレースを訂正した版。物理モデル、保存済みK、評価条件、D-000544-52890の比較基準は同じ。比較基準の本体とcampaign_summary（前回46件の31/9/6を含む）は件数制限の外で必ず渡す。既存の受入履歴は保存し、今後の受入試験は一時ストアで実施する。

`suggested_search_step` は探索の助言であり、親との差の上限ではない。compilerは機械・制御の絶対範囲を強制する。比較基準の実行失敗時にはPIを始めず、要求したGPUが未実行ならinconclusiveと非ゼロ終了を返す。2×2途中の集計失敗でも部分証拠を残し、bestを元に戻す。

CIはMuJoCoとReleaseのSHA-256固定One-Piece 0.1.1 wheelを導入し、Python 3.11/3.12でCube試験のスキップ0件を必須とする。実GPU実行は別の未実施項目である。
