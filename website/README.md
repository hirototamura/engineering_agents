# Engineering research article

日本語の記事が直接開く、Astro製の公開用サイトです。トップページや記事一覧は
追加せず、現在の研究記事をそのまま掲載しています。

- `/` — 日本語
- `/en/` — English
- 記事上部の言語ボタンで相互に切り替えます。
- 図、データ、保存されたシミュレーション再生はHTMLに内蔵されています。
- Python、GPU、One-Pieceのストア、LLMサービスは公開サイトに不要です。

## Codexからの更新

通常は `engineering_agents` をCodexで開き、記事の変更を依頼してください。
研究記事の原本はEngineering Agents側で管理し、このサイトには公開用の英日版を
コピーして保持します。サイトのビルドは、コピー済みのファイルだけで完結します。

```sh
cd website
npm ci
npm run dev
```

表示を確認してから、次のコマンドで公開用の生成と検査を行います。

```sh
npm run check
```

研究ワークスペースで記事を更新した場合に、両言語を取り込み直すには：

```sh
npm run sync:article
npm run check
```

別の場所から取り込む場合は `npm run sync:article -- /path/to/iphone-research`。
`content/balancing-cube/source-manifest.json` に原本のSHA-256を記録します。
古い実験の判定、数値、コントローラをサイト側で書き換えません。

## Vercel

既存のGitHubリポジトリ `hirototamura/engineering_agents` をVercelに接続し、
公開対象をこの `website` フォルダに設定します。

- Root Directory: `website`
- Framework preset: Astro
- Install command: `npm ci`
- Build command: `npm run build`
- Output directory: `dist`
- Node.js: 22.22以降（現在のVercelのNode.js 22系を選択）
- 環境変数、データベース、サーバー用アダプタは不要です。

`vercel.json` にビルド設定を保持しています。GitHub/Vercelの接続後は、変更を
プレビューで確認し、公開する版を反映します。Vercelへのログインとプロジェクト
接続は別途必要です。このフォルダを作成しただけではWeb公開されません。

GitHub Actionsの `Research website` は、このフォルダの変更時に両言語をビルドし、
保存されたデータ、再生スクリプト、言語切替と出典ハッシュを検査します。
公開サイトのビルドにPythonやシミュレーション環境は不要です。

元のHTMLを直接渡すオフライン版は、研究ワークスペースの
`reports/iphone-research/` に引き続き保持しています。

## Source layout

`src/pages/` defines the two static routes. `src/lib/article.mjs` adapts only
navigation and page metadata; recorded evidence and interactive scripts remain
unchanged. `content/balancing-cube/` contains the imported, self-contained article
copies. Run `npm run sync:article` to update them from the research workspace.

The article's numerical and physical limitations remain visible. Publishing
this site does not establish hardware performance or change requirement status.
