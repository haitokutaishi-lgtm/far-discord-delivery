# FAR 図解 → Discord 定期配信

Google スプレッドシートのキューから、承認済みの次の1件を **水・土 12:00（日本時間）** に Discord へ投稿します。本文は **Embed（テーマ・概要・URL）** です。

## セキュリティ（必ず実施）

チャットなどに **Webhook URL 全文を貼らないでください**。漏れた場合は [Discord サーバー設定 → 連携サービス → Webhooks](https://support.discord.com/) から該当 Webhook を **削除し、新規作成** してください。トークン付き URL はパスワードと同じ扱いです。

## リポジトリ構成

- `scripts/deliver.py` — Sheets 読取・Discord 投稿・`sent_at` 更新
- `.github/workflows/far-deliver.yml` — 配信スケジュール（UTC に換算）
- `.github/workflows/pages.yml` — `docs/` を GitHub Pages に公開（図解 HTML の置き場）
- `docs/far/` — 図解 HTML をコミット（例: `docs/far/lease-modifications.html`）

GitHub Pages の URLは通常 `https://<ユーザー名>.github.io/<リポジトリ名>/far/<ファイル名>` です（リポジトリ設定で Pages を有効化後）。

## Google スプレッドシート

1. 新規シートにタブ名 **`Queue`**（別名にする場合はリポジトリ Variables の `SHEET_NAME`）
2. 1行目に次のヘッダ（A〜H）

| slug | title | summary | public_url | status | approved_at | scheduled_date | sent_at |
|------|-------|---------|------------|--------|-------------|----------------|---------|
| 識別子（UTM campaign にも使う） | Discord タイトル | 概要本文 | 図解ページの URL | `draft` / `approved` / など | 任意 | 空 or `YYYY-MM-DD`（この日付まで送らない） | 送信後に自動記入 |

3. 配信対象: **`status` が `approved`（大文字小文字無視）かつ `sent_at` が空** のうち、上から最初の1行。`scheduled_date` がある場合は **日本日付がその日以前** のものだけ。

4. [Google Cloud](https://console.cloud.google.com/) でプロジェクトを作成し **Google Sheets API** を有効化。サービスアカウントを作成し、JSON キーをダウンロード。

5. スプレッドシートを **サービスアカウントのメールアドレス** に共有（閲覧者で可、更新は `sent_at` 用に **編集者** が必要）。

## GitHub Secrets

| Name | 内容 |
|------|------|
| `GOOGLE_SPREADSHEET_ID` | スプレッドシート URL の `/d/` と `/edit` の間の ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | サービスアカウント JSON の全文（1行でも可） |
| `DISCORD_WEBHOOK_URL` | 配信先 Incoming Webhook の URL（**再発行した新しいもの**） |
| `DISCORD_ERROR_WEBHOOK_URL` | 任意。失敗時に投稿する別 Webhook |
| `DISCORD_THREAD_ID` | 任意。スレッド内に投稿する場合のスレッド ID（18桁前後の数値） |
| `DISCORD_ERROR_THREAD_ID` | 任意。エラー Webhook 投稿先スレッド ID |

任意の Repository variables: `SHEET_NAME`（デフォルト `Queue`）。

## GitHub へ載せる（初回）

このマシンでは **GitHub CLI にログインしていない**ため、こちらからリモート作成・push はできません。あなたのターミナルで **一度だけ** ログインし、次を実行してください。

```bash
gh auth login -h github.com -p https -w
cd ~/far-discord-delivery
./scripts/github-setup.sh
```

`github-setup.sh` は `far-discord-delivery` リポジトリの作成（または既存への接続）、`main` の push、可能なら **Pages（workflow）** の有効化まで行い、続けて `gh secret set` の例を表示します。

スプレッドシートの列見本は `docs/queue-template.csv` を Google シートにインポートして使えます。

## ローカルでの手動実行

```bash
cd far-discord-delivery
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/service-account.json"
export GOOGLE_SPREADSHEET_ID="..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
# 任意: export DISCORD_THREAD_ID="..."
python scripts/deliver.py
```

## スケジュール（Actions）

`far-deliver.yml` の cron は **UTC** です。水・土 12:00 JST = **水・土 03:00 UTC**。

手動テスト: GitHub の **Actions → FAR diagram Discord deliver → Run workflow**。

## UTM（任意）

`deliver.py` は `public_url` にまだ `utm_` が無いときだけ付与します。環境変数で上書き可: `UTM_SOURCE`, `UTM_MEDIUM`, `UTM_CAMPAIGN`（未設定時は slug を使用）。

## Webhook とスレッド

Incoming Webhook は **チャンネルに紐づき**ます。フォーラム投稿やスレッド内に出したい場合は、Discord 上で **スレッド ID** を開発者モードでコピーし、`DISCORD_THREAD_ID` を設定してください。**配信のたびに新規スレッドを API で切る**には Bot が必要です（本リポジトリは Webhook 前提）。
