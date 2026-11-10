"""Audit every current paper source, including DOI prefixes, with one live sample.

Usage: python -m scripts.audit_paper_pdfs --output ../docs/paper-pdf-site-audit.csv
The report is a snapshot; rerun before adding publisher-specific plugins.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import ipaddress
import json
import http.client
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

API = "https://agrihot.com/api/v1/items?category=%E8%AE%BA%E6%96%87&page_size=100&compact=true&page="
AGENT = "AgriHot-PDF-Audit/1.0 (+https://agrihot.com)"
PDF_META = re.compile(r'<meta\s+[^>]*name=["\']citation_pdf_url["\'][^>]*content=["\']([^"\']+)', re.I)
PDF_LINK = re.compile(r'(?:href|content)=["\']([^"\']+(?:\.pdf|/pdf)(?:\?[^"\']*)?)["\']', re.I)


def open_sample(url: str, *, limit: int = 128_000) -> tuple[int, str, str, bytes]:
    def public_url(value: str) -> None:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid URL")
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
            raise ValueError("non-public URL")

    class CheckedRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            target = urllib.parse.urljoin(request.full_url, newurl)
            public_url(target)
            return super().redirect_request(request, fp, code, msg, headers, target)

    public_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.build_opener(CheckedRedirect()).open(request, timeout=6) as response:
        return response.status, response.url, response.headers.get("Content-Type", ""), response.read(limit)


def page(number: int) -> list[dict]:
    for _ in range(5):
        try:
            return json.load(urllib.request.urlopen(API + str(number), timeout=15))["items"]
        except (OSError, urllib.error.URLError, http.client.HTTPException, json.JSONDecodeError):
            continue
    raise RuntimeError(f"Cannot audit feed page {number}")


def audit(group: tuple[str, list[dict]]) -> dict:
    key, items = group
    item = items[0]
    row = {"group": key, "count": len(items), "sample_id": item["id"],
           "sample_url": item["url"], "publisher_host": "", "result": "", "pdf_url": "", "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        status, final, mime, body = open_sample(item["url"])
        row["publisher_host"] = urllib.parse.urlsplit(final).hostname or ""
        if body.lstrip().startswith(b"%PDF-"):
            row["result"], row["pdf_url"] = "direct_pdf", final
            return row
        if "html" not in mime.lower():
            row["result"] = "non_html_no_pdf"
            return row
        source = body.decode("utf-8", "ignore")
        if "captcha-container" in source or "安全验证" in source[:1000]:
            row["result"] = "captcha"
            return row
        links = PDF_META.findall(source) or PDF_LINK.findall(source)
        if not links:
            row["result"] = "no_advertised_pdf"
            return row
        candidate = urllib.parse.urljoin(final, links[0].replace("&amp;", "&"))
        row["pdf_url"] = candidate
        try:
            _, actual, pdf_mime, content = open_sample(candidate, limit=32)
            row["result"] = ("pdf_header_verified" if content.lstrip().startswith(b"%PDF-")
                             else "captcha" if "/captcha/" in urllib.parse.urlsplit(actual).path
                             else "link_not_pdf")
        except urllib.error.HTTPError as exc:
            row["result"] = f"pdf_http_{exc.code}"
        except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
            row["result"] = "pdf_unavailable"
    except urllib.error.HTTPError as exc:
        row["result"] = f"page_http_{exc.code}"
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
        row["result"] = "page_unavailable"
    return row


def report_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe = [(key, "[redacted]" if any(word in key.lower() for word in ("token", "auth", "key", "sig", "credential")) else value)
            for key, value in pairs]
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(safe)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    first = page(1)
    pages = []
    number = 2
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        while True:
            batch = list(pool.map(page, range(number, number + 4)))
            pages.extend(batch)
            if any(not entries for entries in batch):
                break
            number += 4
    items = [*first, *(item for entries in pages for item in entries)]
    groups = defaultdict(list)
    for item in items:
        url = item["url"]
        host = urllib.parse.urlsplit(url).hostname or ""
        if host in {"doi.org", "dx.doi.org"}:
            doi = urllib.parse.urlsplit(url).path.lstrip("/")
            key = "doi_prefix:" + doi.split("/", 1)[0]
        else:
            key = "host:" + host
        groups[key].append(item)
    output = Path(args.output)
    previous = {}
    if output.exists():
        with output.open(newline="", encoding="utf-8") as file:
            previous = {row["group"]: row for row in csv.DictReader(file) if row.get("result") != "pending"}
    rows = {key: previous.get(key) or {"group": key, "count": len(entries), "sample_id": entries[0]["id"],
                                        "sample_url": entries[0]["url"], "publisher_host": "", "result": "pending",
                                        "pdf_url": "", "checked_at": ""} for key, entries in sorted(groups.items())}
    fields = list(next(iter(rows.values())))

    def save():
        with output.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows.values())

    save()
    pending = [(key, entries) for key, entries in groups.items() if rows[key]["result"] == "pending"]
    print(f"Inventory: {len(items)} papers, {len(rows)} source groups, {len(pending)} to check", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(audit, group) for group in pending]
        for number, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            row["sample_url"] = report_url(row["sample_url"])
            row["pdf_url"] = report_url(row["pdf_url"])
            rows[row["group"]] = row
            if number % 10 == 0 or number == len(futures):
                save()
                print(f"Checked {number}/{len(futures)}", flush=True)
    rows = list(rows.values())
    counts = {result: sum(row["result"] == result for row in rows) for result in {row["result"] for row in rows}}
    print(json.dumps({"items": len(items), "groups": len(rows), "results": counts}))


if __name__ == "__main__":
    main()
