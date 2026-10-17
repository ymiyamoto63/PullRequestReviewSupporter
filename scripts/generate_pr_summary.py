#!/usr/bin/env python3
"""PR の内容を決められたフォーマットの HTML にまとめる。

GitHub API から PR の情報・変更ファイル・コミットを取得し、
<out>/pr/<番号>/index.html と一覧ページ <out>/index.html を生成する。
標準ライブラリのみで動作する。

使い方:
    GITHUB_TOKEN=... python3 scripts/generate_pr_summary.py \
        --repo owner/name --pr 1 --out site
"""

import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")

# 1 ファイルあたりに表示する差分の最大行数(巨大な差分でページが重くならないように)
MAX_PATCH_LINES = 400
LARGE_PR_LINES = 500
LARGE_PR_FILES = 20


def api_request(path, token, method="GET", body=None, accept="application/vnd.github+json"):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as res:
        raw = res.read().decode()
        return raw if accept.endswith("html") else json.loads(raw)


def api_paginated(path, token):
    items, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        batch = api_request(f"{path}{sep}per_page=100&page={page}", token)
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def render_markdown(text, repo, token):
    """GitHub の Markdown API で PR 本文を HTML 化する。失敗したらプレーンテキストで表示する。"""
    if not text or not text.strip():
        return '<p class="muted">説明は書かれていません。</p>'
    try:
        return api_request(
            "/markdown", token, method="POST",
            body={"text": text, "mode": "gfm", "context": repo},
            accept="text/html",
        )
    except (urllib.error.URLError, OSError):
        return f"<pre>{html.escape(text)}</pre>"


def fmt_date(iso):
    if not iso:
        return "-"
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def file_category(path):
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    if "test" in lower or "spec" in lower:
        return "テスト"
    if lower.startswith(".github/"):
        return "CI / GitHub設定"
    if name.endswith((".md", ".rst", ".txt")) or lower.startswith("docs/"):
        return "ドキュメント"
    if name.endswith((".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".lock")) or name.startswith("."):
        return "設定・依存関係"
    if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".pdf")):
        return "画像・バイナリ"
    return "ソースコード"


def review_points(pr, files):
    """変更内容から、レビュー時に注意したい点を機械的に洗い出す。"""
    points = []
    total = pr["additions"] + pr["deletions"]
    cats = Counter(file_category(f["filename"]) for f in files)
    if total >= LARGE_PR_LINES or len(files) >= LARGE_PR_FILES:
        points.append(("warn", f"変更規模が大きめです({len(files)} ファイル / {total} 行)。分割できないか検討してください。"))
    if cats["ソースコード"] and not cats["テスト"]:
        points.append(("warn", "ソースコードの変更がありますが、テストの変更が含まれていません。"))
    if cats["テスト"]:
        points.append(("ok", f"テストの変更が {cats['テスト']} ファイル含まれています。"))
    if cats["CI / GitHub設定"]:
        points.append(("info", "CI / GitHub の設定が変更されています。ワークフローの権限やトリガーを確認してください。"))
    if cats["設定・依存関係"]:
        points.append(("info", "設定ファイルまたは依存関係が変更されています。"))
    if any(f["status"] == "removed" for f in files):
        points.append(("info", "削除されたファイルがあります。参照が残っていないか確認してください。"))
    if any(f["status"] == "renamed" for f in files):
        points.append(("info", "名前が変更されたファイルがあります。"))
    if not (pr.get("body") or "").strip():
        points.append(("warn", "PR の説明が空です。変更の目的を書いてもらいましょう。"))
    if pr.get("draft"):
        points.append(("info", "この PR はドラフトです。"))
    if not points:
        points.append(("ok", "特に注意が必要な点は見つかりませんでした。"))
    return points


PR_STATE_LABEL = {"open": "オープン", "closed": "クローズ", "merged": "マージ済み"}

