"""Resolve every DOI paper to its publisher host, checkpointing progress.

Usage: python -m scripts.audit_doi_landings --output ../docs/paper-pdf-doi-landings.csv
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import http.client
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .audit_paper_pdfs import page, report_url


def public(value: str) -> None:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid URL")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ValueError("non-public URL")


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(request.full_url, newurl)
        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid DOI redirect")
        if parsed.hostname not in {"doi.org", "dx.doi.org"}:
            raise PublisherFound(target)
        public(target)
        return super().redirect_request(request, fp, code, msg, headers, target)


class PublisherFound(Exception):
    def __init__(self, url: str):
        self.url = url


def resolve(item: dict) -> dict:
    url = item["url"]
    row = {"item_id": str(item["id"]), "doi_url": report_url(url), "publisher_host": "", "landing_url": "", "result": ""}
    try:
        public(url)
        opener = urllib.request.build_opener(CheckedRedirect())
        for method in ("HEAD", "GET"):
            try:
                with opener.open(urllib.request.Request(url, method=method), timeout=6) as response:
                    row["landing_url"] = report_url(response.url)
                    row["publisher_host"] = urllib.parse.urlsplit(response.url).hostname or ""
                    row["result"] = "resolved" if row["publisher_host"] not in {"doi.org", "dx.doi.org"} else "doi_only"
                    return row
            except urllib.error.HTTPError as exc:
                if method == "HEAD" and exc.code in {403, 405, 406, 501}:
                    continue
                row["result"] = f"http_{exc.code}"
                return row
    except PublisherFound as found:
        row["landing_url"] = report_url(found.url)
        row["publisher_host"] = urllib.parse.urlsplit(found.url).hostname or ""
        row["result"] = "resolved"
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
        row["result"] = "unavailable"
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    items = []
    number = 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        while True:
            batch = list(pool.map(page, range(number, number + 4)))
            items.extend(item for entries in batch for item in entries)
            if any(not entries for entries in batch):
                break
            number += 4
    doi_items = [item for item in items if urllib.parse.urlsplit(item["url"]).hostname in {"doi.org", "dx.doi.org"}]
    output = Path(args.output)
    previous = {}
    if output.exists():
        with output.open(newline="", encoding="utf-8") as file:
            previous = {row["item_id"]: row for row in csv.DictReader(file) if row.get("result") != "pending"}
    rows = {str(item["id"]): previous.get(str(item["id"])) or {
        "item_id": str(item["id"]), "doi_url": report_url(item["url"]),
        "publisher_host": "", "landing_url": "", "result": "pending"} for item in doi_items}
    fields = list(next(iter(rows.values())))

    def save():
        with output.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows.values())

    save()
    pending = [item for item in doi_items if rows[str(item["id"])]["result"] == "pending"]
    print(f"Resolving {len(pending)}/{len(rows)} DOI papers", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(resolve, item) for item in pending]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            rows[row["item_id"]] = row
            if index % 50 == 0 or index == len(futures):
                save()
                print(f"Resolved {index}/{len(futures)}", flush=True)
    print(f"Landing hosts: {len({row['publisher_host'] for row in rows.values() if row['publisher_host']})}")


if __name__ == "__main__":
    main()
