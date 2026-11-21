"""yahoo-search MCP — Yahoo! JAPAN 検索をスクレイピングする自作 MCP サーバー（stdio）。

元実装: kendo910x/OpenWebUI infra/google-search-mcp/yahoo_search_server.py
        commit 5f7f3dd（ローカル clone HEAD 0288932b、2026-11-22 受領）
本PoCでの変更点（必要最小限・指示書 実施範囲1/429規定）:
  - HTTP 429 処理を追加: Retry-After を尊重（未指定なら DEFAULT_WAIT_AFTER_429 秒待機）、
    再試行は最大1回。再429または待機指定が MAX_WAIT_AFTER_429 超なら停止・報告。
    IP/UA変更・プロキシ切替・CAPTCHA回避は行わない。
  - 結果末尾に HTTP ステータス・待機・再試行の記録を付与。
  - 依存・パス以外は元実装のまま（セレクタ・判別マーカー・num_results clamp 同一）。

公開ツールは yahoo_search の1つのみ。Chromium 不要（HTTP GET + HTML パース）。
セレクタ・判別マーカーは Stage 0 実測（2026-10-18）に基づく:
  - タイトル: a[href] で囲まれた h3.sw-Card__titleMain
  - URL:      当該 a の href（Yahoo が付与する #:~:text= テキストフラグメントを除去）
  - 抜粋:     直後の div.sw-Card__summary
  - ブロック: captcha / ロボット確認 マーカー、または結果アンカー 0 件
リトライ・fallback・外部中継は意図的に持たない（429の1回再試行のみ例外）。
"""
import time

import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("yahoo-search")

SEARCH_URL = "https://search.yahoo.co.jp/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BLOCK_MARKERS = ("captcha", "ロボット確認", "reCAPTCHA")
SNIPPET_MAX = 300
DEFAULT_WAIT_AFTER_429 = 30   # Retry-After 未指定時の待機秒数
MAX_WAIT_AFTER_429 = 120      # これを超える待機指示は停止・報告


def _clean_url(href: str) -> str:
    # Yahoo が結果 URL に付ける #:~:text= テキストフラグメントを除去する
    return href.split("#:~:")[0]


def _parse_retry_after(value: str | None) -> float | None:
    """Retry-After（秒数形式のみ）を秒数に変換。Date形式や不正値は None。"""
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _fetch(query: str, log: list) -> requests.Response | str:
    """429規定に従い検索ページを取得する。失敗時は判別可能な文言を返す。"""
    attempt = 0
    while True:
        try:
            resp = requests.get(
                SEARCH_URL,
                params={"p": query, "ei": "utf-8"},
                headers={"User-Agent": USER_AGENT},
                timeout=20,
            )
        except requests.RequestException as exc:
            log.append(f"HTTP=exception({type(exc).__name__})")
            return f"検索取得失敗: ネットワーク/HTTP エラー（{type(exc).__name__}）"

        if resp.status_code != 429:
            log.append(f"HTTP={resp.status_code} retry={attempt}")
            return resp

        wait = _parse_retry_after(resp.headers.get("Retry-After"))
        if wait is None:
            wait = DEFAULT_WAIT_AFTER_429
            log.append("HTTP=429 Retry-After=none")
        else:
            log.append(f"HTTP=429 Retry-After={wait:g}")
        if wait > MAX_WAIT_AFTER_429:
            log.append(f"stop: 待機指示 {wait:g}s が上限 {MAX_WAIT_AFTER_429}s 超過")
            return (f"検索停止: 429 の待機指示 {wait:g} 秒が上限 {MAX_WAIT_AFTER_429} 秒を超過"
                    f"（{'/'.join(log)}）")
        if attempt >= 1:
            log.append("stop: 再試行後も429")
            return f"検索停止: 再試行後も429（{'/'.join(log)}）"
        time.sleep(wait)
        attempt += 1


@mcp.tool()
def yahoo_search(query: str, num_results: int = 5) -> str:
    """Search Yahoo! JAPAN and return titles, URLs and snippets of real results.

    Args:
        query: Search query (Japanese or English).
        num_results: Number of results to return (1-10, default 5).
    """
    try:
        n = max(1, min(10, int(num_results)))
    except (TypeError, ValueError):
        n = 5

    log: list[str] = []
    resp = _fetch(query, log)
    if isinstance(resp, str):
        return resp

    if resp.status_code != 200:
        return f"検索取得失敗: HTTP {resp.status_code}（{'/'.join(log)}）"

    page = resp.text
    soup = BeautifulSoup(page, "html.parser")

    results = []
    for h3 in soup.find_all("h3", class_="sw-Card__titleMain"):
        a = h3.find_parent("a", href=True)
        if a is None:
            continue
        title = h3.get_text(" ", strip=True)
        url = _clean_url(a["href"])
        if not title or not url.startswith("http"):
            continue
        snippet = ""
        summary = h3.find_next("div", class_="sw-Card__summary")
        if summary is not None:
            snippet = summary.get_text(" ", strip=True)[:SNIPPET_MAX]
        results.append((title, url, snippet))
        if len(results) >= n:
            break

    if not results:
        low = page.lower()
        if any(marker.lower() in low for marker in BLOCK_MARKERS):
            return f"検索ブロック: Yahoo! JAPAN がボット確認ページを返しました（{'/'.join(log)}）"
        return f"検索結果 0 件: 結果ブロックを抽出できませんでした（0件またはレイアウト変更）（{'/'.join(log)}）"

    lines = [f"Yahoo! JAPAN 検索結果: {query}"]
    for i, (title, url, snippet) in enumerate(results, 1):
        lines.append(f"{i}. {title}\n   URL: {url}")
        if snippet:
            lines.append(f"   {snippet}")
    lines.append(f"[HTTP] {'/'.join(log)}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
