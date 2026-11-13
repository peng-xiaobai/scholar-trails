#!/usr/bin/env python3
"""Find affiliation evidence for missing author positions without changing the evidence ledger."""

import argparse
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from collect_crossref import API, FIELDS, author_name, fetch_query, get_message
from faction_query import clean_orcid, norm_name, openalex_org_pairs, read_csv, verified_affiliation, write_csv
from research_outputs import result_key


COLUMNS = ["work_id", "author_order", "author_name", "evidence_type", "evidence_work_id",
           "evidence_year", "org_name", "identity_basis", "source", "search_terms"]


def name_keys(*names):
    keys = {norm_name(name) for name in names} - {""}
    return keys | {" ".join(reversed(key.split())) for key in keys}


def recheck(gaps, evidence, online=False, related_evidence=(), *, openalex_byline=False):
    by_position, by_person, by_work = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in evidence:
        if row["result_type"] != "paper" or row["role"] != "author":
            continue
        _, work = result_key(row)
        row = {**row, "work_id": work}
        by_work[work].append(row)
        by_position[work, row.get("position", "")].append(row)
        if row.get("person_id"):
            by_person[row["person_id"]].append(row)

    # IDs may be local to a ledger. Link them through a shared, matching byline.
    for ledger in related_evidence:
        anchors = defaultdict(set)
        papers = []
        for row in ledger:
            if row["result_type"] != "paper" or row["role"] != "author" or not row.get("person_id"):
                continue
            _, work = result_key(row)
            papers.append({**row, "work_id": work})
            position = row.get("position", "")
            if not position.isdecimal() or int(position) < 1:
                continue
            keys = name_keys(row["raw_name"])
            orcid = clean_orcid(row.get("orcid"))
            for known in by_position[work, position]:
                known_orcid = clean_orcid(known.get("orcid"))
                if orcid and known_orcid and orcid != known_orcid:
                    continue
                matches = (orcid and orcid == known_orcid) or keys & name_keys(known["raw_name"])
                if known.get("person_id") and matches:
                    anchors[row["person_id"]].add(known["person_id"])
        for row in papers:
            matched = anchors[row["person_id"]]
            if len(matched) == 1:
                by_person[next(iter(matched))].append(row)

    @lru_cache(maxsize=None)
    def original(doi):
        if not doi:
            return {}
        try:
            return get_message(f"{API}/{quote(doi, safe='/')}", {})
        except (OSError, ValueError, KeyError) as exc:
            print(f"Crossref DOI lookup incomplete for {doi}: {exc}")
            return {}

    @lru_cache(maxsize=None)
    def indexed_byline(doi):
        url = f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='/')}"
        try:
            with urlopen(url, timeout=15) as response:
                item = json.load(response)
        except (OSError, ValueError) as exc:
            print(f"OpenAlex byline lookup incomplete for {doi}: {exc}")
            return url, []
        if (item.get("doi") or "").lower() != f"https://doi.org/{doi.lower()}":
            return url, []
        return url, item.get("authorships") or []

    @lru_cache(maxsize=None)
    def related(name, orcid):
        query = {"filter": "orcid:" + orcid} if orcid else {"query.author": name}
        items, audit = fetch_query(query, 8, FIELDS + ",title")
        if audit["status"] not in {"exhausted", "max_works"}:
            print(f"Crossref author lookup incomplete for {name}: {audit['status']}")
        return items

    output = []
    for gap in gaps:
        work = gap["work_id"]
        position = str(gap.get("author_order") or "")
        signature = by_position[work, position]
        name = gap.get("author_name") or ""
        doi = gap.get("doi") or ""
        title = gap.get("title") or ""
        base = {"work_id": work, "author_order": position, "author_name": name}
        raw_name = next((row["raw_name"] for row in signature), name)
        output.append({
            **base, "evidence_type": "original_lookup", "evidence_work_id": work,
            "source": f"https://doi.org/{doi}" if doi else gap.get("sources", ""),
            "search_terms": " ".join(f'"{part}"' for part in (title or doi, raw_name) if part) + " PDF affiliation",
        })
        keys = name_keys(*(row["raw_name"] for row in signature)) or name_keys(name)
        identities = {row.get("person_id") for row in signature if row.get("person_id")}
        same_person = by_person[next(iter(identities))] if len(identities) == 1 else []
        orcids = {clean_orcid(row.get("orcid")) for row in signature + same_person} - {""}
        orcid = next(iter(orcids)) if len(orcids) == 1 else ""
        original_units = [row for row in same_person if row["work_id"] == work
                          and row.get("position") == position and row.get("org_name")
                          and row.get("affiliation_basis") != "other"
                          and row not in signature]
        if original_units:
            verified_units = [row for row in original_units if verified_affiliation(row)]
            output.extend({**base, "evidence_type": "original_evidence" if row in verified_units
                           else "original_candidate", "evidence_work_id": work,
                           "org_name": row["org_name"], "evidence_year": row.get("year", ""),
                           "identity_basis": "shared_work_and_position", "source": row["source"]}
                          for row in original_units)
            if verified_units:
                continue

        def crossref_units(item, author, kind, basis):
            date = ((item.get("published") or {}).get("date-parts") or [[]])[0]
            found_doi = item["DOI"].lower()
            return [{**base, "evidence_type": kind, "evidence_work_id": "doi:" + found_doi,
                     "evidence_year": date[0] if date else "", "org_name": org["name"],
                     "identity_basis": basis, "source": "https://doi.org/" + found_doi}
                    for org in author.get("affiliation") or [] if org.get("name")]

        if online and doi and position.isdecimal() and int(position) > 0:
            item = original(doi)
            authors = item.get("author") or []
            if (item.get("DOI", "").lower() == doi.lower() and int(position) <= len(authors)):
                author = authors[int(position) - 1]
                observed_orcid = clean_orcid(author.get("ORCID"))
                name_matches = norm_name(author_name(author)) in keys
                if (not keys or name_matches or (orcid and observed_orcid == orcid)) and not (
                    orcid and observed_orcid and orcid != observed_orcid
                ):
                    basis = "doi_position_name_or_orcid" if keys else "doi_position_needs_verification"
                    units = crossref_units(item, author, "original_metadata", basis)
                    if units:
                        output.extend(units)
                        continue

        if openalex_byline and doi and keys and position.isdecimal() and int(position) > 0:
            source, authors = indexed_byline(doi)
            if int(position) <= len(authors):
                author = authors[int(position) - 1]
                if norm_name(author.get("raw_author_name")) in keys:
                    units = [org for org, _ in openalex_org_pairs(author, signed_only=True) if org]
                    output.extend({**base, "evidence_type": "original_byline_candidate", "evidence_work_id": work,
                                   "evidence_year": gap.get("year", ""), "org_name": org, "source": source,
                                   "identity_basis": "doi_position_raw_author_name"} for org in units)
                    if units:
                        continue

        if not name:
            continue
        other_units = {}
        for row in sorted(same_person, key=lambda row: row.get("year", ""), reverse=True):
            unit = row.get("org_name")
            if row["work_id"] != work and unit:
                other_units.setdefault(unit, {
                    **base, "evidence_type": "other_publication" if verified_affiliation(row)
                    else "other_publication_candidate", "evidence_work_id": row["work_id"],
                    "evidence_year": row.get("year", ""), "org_name": unit,
                    "identity_basis": "verified_person_id", "source": row["source"],
                })
        output.extend(other_units.values())
        if other_units:
            continue

        collaborator = next((row["raw_name"] for row in by_work[work] if row.get("person_id")
                             and row["person_id"] not in identities
                             and norm_name(row["raw_name"]) not in keys), "")
        output.append({
            **base, "evidence_type": "author_lookup",
            "source": f"https://orcid.org/{orcid}" if orcid else "",
            "search_terms": " ".join(f'"{part}"' for part in (name, collaborator) if part) + " affiliation",
        })
        if online:
            for item in related(raw_name, orcid):
                if "doi:" + item["DOI"].lower() == work:
                    continue
                for author in item.get("author") or []:
                    observed_orcid = clean_orcid(author.get("ORCID"))
                    if orcid and observed_orcid != orcid:
                        continue
                    if not orcid and norm_name(author_name(author)) not in keys:
                        continue
                    output.extend(crossref_units(
                        item, author, "other_publication_candidate",
                        "orcid" if orcid else "name_needs_verification",
                    ))
    return list({tuple(row.get(key, "") for key in COLUMNS): row for row in output}.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gaps", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--related-evidence", type=Path, action="append", default=[],
                        help="another evidence ledger with shared bylines (repeatable)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--online", action="store_true", help="query public Crossref metadata")
    parser.add_argument("--openalex-byline", action="store_true",
                        help="check exact DOI records for original per-author affiliation strings")
    args = parser.parse_args()
    rows = recheck(read_csv(args.gaps), read_csv(args.evidence), args.online,
                   (read_csv(path) for path in args.related_evidence), openalex_byline=args.openalex_byline)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, rows, COLUMNS)
    print(f"Affiliation recheck: {len(rows)} rows.")


if __name__ == "__main__":
    main()
