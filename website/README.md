# Engineering research article

日本語の記事が直接開く、Astro製の公開用サイトです。トップページや記事一覧は
追加せず、現在の研究記事をそのまま掲載しています。

- `/` — 日本語
- `/en/` — English
- `/cube-cad/` — キューブ参考CADアセンブリ（日本語）
- `/cube-cad/en/` — Cube reference CAD assembly (English)

CAD sharing URLs (no login required):
https://engineering-agents-research.vercel.app/cube-cad/
https://engineering-agents-research.vercel.app/cube-cad/en/
- 記事上部の言語ボタンで相互に切り替えます。
- 図、データ、保存されたシミュレーション再生はHTMLに内蔵されています。
- Python、GPU、One-Pieceのストア、LLMサービスは公開サイトに不要です。

公開URL（Vercelへのログイン不要）：

- 日本語: https://engineering-agents-research-one-225b.vercel.app/
- English: https://engineering-agents-research-one-225b.vercel.app/en/

## Codexからの更新

通常は `engineering_agents` をCodexで開き、記事の変更を依頼してください。
研究記事の原本はEngineering Agents側で管理し、このサイトには公開用の英日版を
コピーして保持します。記事はリポジトリ内のファイルから生成します。初回ビルドでは、
すでに一般公開している参考CADデータの固定版をGitHub Releaseから取得し、SHA-256を照合します。

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

The CAD reference lives in `public/cube-cad/` and is copied unchanged by Astro.
The generated directory stays outside Git. `npm run build` first restores its
48 files from the public Release pinned in `assets/cube_cad.json`. The archive
and every file are checked by size and SHA-256; downloaded archives are cached
in `.asset-cache/`. Existing edited assets cause an error and are preserved.
For an offline build, download that exact archive in advance and run
`node scripts/restore-cube-cad.mjs /path/to/engineering-research-cube-cad-20261024.tar.gz`.
Only the already public CAD reference is in this package; private validation
datasets are not needed for a website build.

Run `node scripts/sync-cube-cad.mjs` to import the bilingual reference from the
local simulator output (or pass its directory as the first argument). This
removes the local source-directory path, rewrites download/language links for
the public site, and records source and asset hashes in `publication-manifest.json`.
CAD downloads and attribution accompany the pages. The supplied source license
and all fit limitations remain visible. The public site needs no simulator.
After intentionally publishing revised CAD pages, use
`node scripts/package-cube-cad.mjs /path/to/new-package.tar.gz RELEASE_ASSET_URL`
to prepare a new package and manifest, then upload that package to the specified
Release before committing the new pin. Node.js 22 and `tar` are required.

`src/pages/` defines the two static routes. `src/lib/article.mjs` adapts only
navigation and page metadata; recorded evidence and interactive scripts remain
unchanged. `content/balancing-cube/` contains the imported, self-contained article
copies. Run `npm run sync:article` to update them from the research workspace.

The article's numerical and physical limitations remain visible. Publishing
this site does not establish hardware performance or change requirement status.
