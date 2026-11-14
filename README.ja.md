# Engineering Agents

ドメインによらずシステムを設計・検証する技術者集団をソフトウェアで育てます。知見・記憶・ツール・評価と証拠を積み上げ、次の技術的判断に反映します。

[English](README.md) · [ドキュメント](docs/ja/index.md)

## 設計・検証を行う

[ユーザーガイド](docs/ja/users/index.md)：既存機能を設定し、実行し、結果を判断する技術者向け。

- [クイックスタート](docs/ja/users/quickstart.md)
- [実行条件の設定](docs/ja/users/guides/configure-run.md)
- [結果と証拠の確認](docs/ja/users/guides/inspect-results.md)
- [CLI リファレンス](docs/ja/users/reference/cli.md)

## 実装を追加・変更する

[開発者ガイド](docs/ja/developers/index.md)：リポジトリとシナリオを変更する人向け。

- [開発環境](docs/ja/developers/setup.md)
- [アーキテクチャ](docs/ja/developers/architecture.md)
- [拡張と検査](docs/ja/developers/guides/add-scenario.md)
- [外部シナリオ化に向けた開発](docs/ja/developers/development/external-scenarios.md)

## 組込みシナリオ

- [scrubber_degradation](docs/ja/users/scenarios/scrubber_degradation/index.md): スクラバー劣化と電力支援
- [ssos_eclss_loop](docs/ja/users/scenarios/ssos_eclss_loop/index.md): 生命維持系の運用と処理能力設計
- [balancing_cube](docs/ja/users/scenarios/balancing_cube/index.md): キューブの機械・制御設計

シナリオは同格のインスタンスです。現在は組込み登録が必要で、外部シナリオの読込みは今後の開発課題です。ダッシュボードは成果物を人間が確認する手段です。

Python 3.11+。追加依存・LLM・SSOT・Docker の要否は各シナリオを参照してください。コーディングエージェントは [AGENTS.md](AGENTS.md)、文書編集時は [docs/AGENTS.md](docs/AGENTS.md) を読みます。

[Apache License 2.0](LICENSE.txt) — Copyright 2026 One Piece Engineering
