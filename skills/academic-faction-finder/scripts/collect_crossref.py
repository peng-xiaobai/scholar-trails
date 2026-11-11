#!/usr/bin/env python3
"""Collect independent Crossref candidates for the local authorship analysis."""

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from faction_query import clean_orcid, norm_name, write_csv


API = "https://api.crossref.org/v1/works"
FIELDS = "DOI,author,published,container-title,ISSN"
AUTHORSHIP_COLUMNS = ["work_id", "doi", "title", "year", "venue", "issn", "zone",
                      "author_name", "orcid", "org_name", "org_id", "author_order",
                      "is_first", "role_source"]
PAPER_COLUMNS = ["work_id", "year", "title", "routes", "known_name_match", "author_count"]


def get_message(url, params):
    request = Request(url + "?" + urlencode(params),
                      headers={"User-Agent": "academic-faction-finder/1.0 (Crossref metadata)"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)["message"]
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = exc.headers.get("Retry-After", str(2 ** attempt))
            if not delay.isdecimal() or int(delay) > 10:
                raise
            time.sleep(max(1, int(delay)))
        except URLError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def fetch_query(query, max_works, fields):
    params = {**query, "rows": min(100, max_works) if max_works else 100,
              "cursor": "*", "select": fields}
    works = {}
    audit = {"query": query, "reported_count": None}
    while True:
        try:
            page = get_message(API, params)
        except (OSError, ValueError, KeyError) as exc:
            audit.update(status="error", error=str(exc))
            break
        if audit["reported_count"] is None:
            audit["reported_count"] = page.get("total-results")
        items = page.get("items") or []
        previous_count = len(works)
        for item in items:
            if item.get("DOI"):
                works.setdefault(item["DOI"].lower(), item)
        count = audit["reported_count"]
        cursor = page.get("next-cursor")
        if max_works and (len(works) > max_works or (len(works) == max_works and count != max_works)):
            audit["status"] = "max_works"
            break
        if len(items) < params["rows"] or not cursor or count == len(works):
            audit["status"] = "exhausted" if count in (None, len(works)) else "count_mismatch"
            break
        if len(works) == previous_count:
            audit["status"] = "stalled_page"
            break
        params["cursor"] = cursor
    results = list(works.values())[:max_works or None]
    audit["retrieved"] = len(results)
    return results, audit


def author_name(author):
    given = (author.get("given") or "").strip()
    family = (author.get("family") or "").strip()
    if re.fullmatch(r"[\u3400-\u9fff]+", given) and re.fullmatch(r"[\u3400-\u9fff]+", family):
        return family + given
    return " ".join(filter(None, (given, family))) or author.get("name") or ""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", action="append", default=[], help="search name spelling (repeatable)")
    parser.add_argument("--query", action="append", default=[], help="bibliographic query (repeatable)")
    parser.add_argument("--doi", action="append", default=[], help="known DOI (repeatable)")
    parser.add_argument("--orcid", help="independently verified ORCID")
    parser.add_argument("--from-year", type=int, help="first publication year for name and bibliographic queries")
    parser.add_argument("--to-year", type=int, help="last publication year for name and bibliographic queries")
    parser.add_argument("--max-works", type=int, default=300,
                        help="maximum candidates per query, 0 to exhaust the cursor")
    parser.add_argument("--with-titles", action="store_true", help="include titles in the CSVs")
    parser.add_argument("--out", type=Path, required=True, help="output long-table CSV")
    args = parser.parse_args(argv)
    names = [name.strip() for name in args.name if name.strip()]
    terms = [term.strip() for term in args.query if term.strip()]
    orcid = clean_orcid(args.orcid)
    if args.orcid and not orcid:
        parser.error("--orcid requires an ORCID")
    if not (names or terms or args.doi or orcid) or args.max_works < 0:
        parser.error("provide a name, bibliographic query, DOI or ORCID and a nonnegative --max-works")
    first, last = args.from_year, args.to_year
    if any(year is not None and not 1 <= year <= 9999 for year in (first, last)) or (
            first is not None and last is not None and first > last):
        parser.error("invalid publication year range")
    dois = [re.sub(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)", "", d.strip(), flags=re.I).lower()
            for d in args.doi]
    if any(not re.fullmatch(r"10\.\d+/\S+", doi) for doi in dois):
        parser.error("--doi requires a DOI")

    fields = FIELDS + (",title" if args.with_titles else "")
    works, routes, audits = {}, defaultdict(set), []
    queries = [("name:" + name, {"query.author": name}) for name in dict.fromkeys(names)]
    queries += [("bibliographic:" + term, {"query.bibliographic": term})
                for term in dict.fromkeys(terms)]
    date_filter = ",".join(value for value in (
        f"from-pub-date:{first:04d}-01-01" if first else "",
        f"until-pub-date:{last:04d}-12-31" if last else "",
    ) if value)
    if date_filter:
        for _, query in queries:
            query["filter"] = date_filter
    queries[:0] = [("doi:" + doi, {"filter": "doi:" + doi}) for doi in dict.fromkeys(dois)]
    if orcid:
        queries.insert(0, ("orcid:" + orcid, {"filter": "orcid:" + orcid}))
    for label, query in queries:
        batch, audit = fetch_query(query, args.max_works, fields)
        if label.startswith("doi:") and not batch and audit["status"] == "exhausted":
            audit["status"] = "not_found"
        audits.append(audit)
        for item in batch:
            doi = item["DOI"].lower()
            works.setdefault(doi, item)
            routes[doi].add(label)
    keys = {norm_name(name) for name in names}
    rows, papers, missing_bylines = [], [], []
    for doi, item in sorted(works.items()):
        wid = "doi:" + doi
        date = ((item.get("published") or {}).get("date-parts") or [[]])[0]
        year = date[0] if date else ""
        title = (item.get("title") or [""])[0] if args.with_titles else ""
        authors = item.get("author") or []
        byline = [(i, author_name(author), author) for i, author in enumerate(authors, 1)]
        byline = [(i, name, author) for i, name, author in byline if name.strip()]
        if not byline or len(byline) < len(authors):
            missing_bylines.append(wid)
        papers.append({"work_id": wid, "year": year, "title": title,
                       "routes": " | ".join(sorted(routes[doi])),
                       "known_name_match": int(any(norm_name(name) in keys for _, name, _ in byline)),
                       "author_count": len(byline)})
        for i, name, author in byline:
            sequence = author.get("sequence")
            is_first = ""
            if sequence == "first":
                is_first = "yes"
            elif i == 1:
                is_first = "no" if sequence == "additional" else "yes"
            for org in author.get("affiliation") or [{}]:
                rows.append({"work_id": wid, "doi": doi, "year": year, "title": title,
                             "venue": (item.get("container-title") or [""])[0],
                             "issn": "|".join(item.get("ISSN") or []), "author_name": name,
                             "orcid": clean_orcid(author.get("ORCID")), "author_order": i,
                             "is_first": is_first,
                             "role_source": "Crossref author metadata",
                             "org_name": org.get("name") or ""})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, rows, AUTHORSHIP_COLUMNS)
    write_csv(args.out.with_name(args.out.stem + "_papers.csv"), papers, PAPER_COLUMNS)
    coverage = {"query_status": ("exhausted" if all(a["status"] == "exhausted" for a in audits)
                                 else "incomplete"), "queries": audits,
                "candidates": len(papers), "missing_bylines": missing_bylines}
    args.out.with_name(args.out.stem + "_coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Crossref: {len(papers)} candidate works, {len(rows)} authorship rows. "
          f"Query status: {coverage['query_status']}.")
    return 0 if papers else 1


if __name__ == "__main__":
    raise SystemExit(main())
