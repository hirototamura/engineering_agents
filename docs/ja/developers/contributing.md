# レビュー可能な変更を行う

具体的な不具合や不足機能、担当する境界、修正後に観測できる動作を明確にします。1 つの事例を基盤全体とみなさず、[アーキテクチャ](architecture.md)と対象の[シナリオ](scenarios/index.md)から着手してください。

## 作業を定義する

機能、設計、連携の提案には、リポジトリの[第一原理の Issue テンプレート](https://github.com/hirototamura/engineering_agents/blob/main/.github/ISSUE_TEMPLATE/first_principles.md)を使います。現状の課題、解決する理由、範囲、受入条件を含む期待結果を記述します。このテンプレートは作業の必要性を問います。`first_principles` のペルソナ・アーキタイプはシミュレーション中の思考方法を指定する別の仕組みです。

要件の出典と改訂権限を示します。設計変数、実行中の方針、評価器、証拠表示の変更を区別してください。ミッション、物理的制約、独立した決定論的検証を守ります。外部シナリオ化は[範囲を定めた開発作業](development/external-scenarios.md)を使い、未実装のプラグイン API を作り上げて説明しません。

## 実装と確認

リポジトリの [AGENTS ガイド](https://github.com/hirototamura/engineering_agents/blob/main/AGENTS.md)と[文書規則](https://github.com/hirototamura/engineering_agents/blob/main/docs/AGENTS.md)を読みます。担当レイヤーで変更し、両言語の文書を更新し、テストの成果物は一時ディレクトリへ保存してください。記録済みの実験ディレクトリをテストに流用しません。

開発中は対象のテストを実行し、仕上げに次を実行します。

```bash
python -m pytest --ignore=tests/e2e
python -m mkdocs build --strict
```

プロバイダのテストは制御した応答で通信・解析の失敗も確認します。バックエンド変更は単位、状態遷移、証拠を確認します。実 ROS2、GPU、実機の検証には対応環境と範囲の明示が必要です。関連する追加テストのスキップも確認してください。ビューアが開くことは設計・検証ループの証明ではありません。

## 結果を説明する

発生条件、以前の失敗、変更後の動作、影響する契約、実施した確認を示します。モックと物理バックエンド、数値検証と実機検証、最終提案の未実行、不完全な配信など、主張に関わる限界を添えます。過去の実験証拠と記録条件を維持してください。移転ページや旧見出しの互換措置を残さず、現行文書を更新します。[文書の保守](development/documentation.md)を参照してください。
