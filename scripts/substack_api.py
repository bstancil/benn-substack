#!/usr/bin/env python3
"""
Substack API client.

The publication is configured in the repo-root .env file: SUBSTACK_URL is its
web address, and the earliest data to fetch is SUBSTACK_START_DATE. Public
endpoints (archive listing, individual posts) need no auth; private stats
endpoints require a logged-in session cookie in SUBSTACK_COOKIE.
"""

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).parent.parent


def load_env(key, env_path=None):
    """Read one KEY=value line from .env. Returns the value or None."""
    env_path = env_path or ROOT_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, value = line.partition("=")
        if k.strip() == key:
            return value.strip().strip("'\"") or None
    return None


BASE_URL = (load_env("SUBSTACK_URL") or "").rstrip("/")
PUBLICATION_START = load_env("SUBSTACK_START_DATE") or "2020-01-01"

# Substack occasionally rejects requests with no browser-like user agent
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

COOKIE_HELP = """\
No valid Substack session cookie found.

To fix:
  1. Log in to {url} in your browser
  2. Open devtools (cmd-opt-I) -> Application -> Cookies -> {url}
  3. Copy the value of the `substack.sid` cookie
  4. Put this line in {root}/.env:

     SUBSTACK_COOKIE=substack.sid=<paste value here>

Sessions last for months, so this is rare. Verify with:
  python scripts/update.py --check-auth
"""


class AuthError(Exception):
    """Raised when a stats endpoint rejects our cookie (or there isn't one)."""

    def __init__(self, message=None):
        super().__init__(
            message or COOKIE_HELP.format(url=BASE_URL or "your Substack", root=ROOT_DIR)
        )


def load_cookie(env_path=None):
    """Read SUBSTACK_COOKIE from .env. Returns a Cookie header string or None."""
    value = load_env("SUBSTACK_COOKIE", env_path)
    if not value:
        return None
    # Accept either a full cookie string or a bare substack.sid token
    if "=" not in value:
        value = f"substack.sid={value}"
    return value


class SubstackClient:
    def __init__(self, cookie=None, base_url=BASE_URL, delay=0.3):
        if not base_url:
            raise SystemExit(
                "SUBSTACK_URL is not set — add a line like\n"
                f"  SUBSTACK_URL=https://yourname.substack.com\nto {ROOT_DIR}/.env"
            )
        self.base_url = base_url
        self.delay = delay
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.cookie = cookie if cookie is not None else load_cookie()
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def _get(self, path, params=None, authed=False, retries=3):
        """GET a JSON endpoint with retry on transient failures."""
        if authed and not self.cookie:
            raise AuthError()

        url = f"{self.base_url}{path}"
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                # Substack sheds load by dropping connections; back off and retry
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
            if resp.status_code in (401, 403):
                if authed:
                    raise AuthError()
                resp.raise_for_status()
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < retries - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue
            resp.raise_for_status()
            try:
                return resp.json()
            except json.JSONDecodeError:
                # Login-redirect HTML instead of JSON means the cookie is stale
                if authed:
                    raise AuthError()
                raise
        raise RuntimeError(f"unreachable: {url}")

    # ---------- Public endpoints ----------

    def iter_archive(self, page_size=20):
        """Yield archive post metadata dicts, newest first.

        The API can return fewer items than requested mid-stream, so a short
        page doesn't mean the end — only an empty one does.
        """
        offset = 0
        while True:
            batch = self._get(
                "/api/v1/archive",
                params={"sort": "new", "limit": page_size, "offset": offset},
            )
            if not batch:
                return
            yield from batch
            offset += len(batch)
            time.sleep(self.delay)

    def get_post(self, slug):
        """Full post JSON, including body_html."""
        return self._get(f"/api/v1/posts/{slug}")

    # ---------- Private stats endpoints (cookie required) ----------

    def check_auth(self):
        """Return True if the cookie works against a stats endpoint."""
        try:
            self.get_email_stats(max_rows=1)
            return True
        except AuthError:
            return False

    def get_email_stats(self, max_rows=None):
        """All rows from the publication email_stats endpoint.

        The endpoint rejects a `limit` param with a 400 and serves fixed-size
        pages (currently 10 rows), so paginate by offset only.
        """
        rows, total = [], None
        while total is None or len(rows) < total:
            data = self._get(
                "/api/v1/publication/stats/email_stats",
                params={
                    "order_by": "post_date",
                    "order_direction": "desc",
                    "offset": len(rows),
                },
                authed=True,
            )
            total = data["total"]
            batch = data["rows"]
            if not batch:
                break
            rows.extend(batch)
            if max_rows is not None and len(rows) >= max_rows:
                break
            time.sleep(self.delay)
        return rows

    def get_post_stats(self, post_id):
        """Detailed stats (views, clicks, signups...) for one post."""
        return self._get(f"/api/v1/drafts/{post_id}/stats", authed=True)

    def get_subscriber_timeseries(self, from_date=PUBLICATION_START):
        """Full daily subscriber-count history."""
        if "T" not in from_date:
            from_date += "T00:00:00.000Z"
        return self._get(
            "/api/v1/publication/stats/emails/timeseries",
            params={"from": from_date},
            authed=True,
        )

    def get_visitor_sources(self, from_date, to_date):
        """Traffic sources (views, users, signups, conversions) for a date range."""
        rows, total = [], None
        while total is None or len(rows) < total:
            data = self._get(
                "/api/v1/publication/stats/visitor_sources",
                params={
                    "from_date": from_date,
                    "to_date": to_date,
                    "offset": len(rows),
                    "limit": 50,  # larger limits are rejected
                    "order_by": "views",
                    "order_direction": "desc",
                },
                authed=True,
            )
            total = data["total"]
            batch = data["rows"]
            if not batch:
                break
            rows.extend(batch)
            time.sleep(self.delay)
        return rows

    def get_traffic_timeseries(self, start=PUBLICATION_START, chunk_days=80):
        """Full daily site-traffic history.

        The API accepts any date range but only returns daily granularity for
        windows up to ~90 days (longer ranges come back bucketed by month), so
        walk the whole history in short overlapping chunks.
        """
        cur = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
        today = datetime.now(timezone.utc).date()
        rows = []
        while cur <= today:
            end = min(cur + timedelta(days=chunk_days), today)
            rows.extend(
                self._get(
                    "/api/v1/publication/stats/publication_traffic/timeseries",
                    params={"from": cur.isoformat(), "to": end.isoformat()},
                    authed=True,
                )
            )
            cur = end  # windows overlap by a day; the loader dedups by date
            if end == today:
                break
            time.sleep(self.delay)
        return rows


def today_str():
    return date.today().isoformat()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
