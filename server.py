#!/usr/bin/env python
"""Read-only MCP server for the Google Search Console API."""
import os
import sys
from datetime import date, timedelta
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

SA_JSON = os.path.expanduser(os.environ.get("GSC_SA_JSON", "~/.config/ga-mcp/sa.json"))
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
V3 = "https://www.googleapis.com/webmasters/v3"

mcp = MCPServer("gsc")
_cached_session = None


def _session():
    global _cached_session
    if _cached_session is None:
        creds = service_account.Credentials.from_service_account_file(SA_JSON, scopes=SCOPES)
        _cached_session = AuthorizedSession(creds)
    return _cached_session


def _call(method, url, **kw):
    r = _session().request(method, url, **kw)
    if r.status_code == 403:
        raise ToolError(
            f"403 from {url}. Two likely causes: (1) the Search Console API is not enabled "
            f"in the GCP project, or (2) the service account's client_email from {SA_JSON} "
            f"has not been added as a user in Search Console "
            f"(Settings -> Users and permissions; 'Restricted' is enough). Body: {r.text[:300]}"
        )
    if not r.ok:
        raise ToolError(f"{r.status_code} from {url}: {r.text[:500]}")
    return r.json()


@mcp.tool()
def list_sites() -> list[dict]:
    """List every Search Console property the service account can read.

    Returns a list of {siteUrl, permissionLevel}. siteUrl is either a URL prefix
    property ("https://example.com/") or a domain property ("sc-domain:example.com");
    pass it verbatim as the `site` argument of the other tools.
    """
    return _call("GET", f"{V3}/sites").get("siteEntry", [])


@mcp.tool()
def search_analytics(
    site: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] = ["query"],
    filters: list[dict] | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Query Search Console performance data (clicks, impressions, CTR, position).

    site: siteUrl from list_sites(), e.g. "sc-domain:example.com".
    start_date/end_date: "YYYY-MM-DD" (data lags ~2-3 days).
    dimensions: any of query, page, country, device, date, searchAppearance.
    filters: e.g. [{"dimension": "page", "operator": "contains", "expression": "/blog"}]
             (operators: contains, notContains, equals, notEquals, includingRegex,
             excludingRegex). All filters are ANDed.
    limit: total rows wanted; paginated automatically in pages of 25000.

    Returns a list of rows: {keys: [...one value per dimension...], clicks,
    impressions, ctr, position}, sorted by clicks descending.
    """
    url = f"{V3}/sites/{quote(site, safe='')}/searchAnalytics/query"
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "type": "web",
        "dataState": "final",
    }
    if filters:
        body["dimensionFilterGroups"] = [{"filters": filters}]
    rows = []
    while len(rows) < limit:
        body["startRow"] = len(rows)
        body["rowLimit"] = min(25000, limit - len(rows))
        page = _call("POST", url, json=body).get("rows", [])
        rows += page
        if len(page) < body["rowLimit"]:
            break
    return rows


@mcp.tool()
def inspect_url(site: str, url: str) -> dict:
    """Inspect one URL's index status in Search Console. Quota: 2000 calls/day per property.

    site: siteUrl from list_sites(). url: the full page URL, must live under that property.

    Returns inspectionResult: indexStatusResult (coverageState, verdict, robotsTxtState,
    googleCanonical, lastCrawlTime), plus mobileUsabilityResult / richResultsResult and
    an inspectionResultLink when available.
    """
    return _call(
        "POST",
        "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
        json={"inspectionUrl": url, "siteUrl": site, "languageCode": "nl"},
    )


def _selftest():
    sites = list_sites()
    print(f"list_sites: {len(sites)} properties")
    for s in sites:
        print(f"  {s['siteUrl']}  ({s['permissionLevel']})")
    if not sites:
        raise RuntimeError("no properties: is the service account added as a user in Search Console?")
    site = sites[0]["siteUrl"]
    end = date.today() - timedelta(days=3)  # GSC data lags ~2-3 days
    start = end - timedelta(days=6)
    rows = search_analytics(site, str(start), str(end), limit=10)
    print(f"\nsearch_analytics: {site} {start}..{end} -> {len(rows)} rows")
    for r in rows:
        print(f"  {r['keys']}  clicks={r['clicks']} impr={r['impressions']} "
              f"ctr={r['ctr']:.3f} pos={r['position']:.1f}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        try:
            _selftest()
        except Exception as e:
            sys.stdout.flush()  # keep the progress lines above the error when piped
            print(f"SELFTEST FAILED: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        mcp.run()
