# Pull Request Review Supporter

GitHub PR のレビューを効率化するため、PR 発行時にその内容を決められたフォーマットで分かりやすくまとめ、HTML として出力します。生成した HTML は GitHub Pages から参照できるようにします。

## 仕組み

PR が作成・更新されると GitHub Actions(`.github/workflows/pr-summary.yml`)が動き、
`scripts/generate_pr_summary.py` が PR の内容を、Approve してよいかを素早く判断するための HTML にまとめます。
生成した HTML は `gh-pages` ブランチに push され、GitHub Pages で公開されます。

- PR ごとのサマリー: `https://<owner>.github.io/<repo>/pr/<番号>/`
- PR 一覧: `https://<owner>.github.io/<repo>/`

PR が作成されると、サマリーへのリンクが PR にコメントされます。差分やコミットなどの詳細は PR を直接確認する前提です。

### サマリーの構成

1. **判断サマリー**: リスク度(高・中・低)、PR の要約、Approve 前に確認すること
2. **何を変更したか**: 変更点ごとの「変更前 → 変更後」カード、影響するコンポーネントの図、変更したエリア(ディレクトリ別の変更量)
3. **レビュー観点**: 重要箇所(認証認可、データベース、API、秘密情報、依存関係、CI/CD)の変更をルールで自動検出して必ず列挙し、AI が補足の観点を追加

### AI による要約(GitHub Models)

変更内容の要約には [GitHub Models](https://docs.github.com/github-models) を使います。ワークフローの
`permissions: models: read` により標準の `GITHUB_TOKEN` で呼び出すため、API キーの登録は不要です。
GitHub Models が使えない場合でも、ルールによるレビュー観点と変更エリアの図は出力されます。

環境変数で次を変更できます。

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `PR_SUMMARY_MODEL` | `openai/gpt-4.1` | 使用するモデル |
| `PR_SUMMARY_PROMPT_CHARS` | `20000` | モデルに渡す最大文字数(プランの入力上限に合わせて調整) |
| `PR_SUMMARY_RULES` | `scripts/review_rules.json` | 重要箇所の検出ルール |

### 重要箇所の検出ルール

`scripts/review_rules.json` に、ファイルパスと差分中のキーワード(正規表現)でルールを定義しています。
一致したものは AI の判断に関係なく、レビュー観点として必ず表示されます。リポジトリに合わせてルールを追加してください。

## セットアップ

1. 最初の PR でワークフローが動くと `gh-pages` ブランチが作られます。
2. リポジトリの **Settings → Pages** で、Source を「Deploy from a branch」、Branch を `gh-pages` / `/ (root)` にして保存します。

## ローカルで試す

```sh
GITHUB_TOKEN=<models:read 権限を持つトークン> python3 scripts/generate_pr_summary.py --repo owner/name --pr 1 --out site
open site/pr/1/index.html
```

`--no-ai` を付けると GitHub Models を呼ばずに生成します。