STATUS_LABEL = {
    "added": "追加", "removed": "削除", "modified": "変更",
    "renamed": "名前変更", "copied": "コピー", "changed": "変更", "unchanged": "変更なし",
}


def render_patch(patch):
    if patch is None:
        return '<p class="muted">差分を表示できません(バイナリファイル、または差分が大きすぎます)。</p>'
    lines = patch.split("\n")
    truncated = len(lines) > MAX_PATCH_LINES
    out = []
    for line in lines[:MAX_PATCH_LINES]:
        cls = "ctx"
        if line.startswith("@@"):
            cls = "hunk"
        elif line.startswith("+"):
            cls = "add"
        elif line.startswith("-"):
            cls = "del"
        out.append(f'<span class="{cls}">{html.escape(line) or " "}</span>')
    body = "".join(out)
    note = f'<p class="muted">差分が長いため先頭 {MAX_PATCH_LINES} 行のみ表示しています。</p>' if truncated else ""
    return f'<pre class="diff">{body}</pre>{note}'


PAGE_CSS = """
:root{--bg:#f6f8fa;--card:#fff;--text:#1f2328;--muted:#656d76;--border:#d0d7de;--accent:#0969da;
--add-bg:#dafbe1;--add:#1a7f37;--del-bg:#ffebe9;--del:#cf222e;--hunk-bg:#ddf4ff;
--warn:#9a6700;--warn-bg:#fff8c5;--ok:#1a7f37;--ok-bg:#dafbe1;--info:#0969da;--info-bg:#ddf4ff}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--text:#e6edf3;--muted:#8d96a0;
--border:#30363d;--accent:#4493f8;--add-bg:#12261e;--add:#3fb950;--del-bg:#25171c;--del:#f85149;
--hunk-bg:#121d2f;--warn:#d29922;--warn-bg:#272115;--ok:#3fb950;--ok-bg:#12261e;--info:#4493f8;--info-bg:#121d2f}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent)}
h1{font-size:1.6rem;margin:0 0 4px}
h2{font-size:1.15rem;margin:0 0 12px;padding-bottom:6px;border-bottom:1px solid var(--border)}
section{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px 20px;margin-top:16px}
.muted{color:var(--muted)}
.meta{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0}
.meta dt{color:var(--muted)}.meta dd{margin:0}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.8rem;border:1px solid var(--border);margin-right:4px}
.stats{display:flex;flex-wrap:wrap;gap:12px}
.stat{flex:1 1 140px;border:1px solid var(--border);border-radius:6px;padding:10px 14px}
.stat b{display:block;font-size:1.4rem}
.plus{color:var(--add)}.minus{color:var(--del)}
ul.points{list-style:none;padding:0;margin:0}
ul.points li{padding:8px 12px;border-radius:6px;margin-bottom:6px}
li.warn{background:var(--warn-bg);color:var(--warn)}li.ok{background:var(--ok-bg);color:var(--ok)}li.info{background:var(--info-bg);color:var(--info)}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--border);vertical-align:top}
td.num,th.num{text-align:right;white-space:nowrap}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em}
details{border:1px solid var(--border);border-radius:6px;margin-bottom:8px}
summary{cursor:pointer;padding:8px 12px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em}
pre{overflow-x:auto}
pre.diff{margin:0;padding:8px 0;font-size:12.5px;line-height:1.45;border-top:1px solid var(--border)}
pre.diff span{display:block;padding:0 12px;white-space:pre}
.add{background:var(--add-bg)}.del{background:var(--del-bg)}.hunk{background:var(--hunk-bg);color:var(--muted)}
.markdown img{max-width:100%}
footer{margin-top:24px;font-size:.85rem;color:var(--muted)}
"""


