# Pull Request Review Supporter

GitHub PR のレビューを効率化するため、PR 発行時にその内容を決められたフォーマットで分かりやすくまとめ、HTML として出力します。生成した HTML は GitHub Pages から参照できるようにします。

## 仕組み

PR が作成・更新されると GitHub Actions(`.github/workflows/pr-summary.yml`)が動き、
`scripts/generate_pr_summary.py` が GitHub API から PR の情報を取得して HTML を生成します。
生成した HTML は `gh-pages` ブランチに push され、GitHub Pages で公開されます。

- PR ごとのサマリー: `https://<owner>.github.io/<repo>/pr/<番号>/`
- PR 一覧: `https://<owner>.github.io/<repo>/`

PR が作成されると、サマリーへのリンクが PR にコメントされます。

### サマリーのフォーマット

1. 基本情報(状態・作成者・ブランチ・日時・ラベル・レビュアー)
2. 変更の規模(ファイル数・追加/削除行数・コミット数・種類別ファイル数)
3. レビュー観点(変更内容から自動で洗い出した注意点)
4. PR の説明(Markdown を整形して表示)
5. 変更ファイル一覧
6. コミット一覧
7. 差分(ファイルごとに折りたたみ表示)

## セットアップ

1. 最初の PR でワークフローが動くと `gh-pages` ブランチが作られます。
2. リポジトリの **Settings → Pages** で、Source を「Deploy from a branch」、Branch を `gh-pages` / `/ (root)` にして保存します。

## ローカルで試す

```sh
GITHUB_TOKEN=<トークン> python3 scripts/generate_pr_summary.py --repo owner/name --pr 1 --out site
open site/pr/1/index.html
```
