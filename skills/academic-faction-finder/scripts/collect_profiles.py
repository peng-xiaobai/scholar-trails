#!/usr/bin/env python3
"""Enumerate candidate works from independently identified author profiles."""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from faction_query import clean_orcid, write_csv


COLUMNS = ["source", "profile_id", "record_id", "record_url", "doi", "title", "year", "type",
           "authors", "external_ids"]


def get_json(url, api_key=""):
    headers = {"Accept": "application/json", "User-Agent": "academic-faction-finder/1.0"}
    if api_key:
        headers["x-api-key"] = api_key
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def orcid_works(profile, audit):
    root = f"https://pub.orcid.org/v3.0/{profile}"
    payload = get_json(root + "/works")
    for group in payload["group"]:
        for work in group.get("work-summary", []):
            record = work["put-code"]
            external_ids = [entry for entry in (work.get("external-ids") or {}).get("external-id", [])
                            if entry.get("external-id-relationship") == "self"]
            dois = sorted({entry["external-id-value"].strip().lower() for entry in external_ids
                           if entry.get("external-id-type") == "doi" and entry.get("external-id-value")})
            title = ((work.get("title") or {}).get("title") or {}).get("value", "")
            year = ((work.get("publication-date") or {}).get("year") or {}).get("value", "")
            yield {"record_id": record, "record_url": f"{root}/work/{record}",
                   "doi": dois[0] if len(dois) == 1 else "", "title": title, "year": year,
                   "type": work.get("type", ""), "external_ids": json.dumps(external_ids, ensure_ascii=False)}
    audit["groups"] = len(payload["group"])
    audit["status"] = "exhausted"


def semantic_works(profile, audit):
    root = f"https://api.semanticscholar.org/graph/v1/author/{profile}/papers"
    fields = "title,year,externalIds,authors,url,publicationTypes"
    offset = 0
    seen = set()
    while True:
        query = urlencode({"fields": fields, "limit": 100, "offset": offset})
        page = get_json(f"{root}?{query}", os.environ.get("SEMANTIC_SCHOLAR_API_KEY", ""))
        for work in page["data"]:
            record = work["paperId"]
            if record in seen:
                continue
            seen.add(record)
            ids = work.get("externalIds") or {}
            yield {"record_id": record, "record_url": work.get("url") or "",
                   "doi": (ids.get("DOI") or "").strip().lower(), "title": work.get("title") or "",
                   "year": work.get("year"), "type": "|".join(work.get("publicationTypes") or []),
                   "authors": json.dumps(work.get("authors") or [], ensure_ascii=False),
                   "external_ids": json.dumps(ids, ensure_ascii=False)}
        next_offset = page.get("next")
        if next_offset is None:
            audit["status"] = "exhausted"
            return
        if next_offset <= offset:
            audit["status"] = "stalled_page"
            return
        offset = next_offset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orcid", action="append", default=[], help="verified ORCID (repeatable)")
    parser.add_argument("--semantic-author-id", action="append", default=[],
                        help="Semantic Scholar author profile ID (repeatable)")
    parser.add_argument("--out", type=Path, required=True, help="candidate works CSV")
    args = parser.parse_args(argv)
    orcids = [clean_orcid(value) for value in args.orcid]
    if (not (orcids or args.semantic_author_id) or not all(orcids)
            or any(not re.fullmatch(r"[0-9]+", value) for value in args.semantic_author_id)):
        parser.error("provide a valid ORCID or numeric Semantic Scholar author ID")

    rows, audits = [], []
    for source, profiles, fetch in [("ORCID", orcids, orcid_works),
                                    ("Semantic Scholar", args.semantic_author_id, semantic_works)]:
        for profile in dict.fromkeys(profiles):
            audit = {"source": source, "profile_id": profile, "retrieved": 0}
            try:
                for work in fetch(profile, audit):
                    rows.append({"source": source, "profile_id": profile, **work})
                    audit["retrieved"] += 1
            except HTTPError as exc:
                audit.update(status="rate_limited" if exc.code == 429 else "error", http_status=exc.code)
            except (OSError, ValueError, KeyError) as exc:
                audit.update(status="error", error=str(exc))
            audits.append(audit)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, rows, COLUMNS)
    args.out.with_name(args.out.stem + "_coverage.json").write_text(
        json.dumps(audits, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Author profiles: {len(rows)} records. "
          + ", ".join(f"{a['source']} {a['profile_id']}: {a['status']}" for a in audits))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
