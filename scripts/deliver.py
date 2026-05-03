#!/usr/bin/env python3
"""
Pick the next approved row from Google Sheets and post theme + summary + URL to Discord.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import traceback
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

JST = timezone(timedelta(hours=9))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column indices (0-based) for row A:H — header row in sheet row 1
COL_SLUG = 0
COL_TITLE = 1
COL_SUMMARY = 2
COL_PUBLIC_URL = 3
COL_STATUS = 4
COL_APPROVED_AT = 5
COL_SCHEDULED_DATE = 6
COL_SENT_AT = 7


def now_jst() -> datetime:
    return datetime.now(timezone.utc).astimezone(JST)


def parse_date_jst(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=JST)
            return dt
        except ValueError:
            continue
    return None


def extract_service_account_json(raw: str) -> dict[str, Any]:
    """
    GitHub Secret に JSON の前後に BOM・空白・誤って連結した文字が付くことがあるため、
    先頭のオブジェクト1つだけを抜き出してパースする。
    """
    s = (raw or "").strip().lstrip("\ufeff")
    # 全角ブレースや不可視文字だけ壊れているケースを正規化
    s = s.replace("\uff5b", "{").replace("\uff5d", "}")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    if not s:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is empty")

    # URL エンコードされた JSON（%7B ...）や、JSON が1つの文字列として二重に格納されているケース
    if "%7B" in s or "%22" in s:
        s = urllib.parse.unquote(s)
    if len(s) >= 2 and s[0] == '"' and s.rstrip().endswith('"'):
        try:
            inner = json.loads(s)
            if isinstance(inner, str) and "{" in inner:
                s = inner.strip()
        except json.JSONDecodeError:
            pass

    start = s.find("{")
    if start == -1:
        head = s[:48].replace("\n", "\\n").replace("\r", "\\r")
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON に ASCII の { がありません。"
            f"（文字数: {len(s)}、先頭付近 repr: {head!r}）"
            " Google Cloud から落とした .json をテキストで開き、先頭が {{ の1ファイルをそのまま貼るか、"
            "README の GOOGLE_SERVICE_ACCOUNT_JSON_B64（Base64 1行）を使ってください。"
        )

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                blob = s[start : i + 1]
                return json.loads(blob)

    raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON の JSON が閉じていません。ファイル全文を貼り直してください。")


def with_utm(url: str, slug: str) -> str:
    if not url or "utm_" in url:
        return url
    source = os.environ.get("UTM_SOURCE", "discord")
    medium = os.environ.get("UTM_MEDIUM", "far_weekly")
    campaign = os.environ.get("UTM_CAMPAIGN", slug or "far_diagram")
    parsed = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    q["utm_source"] = [source]
    q["utm_medium"] = [medium]
    q["utm_campaign"] = [campaign]
    new_query = urllib.parse.urlencode(q, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def _try_decode_b64(s: str) -> str | None:
    """If s looks like base64 (no ASCII '{'), try decode to UTF-8 JSON text."""
    t = "".join(s.strip().split())  # drop newlines/spaces often added when pasting b64
    if not t or "{" in t:
        return None
    if len(t) < 80:
        return None
    try:
        out = base64.b64decode(t, validate=True).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        try:
            out = base64.b64decode(t).decode("utf-8")
        except (ValueError, binascii.Error, UnicodeDecodeError):
            return None
    return out if "{" in out else None


def load_service_account_raw() -> str:
    """Plain JSON secret, Base64 in *_B64 secret, or Base64 mistakenly pasted into GOOGLE_SERVICE_ACCOUNT_JSON."""
    b64 = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_B64") or "").strip()
    if b64:
        try:
            return base64.b64decode(b64).decode("utf-8")
        except (ValueError, binascii.Error, UnicodeDecodeError) as e:
            raise SystemExit(f"GOOGLE_SERVICE_ACCOUNT_JSON_B64 のデコードに失敗しました: {e}") from e

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or ""
    if not raw.strip():
        raise SystemExit(
            "GOOGLE_SERVICE_ACCOUNT_JSON も GOOGLE_SERVICE_ACCOUNT_JSON_B64 も使えません（JSON が空）。"
            "リポジトリ「far-discord-delivery」の Settings → Secrets and variables → Actions の Repository secrets に、"
            "名前 GOOGLE_SERVICE_ACCOUNT_JSON で貼り直すか、README の Base64 手順で GOOGLE_SERVICE_ACCOUNT_JSON_B64 を追加してください。"
        )
    decoded = _try_decode_b64(raw)
    if decoded is not None:
        return decoded
    return raw


def get_sheets_service():
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    raw = load_service_account_raw()
    if cred_path and os.path.isfile(cred_path):
        creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    elif raw:
        info = extract_service_account_json(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        raise SystemExit(
            "GOOGLE_APPLICATION_CREDENTIALS か GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_SERVICE_ACCOUNT_JSON_B64 が必要です。"
        )

    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def a1_range(sheet_name: str, cell_range: str) -> str:
    safe = "'" + sheet_name.replace("'", "''") + "'"
    return f"{safe}!{cell_range}"


def read_queue(service, spreadsheet_id: str, sheet_name: str) -> list[list[Any]]:
    rng = a1_range(sheet_name, "A1:H500")
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=rng).execute()
    return result.get("values", [])


def update_sent(service, spreadsheet_id: str, sheet_name: str, row_1based: int, sent_iso: str) -> None:
    cell = a1_range(sheet_name, f"H{row_1based}")
    body = {"values": [[sent_iso]]}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=cell,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


def post_discord(webhook_base: str, payload: dict, thread_id: str | None) -> None:
    base = webhook_base.strip().rstrip("/")
    parts = urllib.parse.urlparse(base)
    q = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    q["wait"] = ["true"]
    if thread_id:
        q["thread_id"] = [thread_id]
    new_query = urllib.parse.urlencode(q, doseq=True)
    url = urllib.parse.urlunparse(parts._replace(query=new_query))
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def notify_error(error_webhook: str | None, message: str, thread_id: str | None) -> None:
    if not error_webhook:
        return
    payload = {"content": f"**FAR deliver failed**\n```{message[:1800]}```"}
    try:
        post_discord(error_webhook, payload, thread_id)
    except Exception:
        pass


def pick_next_row(rows: list[list[Any]], today_jst: datetime) -> tuple[int, list[Any]] | None:
    if not rows:
        return None
    header = rows[0]
    if len(header) < 8:
        raise SystemExit("Sheet needs header row A1:H1 with 8 columns (see README).")

    today_date = today_jst.date()

    for i, row in enumerate(rows[1:], start=2):
        while len(row) < 8:
            row.append("")
        status = str(row[COL_STATUS]).strip().lower()
        sent = str(row[COL_SENT_AT]).strip()
        if status != "approved" or sent:
            continue
        sched = parse_date_jst(str(row[COL_SCHEDULED_DATE]))
        if sched is not None and sched.date() > today_date:
            continue
        return i, row
    return None


def build_embed(title: str, summary: str, url: str) -> dict:
    desc = summary.strip() if summary else ""
    if url:
        if desc:
            desc += "\n\n"
        desc += url
    embed: dict[str, Any] = {"title": title[:256], "color": 0x3498DB}
    if desc:
        embed["description"] = desc[:4096]
    if url:
        embed["url"] = url
    return {"embeds": [embed]}


def main() -> int:
    spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
    sheet_name = (os.environ.get("SHEET_NAME") or "Queue").strip()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    error_webhook = os.environ.get("DISCORD_ERROR_WEBHOOK_URL", "").strip() or None
    thread_id = os.environ.get("DISCORD_THREAD_ID", "").strip() or None
    error_thread_id = os.environ.get("DISCORD_ERROR_THREAD_ID", "").strip() or None

    if not spreadsheet_id or not webhook:
        print("Missing GOOGLE_SPREADSHEET_ID or DISCORD_WEBHOOK_URL", file=sys.stderr)
        return 1

    try:
        service = get_sheets_service()
        rows = read_queue(service, spreadsheet_id, sheet_name)
        today = now_jst()
        picked = pick_next_row(rows, today)

        if not picked:
            print("No approved unsent row (or all future scheduled_date). Nothing to do.")
            return 0

        row_idx, row = picked
        slug = str(row[COL_SLUG]).strip()
        title = str(row[COL_TITLE]).strip()
        summary = str(row[COL_SUMMARY]).strip()
        public_url = str(row[COL_PUBLIC_URL]).strip()

        if not title or not public_url:
            raise ValueError(f"Row {row_idx}: title and public_url are required.")

        final_url = with_utm(public_url, slug)
        payload = build_embed(title, summary, final_url)
        post_discord(webhook, payload, thread_id)

        sent_iso = today.strftime("%Y-%m-%d %H:%M JST")
        update_sent(service, spreadsheet_id, sheet_name, row_idx, sent_iso)
        print(f"Posted row {row_idx}: {title!r}")
        return 0

    except Exception as e:
        tb = traceback.format_exc()
        msg = f"{e}\n{tb}"
        print(msg, file=sys.stderr)
        notify_error(error_webhook, msg, error_thread_id)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
