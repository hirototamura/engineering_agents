# Engineering Agents を使う

Engineering Agents は、設計を提案し、シミュレーションでシステムを観測し、得られた証拠を評価するエンジニアリングチームを実行します。特定の分野に限定した仕組みではありません。同梱の各シナリオが、対象世界、許可する操作、要求、証拠の契約を定めます。

まず[ローカルクイックスタート](quickstart.md)で流れを確認し、目的に合う[シナリオ](scenarios/index.md)を選びます。チュートリアルで使う単位や検証規則は、他のシナリオへそのまま適用できません。

## 計画・実行・確認

- [実行を設定する](guides/configure-run.md): 条件を選び、入力と出力先を残す。
- [LLM を接続する](guides/llm.md): 既存のモデルサービスと利用するエージェントを選ぶ。
- [設計を反復する](guides/design-iterations.md): 提案を適用し、再シミュレーションを比較する。
- [結果を確認する](guides/inspect-results.md): 実行の完了と工学的な証拠を区別する。
- [レポートを開く](guides/reports.md)、または[問題を調べる](guides/troubleshooting.md)。

監督・設計・運用・検証の役割は[基本概念](concepts.md)で説明します。反復可能な実行には [CLI](reference/cli.md)、[設定](reference/configuration.md)、[成果物](reference/artifacts.md)のリファレンスを参照してください。

ここでは実装済みの機能を使う手順を扱います。シミュレータやツールの変更、シナリオの開発は[開発者向け文書](../developers/index.md)に進んでください。外部パッケージからのシナリオ読み込みは[開発目標](../developers/development/external-scenarios.md)であり、現在の CLI 機能ではありません。

## 必要な判断から始める

| 確認したいこと | 入口 | 残す証拠 |
| --- | --- | --- |
| ローカルで設計を引き渡せるか | [クイックスタート](quickstart.md) | 別々の初回・適用後実行と消費した提案 |
| 工学上の問いにどのシステムを使うか | [シナリオ選択](scenarios/index.md) | 選んだシナリオの範囲と前提 |
| 2 回の実行で何が変わったか | [結果の確認](guides/inspect-results.md) | 実効入力、観測、評価バージョン |
| 提案を受け入れられるか | [基本概念](concepts.md)と各シナリオの結果 | 制約、検証証拠、承認理由 |
| 既存の実験レポートを読みたい | [レポートライブラリ](guides/reports.md) | 派生表示と対応する元の証拠 |
