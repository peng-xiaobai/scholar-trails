#!/usr/bin/env python3
"""Rank verified researchers by topic output count and audited portfolio share."""

import argparse
import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from faction_query import write_csv
from research_outputs import load_table, result_key


CONTRIBUTOR_ROLES = {
    "paper": {"author"},
    "patent": {"inventor"},
    "software": {"developer", "copyright_holder"},
}
FIELDS = [
    "rank", "selection", "person_id", "name", "topic_outputs", "verified_outputs",
    "pending_topic_outputs", "topic_share", "bibliography_sources",
    "topic_affiliations", "representative_outputs",
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="verified evidence with topic_status and topic_evidence")
    parser.add_argument("--out", type=Path, required=True, help="output CSV")
    parser.add_argument("--from-year", type=int, required=True)
    parser.add_argument("--to-year", type=int, required=True)
    parser.add_argument("--result-type", choices=CONTRIBUTOR_ROLES, default="paper")
    parser.add_argument("--bibliographies", type=Path, help="optional audited person_id,source CSV")
    parser.add_argument("--limit", type=int, default=10, help="maximum count-ranked researchers")
    parser.add_argument("--focused-limit", type=int, default=3, help="additional researchers ranked by topic share")
    args = parser.parse_args(argv)
    if not 1000 <= args.from_year <= args.to_year <= 9999:
        parser.error("year range must be ordered and use four-digit years")
    if args.limit < 1 or args.focused_limit < 0:
        parser.error("--limit must be positive and --focused-limit must be nonnegative")

    required = {"result_type", "result_id", "source", "year", "role", "entity_type", "person_id",
                "canonical_name", "identity_source", "topic_status", "topic_evidence"}
    by_work = defaultdict(list)
    for row in load_table(args.input, required):
        if row["result_type"] == args.result_type:
            by_work[result_key(row)[1]].append(row)

    names = {}
    works = {}
    portfolios = defaultdict(set)
    affiliations = defaultdict(set)
    for identifier, rows in by_work.items():
        years = {int(row["year"]) for row in rows if row["year"].isdecimal()}
        if not any(args.from_year <= year <= args.to_year for year in years):
            continue
        if len(years) != 1:
            raise ValueError(f"Conflicting years on {identifier}")
        judgments = {row["topic_status"] for row in rows} - {"", "pending"}
        if not judgments <= {"matched", "outside_topic"} or len(judgments) > 1:
            raise ValueError(f"Invalid or conflicting topic judgments on {identifier}")
        topic = next(iter(judgments), "pending")
        evidence = next((row["topic_evidence"] for row in rows
                         if row["topic_status"] == topic and row["topic_evidence"]), "")
        if topic == "matched" and not evidence:
            raise ValueError(f"Missing topic evidence on {identifier}")
        works[identifier] = {
            "result_id": identifier, "year": next(iter(years)), "topic_status": topic,
            "title": next((row["title"] for row in rows if row.get("title")), ""),
            "source": next((row["source"] for row in rows if row["source"]), ""),
            "topic_evidence": evidence,
        }
        for row in rows:
            person = row["person_id"]
            name = row["canonical_name"]
            if (row["role"] not in CONTRIBUTOR_ROLES[args.result_type] or row["entity_type"] != "person"
                    or not all((person, name, row["identity_source"], row["source"]))):
                continue
            if names.setdefault(person, name) != name:
                raise ValueError(f"Conflicting names on {person}")
            portfolios[person].add(identifier)
            if topic == "matched" and row.get("org_name"):
                affiliations[person].add(row["org_name"])

    audited = defaultdict(set)
    if args.bibliographies:
        for row in load_table(args.bibliographies, {"person_id", "source"}):
            if not row["person_id"] or not row["source"]:
                raise ValueError("Audited bibliographies need both person_id and source")
            audited[row["person_id"]].add(row["source"])

    ranked = []
    for person, ids in portfolios.items():
        matched = [works[identifier] for identifier in ids if works[identifier]["topic_status"] == "matched"]
        if len(matched) < 2:
            continue
        pending = sum(works[identifier]["topic_status"] == "pending" for identifier in ids)
        share = Fraction(len(matched), len(ids)) if audited[person] and not pending else None
        representatives = sorted(matched, key=lambda work: (-work["year"], work["result_id"]))[:3]
        ranked.append({
            "person_id": person, "name": names[person], "topic_outputs": len(matched),
            "verified_outputs": len(ids), "pending_topic_outputs": pending,
            "topic_share": f"{float(share):.1%}" if share is not None else "",
            "bibliography_sources": " | ".join(sorted(audited[person])),
            "topic_affiliations": " | ".join(sorted(affiliations[person])),
            "representative_outputs": json.dumps(representatives, ensure_ascii=False),
            "share": share,
        })

    ranked.sort(key=lambda row: (-row["topic_outputs"], row["name"].casefold(), row["person_id"]))
    main_list = ranked[:args.limit]
    focused = [row for row in ranked[args.limit:]
               if row["topic_outputs"] >= 3 and row["share"] is not None and row["share"] >= Fraction(1, 2)]
    focused.sort(key=lambda row: (-row["share"], -row["topic_outputs"], row["name"].casefold(), row["person_id"]))
    output = [{**row, "rank": i, "selection": selection}
              for selection, group in (("output_count", main_list), ("topic_share", focused[:args.focused_limit]))
              for i, row in enumerate(group, 1)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, output, FIELDS)
    print(f"Wrote {len(output)} researchers to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
