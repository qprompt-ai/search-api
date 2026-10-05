#!/usr/bin/env python3
"""Generic, config-driven REST search-API caller -- not specific to job
search or any other domain. The CONFIG env var (a small JSON object, see
README.md) declares which API to call, how to build the request, and how
to map its response into a flat list of items; this script contains no
knowledge of what the API or the results actually are.

Reads the mounted search_queries file for a line prefixed with the
config's own query_prefix (e.g. "adzuna: <query>"), falling back to the
whole file verbatim if that line isn't there -- e.g. a hand-run test that
mounts a bare keyword string directly.

Secrets are never embedded in CONFIG itself -- only the *names* of env
vars to resolve (auth_query_params' values, and any {NAME} placeholder in
url), same convention as qprompt's Resource.credential. Prints exactly
one JSON report to stdout ({"passed": true, "items": [...]} or
{"passed": false, "output": "..."}) -- run_container's generic default
needs nothing more than that, so this tool needs no
register_container_adapter entry."""

import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

_ENV_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+")
# Generic size guard, not specific to any one API's response shape --
# whatever's downstream of this tool (an LLM prompt, today) pays in
# tokens for every character and every extra item, and a raw API response
# field can carry markup/entities a downstream consumer never asked for.
_MAX_FIELD_CHARS = 400
_DEFAULT_MAX_RESULTS = 10


def _get_path(obj, path):
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _clean(value):
    if not isinstance(value, str):
        return value
    text = html.unescape(_HTML_TAG_RE.sub("", value)).strip()
    return text[:_MAX_FIELD_CHARS]


def _build_request(config: dict, query: str) -> urllib.request.Request:
    url = _ENV_PLACEHOLDER_RE.sub(lambda m: os.environ[m.group(1)], config["url"])
    method = config.get("method", "GET").upper()

    if method == "GET":
        params = dict(config.get("extra_params", {}))
        for query_param, env_name in config.get("auth_query_params", {}).items():
            params[query_param] = os.environ[env_name]
        params[config["query_param"]] = query
        return urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}")

    body = dict(config.get("extra_params", {}))
    body[config["body_param"]] = query
    return urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})


def main() -> None:
    config = json.loads(os.environ["CONFIG"])

    text = open("/workspace/search_queries", encoding="utf-8").read()
    prefix = config["query_prefix"]
    match = re.search(rf"^{re.escape(prefix)}:\s*(.+)$", text, re.MULTILINE)
    query = match.group(1).strip() if match else text.strip()

    try:
        request = _build_request(config, query)
        with urllib.request.urlopen(request, timeout=20) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "output": str(exc)}))
        return

    max_results = config.get("max_results", _DEFAULT_MAX_RESULTS)
    results = (_get_path(data, config["results_path"]) or [])[:max_results]
    extract_email_from = config.get("extract_email_from")
    items = []
    for result in results:
        item = {
            "source": prefix,
            **{field: _clean(_get_path(result, path)) for field, path in config["field_map"].items()},
        }
        # Scanned on the *raw*, untruncated field -- a real contact email
        # buried past _MAX_FIELD_CHARS in a long description must still be
        # found. Never invented: None when no email literally appears in
        # the API's own response, so a downstream consumer (an LLM
        # drafting outreach, today) has no contact to send to rather than
        # a plausible-looking guess.
        contact_email = None
        if extract_email_from:
            raw_value = _get_path(result, extract_email_from)
            if isinstance(raw_value, str):
                email_match = _EMAIL_RE.search(html.unescape(raw_value))
                contact_email = email_match.group(0) if email_match else None
            item["contact_email"] = contact_email
        items.append(item)
    print(json.dumps({"passed": True, "items": items}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- must still emit one JSON report, never a bare traceback
        print(json.dumps({"passed": False, "output": str(exc)}))
        sys.exit(0)