def page(title, body):
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}</style>
</head>
<body><main>
{body}
</main></body>
</html>
"""


def build_pr_page(repo, pr, files, commits, body_html):
    e = html.escape
    state = "マージ済み" if pr.get("merged_at") else ("クローズ" if pr["state"] == "closed" else "オープン")
    if pr.get("draft"):
        state += "(ドラフト)"
    labels = "".join(f'<span class="badge">{e(l["name"])}</span>' for l in pr.get("labels", [])) or "-"
    reviewers = ", ".join(e(r["login"]) for r in pr.get("requested_reviewers", [])) or "-"

    cats = Counter(file_category(f["filename"]) for f in files)
    cat_rows = "".join(
        f"<tr><td>{e(c)}</td><td class='num'>{n}</td></tr>" for c, n in cats.most_common()
    )

    points = "".join(f'<li class="{k}">{e(t)}</li>' for k, t in review_points(pr, files))

    file_rows = "".join(
        f"<tr><td><a href='#file-{i}'><code>{e(f['filename'])}</code></a>"
        + (f"<br><span class='muted'>← {e(f['previous_filename'])}</span>" if f.get("previous_filename") else "")
        + f"</td><td>{e(STATUS_LABEL.get(f['status'], f['status']))}</td>"
        f"<td>{e(file_category(f['filename']))}</td>"
        f"<td class='num plus'>+{f['additions']}</td><td class='num minus'>-{f['deletions']}</td></tr>"
        for i, f in enumerate(files)
    )

    commit_rows = "".join(
        "<tr><td><a href='{url}'><code>{sha}</code></a></td><td>{msg}</td><td>{author}</td><td>{date}</td></tr>".format(
            url=e(c["html_url"]), sha=e(c["sha"][:7]),
            msg=e(c["commit"]["message"].split("\n", 1)[0]),
            author=e((c.get("author") or {}).get("login") or c["commit"]["author"]["name"]),
            date=e(fmt_date(c["commit"]["author"]["date"])),
        )
        for c in commits
    )

    diffs = "".join(
        f"<details id='file-{i}'{' open' if f['additions'] + f['deletions'] <= 80 else ''}>"
        f"<summary>{e(f['filename'])} <span class='plus'>+{f['additions']}</span> "
        f"<span class='minus'>-{f['deletions']}</span></summary>{render_patch(f.get('patch'))}</details>"
        for i, f in enumerate(files)
    )

    body = f"""
<p class="muted"><a href="../../">← PR 一覧</a> · {e(repo)}</p>
<h1>#{pr['number']} {e(pr['title'])}</h1>
<p><a href="{e(pr['html_url'])}">GitHub で PR を開く</a></p>

<section>
<h2>1. 基本情報</h2>
<dl class="meta">
<dt>状態</dt><dd>{e(state)}</dd>
<dt>作成者</dt><dd>{e(pr['user']['login'])}</dd>
<dt>ブランチ</dt><dd><code>{e(pr['base']['ref'])}</code> ← <code>{e(pr['head']['ref'])}</code></dd>
<dt>作成日時</dt><dd>{e(fmt_date(pr['created_at']))}</dd>
<dt>更新日時</dt><dd>{e(fmt_date(pr['updated_at']))}</dd>
<dt>ラベル</dt><dd>{labels}</dd>
<dt>レビュアー</dt><dd>{reviewers}</dd>
</dl>
</section>

<section>
<h2>2. 変更の規模</h2>
<div class="stats">
<div class="stat"><span class="muted">変更ファイル</span><b>{pr['changed_files']}</b></div>
<div class="stat"><span class="muted">追加行</span><b class="plus">+{pr['additions']}</b></div>
<div class="stat"><span class="muted">削除行</span><b class="minus">-{pr['deletions']}</b></div>
<div class="stat"><span class="muted">コミット</span><b>{pr['commits']}</b></div>
</div>
<div class="table-wrap" style="margin-top:12px"><table>
<thead><tr><th>種類</th><th class="num">ファイル数</th></tr></thead>
<tbody>{cat_rows}</tbody></table></div>
</section>

<section>
<h2>3. レビュー観点</h2>
<ul class="points">{points}</ul>
</section>

