# Engineering research article

研究記事を掲載するAstro製の公開サイトです。

- `/` — 日本語
- `/en/` — English
- `/cube-cad/`、`/cube-cad/en/` — キューブ参考CADのアーカイブ案内
- `/isaac/`、`/isaac/viewer/`、`/isaac/report/` — Isaacキャンペーンのアーカイブ案内

[日本語記事](https://engineering-agents-research.vercel.app/)と
[英語記事](https://engineering-agents-research.vercel.app/en/)は、
記事上部の言語ボタンで切り替えられます。記事の図、データ、保存された
シミュレーション再生は記事のHTMLに内蔵されています。

## Codexからの更新

通常は `engineering_agents` をCodexで開き、記事の変更を依頼してください。
研究記事の原本はEngineering Agents側で管理し、このサイトには公開用の英日版を
コピーして保持します。記事はリポジトリ内のファイルから生成します。

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

公開先は `one-piece-eng/engineering-agents-research` です。チームURLの変更前に
発行した公開ドメインには `one-225b` が残っています。初回公開はGitHubに保存した
コミットから `website/` だけを抽出して実施しました。GitHubの自動公開には、
GitHub側のVercelアプリと `engineering_agents` は接続済みです。
このフォルダを含むPRを `main` にマージした後は、`main` の更新で本番を更新します。
それ以外のブランチはプレビューで確認します。初回公開のためにPRを自動マージは
していません。

本番ドメインは一般公開し、プレビューと個別デプロイURLはVercel認証で保護します。
公開前に両言語のデプロイ出力と検査済みビルドの一致を確認してください。

GitHub Actionsの `Research website` は、このフォルダの変更時に両言語をビルドし、
保存されたデータ、再生スクリプト、言語切替と出典ハッシュを検査します。
公開サイトのビルドにPythonやシミュレーション環境は不要です。

元のHTMLを直接渡すオフライン版は、研究ワークスペースの
`reports/iphone-research/` に引き続き保持しています。

## Source layout

The CAD and Isaac archives remain in the GitHub Releases pinned by
`assets/cube_cad.json` and `assets/isaac-web.json`. The manifests record the
size and SHA-256 of each archive and its individual files. The original
Isaac campaign archives and full raw telemetry remain private.

For offline use, the restore scripts accept the respective downloaded archive:

```sh
node scripts/restore-cube-cad.mjs /path/to/cad.tar.gz
node scripts/restore-isaac.mjs /path/to/isaac.tar.gz
```

The scripts verify the archive and its contents before extracting them into
`public/cube-cad/` and `public/isaac/`. Astro takes public files from `static/`,
so the offline files and archived viewer code under `public/` stay outside
the build.

The CAD sync and packaging scripts (`sync-cube-cad.mjs` and
`package-cube-cad.mjs`) preserve attribution, source licensing and asset
hashes. The Isaac tools (`export-isaac.py` and `package-isaac.mjs`) reproduce
the public projection from the audited campaign analysis cache and report.
Use a new release tag and manifest for any revised archive.

`src/pages/` defines the article and archive pages. `src/lib/article.mjs` adapts only
navigation and page metadata; recorded evidence and interactive scripts remain
unchanged. `content/balancing-cube/` contains the imported, self-contained article
copies. Run `npm run sync:article` to update them from the research workspace.

The article's numerical and physical limitations remain visible. Publishing
this site does not establish hardware performance or change requirement status.

## Deployment Storage

Preview builds skip commits with no changes under `website/` using the
`ignoreCommand` in `vercel.json`. Production builds always run. If Git history
is unavailable (for example an initial commit or shallow checkout), the preview
build runs rather than risk missing a website change. Vercel's ignored builds
may still count toward deployment limits.

Astro builds the article and five archive notices without downloading or
deploying the CAD and Isaac packages (about 302 MiB expanded). The notices
keep the page URLs available and link to the pinned GitHub Releases.

For existing deployment storage, review the project-specific deployment
retention policy and deployment Resources. Keep current production, required
rollback versions, and previews still used by active PRs. Shortening a policy or
removing old deployments can affect rollback and shared preview links. Inspect
usage after Vercel refreshes its measurements; a PR alone does not change the
Vercel retention policy or remove historical deployments.
