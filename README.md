# Pull Request Review Supporter

GitHub PR のレビューを効率化するため、PR 発行時にその内容を決められたフォーマットで分かりやすくまとめ、HTML として出力します。生成した HTML は GitHub Pages から参照できるようにします。

## 仕組み

PR が作成・更新されると GitHub Actions が動き、`action.yml`(コンポジットアクション)から
`scripts/generate_pr_summary.py` が PR の内容を、Approve してよいかを素早く判断するための HTML にまとめます。
生成した HTML は `gh-pages` ブランチに push され、GitHub Pages で公開されます。

- PR ごとのサマリー: `https://<owner>.github.io/<repo>/pr/<番号>/`
- PR 一覧: `https://<owner>.github.io/<repo>/`

アクセス制御付きの Pages(GitHub Enterprise Cloud)では URL が異なりますが、PR へのコメントには Pages API から取得した実際の URL が載ります。

PR が作成されると、サマリーへのリンクが PR にコメントされます。差分やコミットなどの詳細は PR を直接確認する前提です。

### サマリーの構成

1. **判断サマリー**: リスク度(高・中・低)、PR の要約、Approve 前に確認すること
2. **何を変更したか**: 変更点ごとの「変更前 → 変更後」カード、影響するコンポーネントの図、変更したエリア(ディレクトリ別の変更量)
3. **レビュー観点**: 重要箇所(認証認可、データベース、API、秘密情報、依存関係、CI/CD)の変更をルールで自動検出して必ず列挙し、AI が補足の観点を追加

### AI による要約(GitHub Copilot CLI)

変更内容の要約には [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/automate-with-actions) を非対話モードで使います。
利用には Copilot のプランと、次の設定が必要です。

1. **Copilot Requests** 権限を付けた fine-grained personal access token を作成します。
2. リポジトリの **Settings → Secrets and variables → Actions** で、Secret `COPILOT_GITHUB_TOKEN` として登録します。

Copilot の利用分はトークンを作成したユーザーの Copilot に計上されます。
Secret が未設定、または Copilot の呼び出しに失敗した場合でも、ルールによるレビュー観点と変更エリアの図は出力されます。

次の設定で動作を変更できます。

| 設定 | 既定値 | 内容 |
| --- | --- | --- |
| Actions 変数 `PR_SUMMARY_MODEL` | Copilot の既定 | 使用するモデル(`copilot --model` に渡す値) |
| 環境変数 `PR_SUMMARY_PROMPT_CHARS` | `40000` | Copilot に渡す最大文字数 |
| 環境変数 `PR_SUMMARY_RULES` | `scripts/review_rules.json` | 重要箇所の検出ルール |

### 重要箇所の検出ルール

`scripts/review_rules.json` に、ファイルパスと差分中のキーワード(正規表現)でルールを定義しています。
一致したものは AI の判断に関係なく、レビュー観点として必ず表示されます。リポジトリに合わせてルールを追加してください。

## セットアップ

1. 最初の PR でワークフローが動くと `gh-pages` ブランチが作られます。
2. リポジトリの **Settings → Pages** で、Source を「Deploy from a branch」、Branch を `gh-pages` / `/ (root)` にして保存します。

## 他のリポジトリに導入する

導入先のリポジトリに次のワークフローを置くと、再利用可能ワークフロー(`.github/workflows/pr-summary-reusable.yml`)を呼び出します。

```yaml
# .github/workflows/pr-summary.yml
name: PR Summary
on:
  pull_request:
    types: [opened, synchronize, reopened, edited, ready_for_review, closed]
jobs:
  summary:
    uses: ymiyamoto63/PullRequestReviewSupporter/.github/workflows/pr-summary-reusable.yml@main
    permissions:
      contents: write
      pull-requests: write
      pages: read
    secrets:
      COPILOT_GITHUB_TOKEN: ${{ secrets.COPILOT_GITHUB_TOKEN }}
    # with:
    #   model: <モデル名>
    #   rules: .github/pr-review-rules.json   # リポジトリ固有の検出ルール
```

導入先では次の設定が必要です。

- Secret `COPILOT_GITHUB_TOKEN`(上記「AI による要約」を参照)。Organization では Organization Secret にすると一括で配れます。
- 上記「セットアップ」の Pages 設定。
- Organization の Actions 設定で、ワークフローに書き込み権限を与えることが禁止されていないこと。

ステップ単位で組み込みたい場合は、アクションとして直接使うこともできます(`permissions` と `concurrency` は呼び出し側で設定してください)。

```yaml
steps:
  - uses: ymiyamoto63/PullRequestReviewSupporter@main
    with:
      copilot-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}
```

### 会社の Organization で使う場合

private / internal のアクションや再利用可能ワークフローは、同じ所有者(Organization・Enterprise)のリポジトリにしか共有できません。
会社の Organization で使う場合は、このリポジトリを Organization 内の internal リポジトリへコピー(または移管)し、次を行ってください。

1. コピー先の **Settings → Actions → General → Access** で、Organization(または Enterprise)内のリポジトリからのアクセスを許可します。
2. `.github/workflows/pr-summary-reusable.yml` 内のアクションの参照先(`ymiyamoto63/PullRequestReviewSupporter@main`)を、コピー先に書き換えます。
3. 導入先のワークフローの `uses:` もコピー先を指すようにします。
4. `COPILOT_GITHUB_TOKEN` は会社のアカウント(会社の Copilot ライセンス)で作成します。

## ローカルで試す

```sh
GITHUB_TOKEN=<トークン> COPILOT_GITHUB_TOKEN=<Copilot Requests 権限のトークン> python3 scripts/generate_pr_summary.py --repo owner/name --pr 1 --out site
open site/pr/1/index.html
```

Copilot CLI(`npm install -g @github/copilot`)が必要です。`--no-ai` を付けると Copilot を呼ばずに生成します。

## テスト

```sh
python3 -m unittest discover -s tests -v
```

PR と main への push で、GitHub Actions(`.github/workflows/test.yml`)でも実行されます。
