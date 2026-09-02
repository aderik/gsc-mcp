# gsc-mcp

Read-only MCP server for the Google Search Console API. Python, stdio, one file
([server.py](server.py)). Authenticates with a Google Cloud service account
(shares credentials with Google's `analytics-mcp` if you already run it).

Three tools:

| tool | what it returns |
|---|---|
| `list_sites()` | every property the service account can read (`siteUrl`, `permissionLevel`) |
| `search_analytics(site, start_date, end_date, dimensions, filters, limit)` | performance rows: `keys`, `clicks`, `impressions`, `ctr`, `position` |
| `inspect_url(site, url)` | index status of one URL (quota: 2000/day) |

No write tools. Scope is `webmasters.readonly`.

## Two manual steps (required — without them everything returns 403)

1. **Enable the Search Console API** in your GCP project:
   https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
2. **Add the service account as a user in Search Console**: Settings → Users and
   permissions → Add user → the `client_email` from your `sa.json`
   (`python3 -c "import json;print(json.load(open('sa.json'))['client_email'])"`),
   permission "Restricted" is enough. Repeat per property (a domain property
   covers all its subdomains).

## Install

```bash
python3.14 -m venv .venv
.venv/bin/pip install "mcp>=2.1.1" "google-auth[requests]"
```

Credentials: service-account JSON at `~/.config/ga-mcp/sa.json`, override with the
`GSC_SA_JSON` env var.

## Test

```bash
.venv/bin/python server.py --selftest
```

Runs `list_sites()` plus one real `search_analytics` query over the last 7 days
(ending 3 days back, because GSC data lags ~2-3 days) and prints the rows.
Exit 1 on failure; a 403 names the two manual steps above.

## Register globally

```bash
claude mcp add --scope user gsc -- /path/to/gsc-mcp/.venv/bin/python /path/to/gsc-mcp/server.py
```
