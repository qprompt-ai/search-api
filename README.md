# search-api

One generic, config-driven container tool: calls a REST search API and
returns a flat JSON list of results. Not specific to job search, or any
other domain -- `scrape.py` has no knowledge of what the API or the
results mean. What makes one call "Adzuna" and another "Jooble" is purely
the `CONFIG` env var each calling agent declares in its `.qprompt` source,
not anything in this image.

Already fits `run_container`'s generic default contract (read the mounted
`search_queries` file, print one JSON object with `passed`), so it needs
no `register_container_adapter` entry.

## CONFIG shape

```json
{
  "query_prefix": "adzuna",
  "method": "GET",
  "url": "https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1",
  "query_param": "what",
  "extra_params": {"max_days_old": "30", "results_per_page": "20"},
  "auth_query_params": {"app_id": "ADZUNA_APP_ID", "app_key": "ADZUNA_APP_KEY"},
  "results_path": "results",
  "field_map": {"title": "title", "company": "company.display_name", "url": "redirect_url", "description": "description"}
}
```

- `query_prefix` -- which line of the mounted `search_queries` file this
  call reads (e.g. `"adzuna: <query>"`).
- `method` -- `GET` (query becomes `query_param`) or `POST` (query becomes
  `body_param`, sent as a JSON body).
- `url` -- `{NAME}` placeholders are resolved from this container's own
  env vars at call time, same as `auth_query_params`' values -- CONFIG
  itself never contains a literal secret, only env var *names*.
- `results_path` / `field_map` -- dotted-path lookups into the API's own
  response shape, down to a flat `{"source", ...field_map keys}` item.
- `max_results` (optional, default 10) -- caps how many items come back.
  Every `field_map` value also gets HTML tags/entities stripped and is
  truncated to 400 chars, regardless of the API -- raw search-API fields
  routinely carry markup a downstream consumer (today, an LLM prompt) pays
  for in tokens without needing.
- `extract_email_from` (optional) -- a dotted path into the raw result
  (same namespace as `field_map`'s values, before cleaning/truncation) to
  scan for a literal email address, added to each item as
  `contact_email` (`null` if none found). Never invented -- only ever an
  address that genuinely appears in the API's own response.

Swapping APIs (a different job board, a product search, a real-estate
listing API, anything with a keyword-in/JSON-results-out shape) means
writing a new CONFIG value in the `.qprompt` source, never touching this
image.

## Build

```sh
docker build -t search-api:generic .
```
