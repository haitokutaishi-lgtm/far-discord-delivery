#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v gh >/dev/null 2>&1; then
  echo "Install GitHub CLI: brew install gh" >&2
  exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "GitHub CLI に未ログインです。次を実行してからこのスクリプトを再実行してください:" >&2
  echo "  gh auth login -h github.com -p https -w" >&2
  echo "または PAT を stdin で渡す場合:" >&2
  echo "  gh auth login -h github.com --with-token < pat.txt" >&2
  exit 1
fi

OWNER=$(gh api user -q .login)
NAME="far-discord-delivery"
FULL="$OWNER/$NAME"

if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote origin: $(git remote get-url origin)"
  git push -u origin main
else
  if gh repo view "$FULL" >/dev/null 2>&1; then
    echo "リモート $FULL が GitHub にあります。origin を追加して push します。"
    git remote add origin "https://github.com/$FULL.git"
    git push -u origin main
  else
    echo "リポジトリ $FULL を新規作成して push します。"
    gh repo create "$FULL" --public --source="$ROOT" --remote=origin --push
  fi
fi

echo "Pages（GitHub Actions デプロイ）を有効化します…"
if gh api "repos/$FULL/pages" >/dev/null 2>&1; then
  echo "Pages は既に設定済みです。"
else
  gh api -X POST "repos/$FULL/pages" \
    -H "Accept: application/vnd.github+json" \
    -f build_type=workflow \
    || echo "Pages API が拒否されました。GitHub の Settings → Pages → Build and deployment → Source を「GitHub Actions」にしてください。"
fi

echo ""
echo "完了: https://github.com/$FULL"
echo ""
echo "次に Repository secrets（Settings → Secrets and variables → Actions）:"
echo "  GOOGLE_SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, DISCORD_WEBHOOK_URL"
echo "  任意: DISCORD_ERROR_WEBHOOK_URL, DISCORD_THREAD_ID, DISCORD_ERROR_THREAD_ID"
echo ""
echo "CLI 例:"
echo "  gh secret set GOOGLE_SPREADSHEET_ID -b\"スプレッドシートID\" -R \"$FULL\""
echo "  gh secret set GOOGLE_SERVICE_ACCOUNT_JSON < sa.json -R \"$FULL\""
echo "  gh secret set DISCORD_WEBHOOK_URL < webhook-url.txt -R \"$FULL\""