<section class="markdown">
<h2>4. PR の説明</h2>
{body_html}
</section>

<section>
<h2>5. 変更ファイル</h2>
<div class="table-wrap"><table>
<thead><tr><th>ファイル</th><th>状態</th><th>種類</th><th class="num">追加</th><th class="num">削除</th></tr></thead>
<tbody>{file_rows}</tbody></table></div>
</section>

<section>
<h2>6. コミット</h2>
<div class="table-wrap"><table>
<thead><tr><th>SHA</th><th>メッセージ</th><th>作成者</th><th>日時</th></tr></thead>
<tbody>{commit_rows}</tbody></table></div>
</section>

<section>
<h2>7. 差分</h2>
{diffs or '<p class="muted">差分はありません。</p>'}
</section>

<footer>生成日時: {e(fmt_date(datetime.now(timezone.utc).isoformat()))} · head <code>{e(pr['head']['sha'][:7])}</code></footer>
"""
    return page(f"#{pr['number']} {pr['title']}", body)


def build_index(repo, out_dir):
    """pr/*/meta.json を集めて PR 一覧ページを作る。"""
    metas = []
    for meta_path in (out_dir / "pr").glob("*/meta.json"):
        metas.append(json.loads(meta_path.read_text(encoding="utf-8")))
    metas.sort(key=lambda m: m["number"], reverse=True)
    e = html.escape
    rows = "".join(
        f"<tr><td class='num'>#{m['number']}</td><td><a href='pr/{m['number']}/'>{e(m['title'])}</a></td>"
        f"<td>{e(m['author'])}</td><td>{e(PR_STATE_LABEL.get(m['state'], m['state']))}</td>"
        f"<td class='num'><span class='plus'>+{m['additions']}</span> <span class='minus'>-{m['deletions']}</span></td>"
        f"<td>{e(fmt_date(m['updated_at']))}</td></tr>"
        for m in metas
    )
    body = f"""
<h1>PR レビューサマリー</h1>
<p class="muted">{e(repo)}</p>
<section>
<h2>PR 一覧</h2>
<div class="table-wrap"><table>
<thead><tr><th class="num">番号</th><th>タイトル</th><th>作成者</th><th>状態</th><th class="num">変更</th><th>更新日時</th></tr></thead>
<tbody>{rows or '<tr><td colspan="6" class="muted">まだサマリーはありません。</td></tr>'}</tbody></table></div>
</section>
"""
    (out_dir / "index.html").write_text(page(f"PR レビューサマリー - {repo}", body), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"), help="owner/name")
    parser.add_argument("--pr", type=int, required=True, help="PR 番号")
    parser.add_argument("--out", default="site", help="出力先ディレクトリ")
    args = parser.parse_args()
    if not args.repo:
        sys.exit("--repo か GITHUB_REPOSITORY を指定してください")

    token = os.environ.get("GITHUB_TOKEN", "")
    base = f"/repos/{args.repo}/pulls/{args.pr}"
    pr = api_request(base, token)
    files = api_paginated(f"{base}/files", token)
    commits = api_paginated(f"{base}/commits", token)
    body_html = render_markdown(pr.get("body"), args.repo, token)

    out_dir = Path(args.out)
    pr_dir = out_dir / "pr" / str(pr["number"])
    pr_dir.mkdir(parents=True, exist_ok=True)
    (pr_dir / "index.html").write_text(build_pr_page(args.repo, pr, files, commits, body_html), encoding="utf-8")
    state = "merged" if pr.get("merged_at") else pr["state"]
    meta = {
        "number": pr["number"], "title": pr["title"], "author": pr["user"]["login"],
        "state": state, "additions": pr["additions"], "deletions": pr["deletions"],
        "updated_at": pr["updated_at"],
    }
    (pr_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    build_index(args.repo, out_dir)
    print(f"generated {pr_dir / 'index.html'}")


if __name__ == "__main__":
    main()
