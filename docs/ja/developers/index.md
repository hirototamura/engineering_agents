# Engineering Agents の開発

Engineering Agents は、分野をまたいでシステムを設計・検証するエンジニアリングチームを開発します。開発者は実行基盤、エージェントの作業手順、シミュレータ、ツール、証拠の検査を変更し、チームの判断をレビュー可能にします。同梱の [3 つのシナリオ](scenarios/index.md)は対等な個別のエンジニアリング事例です。

[開発環境](setup.md)を用意し、[アーキテクチャ](architecture.md)と[実行ライフサイクル](runtime.md)を確認してください。具体的な変更は次のガイドから進めます。

- [同梱シナリオを追加する](guides/add-scenario.md)。
- [シミュレータのバックエンドを変更する](guides/change-backend.md)。
- [エージェントのツールを追加する](guides/add-tool.md)。
- [評価を変更する](guides/change-evaluation.md)。

[エージェント](agents.md)、[ツールと記憶](tools-memory.md)、[記録と外部連携](records-integrations.md)では責務の境界を説明します。[実行契約](reference/execution.md)と[保存契約](reference/storage.md)は現行の内部動作の参照先です。コマンド、設定項目、成果物の読み方は[利用者向けリファレンス](../users/reference/cli.md)にあります。

ミッションを守り、設計要件や検証要件の変更は監督へ提案します。設計の創造性と、証拠に対する決定論的な検査を分離してください。シミュレーション結果が示すのはそのモデルの検証範囲であり、実機の妥当性確認ではありません。

現行実装は同梱の設定ディレクトリを検出し、固定レジストリとシナリオ別の分岐で実行します。任意の外部シナリオの読み込みは[開発目標](development/external-scenarios.md)であり、提供済みの機能ではありません。レビューと確認の進め方は[貢献手順](contributing.md)を参照してください。
