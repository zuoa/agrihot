"""Test one PDF sample for every publisher host found by DOI resolution.

Usage: python -m scripts.audit_publisher_sites --output ../docs/paper-pdf-publisher-audit.csv
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
from collections import defaultdict
from pathlib import Path

from .audit_paper_pdfs import audit, report_url


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    root = output.parent
    landings = read_csv(root / "paper-pdf-doi-landings.csv")
    samples = read_csv(root / "paper-pdf-site-audit.csv")
    prior = {}
    for row in samples:
        host = row["publisher_host"]
        if host and row["result"] not in {"pending", "page_unavailable"}:
            prior.setdefault(host, row)
    if output.exists():
        for row in read_csv(output):
            if row["result"] != "pending":
                prior[row["group"].removeprefix("publisher:")] = row
    groups = defaultdict(list)
    for row in landings:
        if row["result"] == "resolved" and row["publisher_host"]:
            groups[row["publisher_host"]].append({"id": int(row["item_id"]), "url": row["doi_url"]})
    rows = {}
    for host, items in sorted(groups.items()):
        known = prior.get(host)
        rows[f"publisher:{host}"] = ({**known, "group": f"publisher:{host}", "count": len(items)} if known else {
            "group": f"publisher:{host}", "count": len(items), "sample_id": items[0]["id"],
            "sample_url": items[0]["url"], "publisher_host": host, "result": "pending",
            "pdf_url": "", "checked_at": ""})
    fields = list(next(iter(rows.values())))

    def save():
        with output.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows.values())

    save()
    pending = [(key, items) for key, items in groups.items() if rows[f"publisher:{key}"]["result"] == "pending"]
    print(f"Publisher hosts {len(groups)}, new samples {len(pending)}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(audit, (f"publisher:{host}", items)) for host, items in pending]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            row["sample_url"], row["pdf_url"] = report_url(row["sample_url"]), report_url(row["pdf_url"])
            rows[row["group"]] = row
            if index % 20 == 0 or index == len(futures):
                save()
                print(f"Publisher samples {index}/{len(futures)}", flush=True)


if __name__ == "__main__":
    main()
