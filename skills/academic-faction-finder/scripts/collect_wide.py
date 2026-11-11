#!/usr/bin/env python3
"""Collect OpenAlex publication candidates for one researcher.

Across institutions, use independently verified ORCID or author positions on
known papers to complement candidate author IDs. Keep exact-query hits even
when their signatures use an unknown spelling. Search by affiliation separately
and use verified coauthors to find candidates with split author IDs.
The candidate CSV is input for local identity resolution, and the coverage
JSON records the result of each query.

It never reads abstracts, full text or references. Titles/DOIs are opt-in via
--with-titles and are used only for a human-verifiable paper list.

"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from faction_query import norm_name, openalex_byline_orcid, openalex_org_pairs

OA = "https://api.openalex.org"
COLS = ["work_id", "doi", "title", "year", "venue", "issn", "zone",
        "author_name", "orcid", "org_name", "org_id", "author_order",
        "source_author_id", "raw_author_name", "profile_author_name", "profile_orcid",
        "is_first", "is_corresponding", "role_source"]


def short(v):
    return str(v or "").strip().rstrip("/").rsplit("/", 1)[-1]


def oa_get(path, params, api_key="", retries=3):
    p = dict(params)
    if api_key:
        p["api_key"] = api_key
    url = OA + path + "?" + urllib.parse.urlencode(p)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "academic-faction-finder/collect_wide (co-authorship research)",
                "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = RuntimeError(f"OpenAlex HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
            if e.code in (400, 401, 402, 403, 404, 429):
                break
        except Exception as e:
            last = e
        time.sleep(1.2 * (i + 1))
    raise last or RuntimeError("OpenAlex request failed")


def fetch(filter_str, fields, api_key, max_works):
    works, page, cursor = {}, 1, "*"
    audit = {"query": filter_str, "reported_count": None}
    params = {"filter": filter_str, "select": ",".join(fields), "per-page": 100}
    while True:
        params.update({"cursor": cursor} if api_key else {"page": page})
        try:
            data = oa_get("/works", params, api_key)
        except (RuntimeError, OSError) as exc:
            audit.update(status="error", error=str(exc))
            break
        meta = data.get("meta") or {}
        if audit["reported_count"] is None:
            audit["reported_count"] = meta.get("count")
        batch = data.get("results") or []
        for w in batch:
            wid = short(w.get("id"))
            if wid:
                works.setdefault(wid, w)
        print(f"  page {page}: +{len(batch)} (total {len(works)})", flush=True)
        expected = audit["reported_count"]
        next_cursor = meta.get("next_cursor")
        exhausted = not batch or (not next_cursor if api_key else len(batch) < 100)
        if len(works) > max_works or (len(works) >= max_works and not exhausted
                                     and expected != len(works)):
            audit["status"] = "max_works"
            break
        if exhausted or expected == len(works):
            audit["status"] = ("exhausted" if expected in (None, len(works))
                               else "count_mismatch")
            break
        if not api_key and page == 100:
            audit["status"] = "basic_paging_limit"
            break
        if api_key and next_cursor == cursor:
            audit["status"] = "stalled_cursor"
            break
        cursor = next_cursor
        page += 1
        time.sleep(0.15)
    results = list(works.values())[:max_works]
    audit["retrieved"] = len(results)
    if audit["status"] != "exhausted":
        print(f"WARNING: incomplete OpenAlex query ({audit['status']}): {filter_str}",
              file=sys.stderr)
    return results, audit


def affiliation_text(ash):
    parts = [i.get("display_name") or "" for i in (ash.get("institutions") or [])]
    parts += list(ash.get("raw_affiliation_strings") or [])
    return " | ".join(p for p in parts if p)


def name_for_signature(ash, variants):
    display = ((ash.get("author") or {}).get("display_name") or "").strip()
    raw = (ash.get("raw_author_name") or "").strip()
    return raw if norm_name(raw) in variants or not display else display


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org-id", action="append", default=[],
                    help="OpenAlex institution ID (repeatable, OR)")
    ap.add_argument("--across-affiliations", action="store_true",
                    help="fetch candidate author IDs across all institutions; verify identity downstream")
    ap.add_argument("--author-ids", default="",
                    help="comma-separated OpenAlex author IDs (candidates / split entities)")
    ap.add_argument("--coauthor-id", action="append", default=[], metavar="AUTHOR_ID",
                    help="verified former coauthor's OpenAlex ID (repeatable); "
                         "narrow the name search to works with one of these coauthors")
    ap.add_argument("--orcid", default="", help="independently verified ORCID for a cross-affiliation search")
    ap.add_argument("--known-work", action="append", default=[], metavar="ID@POSITION",
                    help="verified author position on a work identified by OpenAlex ID or DOI (repeatable)")
    ap.add_argument("--name-variants", default="",
                    help="comma-separated name spellings for byline and affiliation searches")
    ap.add_argument("--org-match", default="",
                    help="optional substring the target signature's affiliation must contain")
    ap.add_argument("--affil-search", action="append", default=[],
                    help="additional raw_affiliation_strings.search scope (repeatable, OR)")
    ap.add_argument("--from-year", type=int)
    ap.add_argument("--to-year", type=int)
    ap.add_argument("--max-works", type=int, default=2000)
    ap.add_argument("--api-key", default=os.environ.get("OPENALEX_API_KEY", ""))
    ap.add_argument("--with-titles", action="store_true",
                    help="also fetch DOI/title/venue for a verifiable paper list")
    ap.add_argument("--out", required=True, help="output long-table CSV path")
    ap.add_argument("--papers-out", help="optional paper-list CSV path")
    args = ap.parse_args(argv)
    if not args.across_affiliations and not args.org_id:
        ap.error("--org-id is required unless --across-affiliations is set")
    if args.across_affiliations and args.org_match:
        ap.error("--org-match would exclude cross-affiliation candidates")
    if not args.across_affiliations and (args.orcid or args.known_work):
        ap.error("--orcid and --known-work require --across-affiliations")
    if args.max_works <= 0:
        ap.error("--max-works must be positive")

    ids = {short(x).upper() for x in args.author_ids.split(",") if x.strip()}
    coauthors = sorted({short(x).upper() for x in args.coauthor_id})
    names = list(dict.fromkeys(x.strip() for x in args.name_variants.split(",") if x.strip()))
    variants = {norm_name(x) for x in names} - {""}
    if coauthors and (not args.across_affiliations or not variants
                      or any(not re.fullmatch(r"A\d+", cid) for cid in coauthors)):
        ap.error("--coauthor-id requires valid OpenAlex author IDs, "
                 "--across-affiliations and --name-variants")
    orcid = short(args.orcid).upper()
    if args.orcid and not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid):
        ap.error("--orcid requires a valid ORCID format")
    if not args.across_affiliations and (not ids or not variants):
        ap.error("scoped collection requires --author-ids and --name-variants")
    if not (ids or orcid or args.known_work or variants):
        ap.error("provide --author-ids, --orcid, --known-work, or --name-variants")
    if args.affil_search and not variants:
        ap.error("--affil-search requires --name-variants")

    org_scope = (["authorships.institutions.id:" + "|".join(short(x) for x in args.org_id)]
                 if args.org_id else [])
    base = []
    if args.from_year:
        base.append(f"from_publication_date:{args.from_year}-01-01")
    if args.to_year:
        base.append(f"to_publication_date:{args.to_year}-12-31")

    # A raw-affiliation scope must NOT be AND-ed with the author-ID list:
    # many papers of a split entity have no usable author ID at all.
    fields = ["id", "publication_year", "authorships", "authors_count"]
    if args.with_titles:
        fields += ["doi", "title", "primary_location"]
    merged = {}
    routes = defaultdict(set)
    audits = []
    for spec in dict.fromkeys(args.known_work):
        identifier, _, pos = spec.rpartition("@")
        doi = re.sub(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)", "", identifier, flags=re.I)
        wid = short(identifier).upper()
        if re.fullmatch(r"10\.\d+/\S+", doi):
            wid = "doi:" + urllib.parse.quote(doi, safe="/")
        elif not re.fullmatch(r"W\d+", wid):
            ap.error("--known-work requires an OpenAlex work ID or DOI")
        if not pos.isdecimal() or int(pos) < 1:
            ap.error("--known-work requires a 1-based author position after @")
        try:
            work = oa_get(f"/works/{wid}", {"select": ",".join(fields)}, args.api_key)
        except (RuntimeError, OSError) as exc:
            audits.append({"query": spec, "status": "error", "retrieved": 0, "error": str(exc)})
            continue
        actual_id = short(work.get("id"))
        authors = work.get("authorships") or []
        if not actual_id or int(pos) > len(authors):
            audits.append({"query": spec, "status": "missing_signature", "retrieved": 0})
            continue
        candidate = short((authors[int(pos) - 1].get("author") or {}).get("id"))
        if candidate:
            ids.add(candidate.upper())
        merged[actual_id] = work
        routes[actual_id].add("known_work")
        audits.append({"query": spec, "status": "exhausted", "retrieved": 1,
                       "resolved_work_id": actual_id, "candidate_author_id": candidate})

    author_scope = base if args.across_affiliations else org_scope + base
    ids = sorted(ids)
    scopes = [("author_id", ",".join(["authorships.author.id:" + "|".join(ids[i:i + 100])] + author_scope))
              for i in range(0, len(ids), 100)]
    if orcid:
        scopes.append(("orcid", ",".join(["authorships.author.orcid:" + orcid] + base)))
    if args.across_affiliations and not coauthors:
        scopes += [("raw_name", ",".join(["raw_author_name.search:" + name] + base))
                   for name in names]
    for i in range(0, len(coauthors), 100):
        coauthor_filter = "authorships.author.id:" + "|".join(coauthors[i:i + 100])
        scopes += [("coauthor", ",".join([coauthor_filter, "raw_author_name.search:" + name] + base))
                   for name in names]
    scopes += [("affiliation", ",".join(["raw_affiliation_strings.search:" + t] + org_scope + base))
               for t in args.affil_search]
    for route, f in scopes:
        print("fetching:", f[:150])
        batch, audit = fetch(f, fields, args.api_key, args.max_works)
        audits.append(audit)
        for w in batch:
            wid = short(w.get("id"))
            merged.setdefault(wid, w)
            routes[wid].add(route)
    print("merged works:", len(merged))

    org_match = args.org_match.lower().strip()
    selected = []
    name_hits = {}
    incomplete_bylines = {}
    for wid, w in merged.items():
        yr = w.get("publication_year")
        is_anchor = "known_work" in routes[wid]
        if not is_anchor and args.from_year and (yr is None or yr < args.from_year):
            continue
        if not is_anchor and args.to_year and (yr is None or yr > args.to_year):
            continue
        listed = len(w.get("authorships") or [])
        reported = w.get("authors_count")
        needs_full_byline = reported > listed if reported is not None else listed == 100
        if not is_anchor and needs_full_byline:
            try:
                full = oa_get(f"/works/{wid}", {"select": ",".join(fields)}, args.api_key)
            except (RuntimeError, OSError) as exc:
                incomplete_bylines[wid] = str(exc)
            else:
                if len(full.get("authorships") or []) >= (reported or listed):
                    w = full
                else:
                    incomplete_bylines[wid] = "single-work response lacks reported authorships"
        authors_read = len(w.get("authorships") or [])
        if reported is not None and authors_read < reported:
            incomplete_bylines.setdefault(wid, "fewer authorships than authors_count")
        if authors_read >= 5000:
            incomplete_bylines[wid] = "provider authorship limit reached"
        name_hits[wid] = any(
            norm_name(name_for_signature(ash, variants)) in variants
            and (not org_match or org_match in affiliation_text(ash).lower())
            for ash in (w.get("authorships") or [])
        )
        exact_route = bool(routes[wid] & {"known_work", "author_id", "orcid"})
        if routes[wid] == {"coauthor"} and wid not in incomplete_bylines:
            byline = w.get("authorships") or []
            coauthor_positions = {pos for pos, ash in enumerate(byline)
                                  if short((ash.get("author") or {}).get("id")).upper() in coauthors}
            if not any(norm_name(name_for_signature(ash, variants)) in variants
                       and coauthor_positions - {pos} for pos, ash in enumerate(byline)):
                continue
        if name_hits[wid] or (args.across_affiliations and (exact_route or wid in incomplete_bylines)):
            selected.append(w)
    print("selected candidate papers:", len(selected))
    vc, yc = Counter(), Counter()
    for w in selected:
        yc[w.get("publication_year")] += 1
        for ash in w.get("authorships") or []:
            nm = norm_name(name_for_signature(ash, variants))
            if nm in variants:
                vc[nm] += 1
    print("variant breakdown:", dict(vc))
    print("years:", dict(sorted(yc.items(), key=lambda x: (x[0] or 0))))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    coverage_path = out.with_name(out.stem + "_coverage.json")
    coverage_path.write_text(json.dumps({
        "query_status": ("exhausted" if not incomplete_bylines
                         and all(a["status"] == "exhausted" for a in audits) else "incomplete"),
        "queries": audits, "unique_retrieved": len(merged), "candidates": len(selected),
        "incomplete_bylines": incomplete_bylines,
        "candidates_without_known_name": sum(not name_hits[short(w.get("id"))] for w in selected),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", coverage_path)
    rows = []
    for w in selected:
        wid = short(w.get("id"))
        src = ((w.get("primary_location") or {}).get("source") or {})
        venue = src.get("display_name") or "" if args.with_titles else ""
        for pos, ash in enumerate(w.get("authorships") or [], 1):
            au = ash.get("author") or {}
            profile_name = (au.get("display_name") or "").strip()
            name = (ash.get("raw_author_name") or "").strip() or profile_name
            if not name:
                continue
            profile_orcid = short(au.get("orcid"))
            orcid = openalex_byline_orcid(ash)
            for oname, oid in openalex_org_pairs(ash):
                rows.append({"work_id": wid, "doi": w.get("doi") or "",
                             "title": w.get("title") or "", "year": w.get("publication_year") or "",
                             "venue": venue, "issn": "", "zone": "", "author_name": name,
                             "orcid": orcid, "org_name": oname, "org_id": short(oid),
                             "author_order": pos, "source_author_id": short(au.get("id")),
                             "raw_author_name": ash.get("raw_author_name") or "",
                             "profile_author_name": profile_name,
                             "profile_orcid": profile_orcid,
                             "is_first": "yes" if ash.get("author_position") == "first" or pos == 1 else "",
                             "is_corresponding": "yes" if ash.get("is_corresponding") is True else "",
                             "role_source": "OpenAlex authorships"})
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLS)
        wr.writeheader()
        wr.writerows(rows)
    print("wrote", out, "| rows", len(rows), "| papers", len(selected))

    plist = Path(args.papers_out) if args.papers_out else out.with_name(out.stem + "_papers.csv")
    with plist.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["work_id", "year", "title", "venue", "doi", "n_authors", "authors",
                     "candidate_routes", "known_name_match"])
        for w in sorted(selected, key=lambda x: (x.get("publication_year") or 0)):
            src = ((w.get("primary_location") or {}).get("source") or {})
            names = [name_for_signature(a, variants)
                     for a in (w.get("authorships") or [])]
            wid = short(w.get("id"))
            wr.writerow([wid, w.get("publication_year"),
                         w.get("title") or "", src.get("display_name") or "",
                         w.get("doi") or "", len(names), "; ".join(names),
                         "|".join(sorted(routes[wid])), int(name_hits[wid])])
    print("wrote", plist)
    if not selected:
        sys.exit("No candidates. Check the query coverage report and independent source lists.")
    seed_work = ' --seed-work "<verified_work_id>"' if args.across_affiliations else ""
    if seed_work:
        print("Candidate set only. Use an independently verified target publication as the anchor.")
    print("\nNext: python faction_query.py --source local --input", out,
          '--seed-name "<canonical>" --name-alias "<canonical>=<variant1>|<variant2>"' + seed_work,
          "--mode seed --min-collab 1 --out ./out")


if __name__ == "__main__":
    main()
