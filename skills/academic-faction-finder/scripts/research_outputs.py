#!/usr/bin/env python3
"""Reconcile verified research outputs and count collaborations by role."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from faction_query import main as build_network
from faction_query import (
    LEAD_ROLES, ROLE_FIELDS, clean_orcid, norm_name, norm_text, parse_name_alias,
    read_csv, role_flag, role_status, write_csv,
)


ROLES = {
    "paper": {"author"},
    "patent": {"inventor", "applicant", "patent_holder"},
    "software": {"developer", "copyright_holder"},
}
PAIR_ROLES = {"author", "inventor", "developer", "copyright_holder"}
PAPER_COLUMNS = ["work_id", "doi", "title", "year", "venue", "issn", "zone", "author_name",
                 "author_order", "org_name", "org_id", "orcid",
                 "verified_person_id", "verified_name", "identity_source",
                 "is_first", "is_corresponding", "role_source"]
PAPER_LIST_COLUMNS = ["year", "authors", "title", "doi", "is_first", "is_corresponding", "sources"]


def result_key(row):
    kind, identifier = row["result_type"], row["result_id"]
    if kind not in ROLES or not identifier:
        raise ValueError("Each row needs a result_type (paper/patent/software) and result_id")
    if kind == "paper":
        lower = unquote(identifier).lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if lower.startswith(prefix):
                lower = lower.removeprefix(prefix)
                break
        if lower.startswith("10.") and "/" in lower:
            identifier = "doi:" + lower
    return kind, identifier


def load_table(path, required):
    rows = [{k: v.strip() for k, v in row.items()} for row in read_csv(path)]
    if not rows or not required <= rows[0].keys():
        raise ValueError(f"{path} needs data and columns {', '.join(sorted(required))}")
    return rows


def paper_list_entry(group, identifier, target, name_key):
    """Build a citation from reconciled paper and byline evidence."""
    years = {row["year"] for row in group if re.fullmatch(r"[1-9][0-9]{3}", row.get("year", ""))}
    titles = {norm_text(row["title"]): row["title"] for row in group if row.get("title")}
    author_records = defaultdict(list)
    target_rows = []
    for row in group:
        if row["role"] == "author":
            author_records[row["source"], row.get("source_record_id", "")].append(row)
            if row["person_id"] == target:
                target_rows.append(row)

    complete_bylines = {}
    for record in author_records.values():
        counts = {row["author_count"] for row in record if row.get("author_count")}
        if len(counts) != 1:
            continue
        count = next(iter(counts))
        positions = defaultdict(set)
        for row in record:
            positions[int(row["position"])].add(row["raw_name"])
        if (count != str(len(positions)) or max(positions) != len(positions)
                or any(len(spellings) != 1 for spellings in positions.values())):
            continue
        ordered = [next(iter(positions[pos])) for pos in sorted(positions)]
        keys = tuple(name_key(name) for name in ordered)
        complete_bylines.setdefault(keys, ordered)

    roles = {}
    for field in ROLE_FIELDS:
        flags = {role_flag(row.get(field)) for row in target_rows} - {None}
        if field == "is_first" and not flags and target_rows[0]["position"] == "1":
            flags.add("yes")
        status = role_status(flags)
        roles[field] = status if status in LEAD_ROLES | {"no"} else ""
    doi = identifier[4:] if identifier.startswith("doi:") else ""
    return {
        "year": next(iter(years)) if len(years) == 1 else "",
        "authors": " | ".join(next(iter(complete_bylines.values()))) if len(complete_bylines) == 1 else "",
        "title": next(iter(titles.values())) if len(titles) == 1 else "",
        "doi": doi if re.fullmatch(r"10\.[0-9]{4,9}/\S+", doi) else "",
        **roles,
        "sources": " | ".join(sorted({row["source"] for row in group})),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="normalized evidence CSV")
    parser.add_argument("--target", required=True, help="verified person_id")
    parser.add_argument("--reference", type=Path, help="independent CSV with result_type,result_id,source")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--network", action="store_true", help="build the role-weighted paper network")
    parser.add_argument("--paper-list", action="store_true",
                        help="export a citation list for papers attributed to the target")
    parser.add_argument("--alias-map", help="institution aliases CSV for the paper network")
    parser.add_argument("--affiliation-history", help="CSV of sourced affiliation dates for the paper network")
    parser.add_argument("--name-alias", action="append", default=[],
                        help="verified name variants, Canonical=Variant A|Variant B (repeatable)")
    parser.add_argument("--network-min-papers", type=int, default=1,
                        help="verified paper count required before building the network")
    args = parser.parse_args(argv)
    if args.network_min_papers < 1:
        parser.error("--network-min-papers must be positive")
    name_aliases, _ = parse_name_alias(args.name_alias)

    def name_key(name: str) -> str:
        key = norm_name(name)
        return name_aliases.get(key, key)

    required = {"result_type", "result_id", "source", "raw_name", "role", "entity_type",
                "person_id", "canonical_name", "identity_source"}
    rows = load_table(args.input, required)
    grouped = defaultdict(list)
    names = {}
    for row in rows:
        kind, identifier = result_key(row)
        row["result_id"] = identifier
        role = row["role"]
        entity_type = row["entity_type"]
        person = row["person_id"]
        if (not row["source"] or (role and role not in ROLES[kind])
                or entity_type not in {"person", "organization", "unknown"}
                or bool(role) != bool(row["raw_name"])):
            raise ValueError(f"Invalid source, role or contributor on {identifier}")
        if person or row["canonical_name"] or row["identity_source"]:
            if not (entity_type == "person" and role and person
                    and row["canonical_name"] and row["identity_source"]):
                raise ValueError(f"Incomplete personal identity evidence on {identifier}")
            if names.setdefault(person, row["canonical_name"]) != row["canonical_name"]:
                raise ValueError(f"Conflicting canonical names for {person}")
        position = row.get("position", "")
        if kind == "paper" and role == "author" and (not position.isdecimal() or int(position) < 1):
            raise ValueError(f"Paper authors need an exact 1-based position on {identifier}")
        if position.isdecimal():
            row["position"] = str(int(position))
        grouped[kind, identifier].append(row)

    results, paper_rows, paper_list = [], [], []
    pair_evidence = defaultdict(set)
    counts = Counter(dict.fromkeys((
        "paper", "patent", "software", "paper_pending", "patent_pending", "software_pending",
        "scie_papers", "chinese_language_papers", "scie_and_chinese_language_papers",
        "index_unverified_papers", "chinese_journal_papers", "scie_and_chinese_journal_papers",
    ), 0))
    statuses = {}
    for (kind, identifier), group in sorted(grouped.items()):
        people_by_role = defaultdict(set)
        people_by_record = defaultdict(set)
        positions = {}
        person_positions = {}
        for row in group:
            person = row["person_id"]
            role = row["role"]
            position = row.get("position", "")
            if person:
                people_by_role[role].add(person)
                people_by_record[role, row["source"], row.get("source_record_id", "")].add(person)
                if role == "author":
                    if (positions.setdefault(position, person) != person
                            or person_positions.setdefault(person, position) != position):
                        raise ValueError(f"Conflicting verified author positions on {identifier}")
        target_roles = {role for role, people in people_by_role.items() if args.target in people}
        statuses[kind, identifier] = status = "attributed" if target_roles else "attribution_pending"
        pending_people = sum(row["entity_type"] == "person" and not row["person_id"] for row in group)
        if any(row.get("index_status", "") not in {"", "unverified", "scie", "not_scie"}
               for row in group):
            raise ValueError(f"Invalid index_status on {identifier}")
        index_statuses = {row.get("index_status") for row in group} & {"scie", "not_scie"}
        if (len(index_statuses) > 1
                or any(row.get("index_status") in index_statuses and not row.get("index_source")
                       for row in group)):
            raise ValueError(f"Conflicting or unsourced SCIE status on {identifier}")
        index = next(iter(index_statuses), "unverified") if kind == "paper" else ""
        journal_statuses = {row.get("chinese_journal") for row in group} & {"yes", "no"}
        if (len(journal_statuses) > 1
                or any(row.get("chinese_journal") in journal_statuses
                       and not row.get("chinese_journal_source") for row in group)):
            raise ValueError(f"Conflicting or unsourced Chinese journal status on {identifier}")
        chinese_journal = next(iter(journal_statuses), "unverified") if kind == "paper" else ""
        languages = {row.get("language", "").lower() for row in group} - {""}
        chinese = "zh" in languages
        metadata = {key: next((row[key] for row in group if row.get(key)), "")
                    for key in ("title", "year", "venue", "issn", "zone")}
        results.append({
            "result_type": kind, "result_id": identifier, "status": status,
            "title": metadata["title"], "year": metadata["year"],
            "target_roles": "|".join(sorted(target_roles)), "index_status": index,
            "index_sources": " | ".join(sorted({row["index_source"] for row in group if row.get("index_source")})),
            "chinese_journal": chinese_journal,
            "chinese_journal_sources": " | ".join(sorted({row["chinese_journal_source"] for row in group
                                                          if row.get("chinese_journal_source")})),
            "family_ids": "|".join(sorted({row["family_id"] for row in group if row.get("family_id")})),
            "record_ids": "|".join(sorted({row["source_record_id"] for row in group
                                            if row.get("source_record_id")})),
            "languages": "|".join(sorted(languages)), "pending_person_rows": pending_people,
            "sources": " | ".join(sorted({row["source"] for row in group})),
        })
        if not target_roles:
            counts[kind + "_pending"] += 1
            continue
        counts[kind] += 1
        if kind != "paper":
            counts.update(kind + "_" + role for role in target_roles)
        if kind == "paper":
            if args.paper_list:
                paper_list.append(paper_list_entry(group, identifier, args.target, name_key))
            counts["scie_papers"] += index == "scie"
            counts["index_unverified_papers"] += index == "unverified"
            counts["chinese_language_papers"] += chinese
            counts["scie_and_chinese_language_papers"] += chinese and index == "scie"
            counts["chinese_journal_papers"] += chinese_journal == "yes"
            counts["scie_and_chinese_journal_papers"] += chinese_journal == "yes" and index == "scie"
            # Use a single aligned byline; leave alternate observed spellings in the evidence ledger.
            by_position = defaultdict(list)
            for row in group:
                if row["role"] == "author" and row["entity_type"] == "person":
                    by_position[row["position"]].append(row)
            for position, signatures in sorted(by_position.items(), key=lambda item: int(item[0])):
                selected = next((row for row in signatures if row["person_id"]), signatures[0])
                key = name_key(selected["raw_name"])
                orcid = clean_orcid(selected.get("orcid"))
                aligned = [row for row in signatures
                           if (selected["person_id"] and selected["person_id"] == row["person_id"])
                           or (orcid and orcid == clean_orcid(row.get("orcid")))
                           or name_key(row["raw_name"]) == key]
                for row in aligned:
                    paper_rows.append({
                        **row, **metadata, "work_id": identifier,
                        "doi": identifier[4:] if identifier.startswith("doi:") else "",
                        "author_name": selected["raw_name"], "author_order": position,
                        "verified_person_id": selected["person_id"], "verified_name": selected["canonical_name"],
                        "identity_source": selected["identity_source"],
                        "role_source": row.get("role_source") or row["source"],
                    })
        for (role, _, _), people in people_by_record.items():
            if role in PAIR_ROLES and args.target in people:
                for other in people - {args.target}:
                    pair_evidence[role, other].add(identifier)

    relations = [{
        "role": role, "target_id": args.target, "target_name": names[args.target],
        "collaborator_id": other, "collaborator_name": names[other], "count": len(identifiers),
        "result_ids": " | ".join(sorted(identifiers)),
    } for (role, other), identifiers in sorted(pair_evidence.items(),
                                               key=lambda item: (item[0][0], -len(item[1]), item[0][1]))]
    reference_rows = []
    if args.reference:
        for row in load_table(args.reference, {"result_type", "result_id", "source"}):
            kind, identifier = result_key(row)
            if not row["source"]:
                raise ValueError(f"Missing reference source for {identifier}")
            reference_rows.append({"result_type": kind, "result_id": identifier,
                                   "source": row["source"],
                                   "status": statuses.get((kind, identifier), "missing_from_input")})
        reference_rows = list({tuple(row.values()): row for row in reference_rows}.values())

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "output_evidence.csv", rows, list(rows[0]))
    write_csv(args.out / "research_outputs.csv",
              [row for row in results if row["result_type"] != "paper"], list(results[0]))
    write_csv(args.out / "paper_authorship.csv", paper_rows, PAPER_COLUMNS)
    if args.paper_list:
        paper_list.sort(key=lambda row: (
            not any(row[field] in LEAD_ROLES for field in ROLE_FIELDS),
            -int(row["year"] or 0), norm_text(row["title"]), row["doi"],
        ))
        write_csv(args.out / "paper_list.csv", paper_list, PAPER_LIST_COLUMNS)
    write_csv(args.out / "typed_collaborations.csv", relations,
              ["role", "target_id", "target_name", "collaborator_id", "collaborator_name", "count", "result_ids"])
    if args.reference:
        write_csv(args.out / "output_reference_coverage.csv", reference_rows,
                  ["result_type", "result_id", "source", "status"])
    reference_counts = Counter(row["status"] for row in reference_rows)
    summary = {"target_id": args.target, "counts": dict(counts),
               "independent_list_status": (
                   "not_checked" if not args.reference else
                   "gaps_found" if any(row["status"] != "attributed" for row in reference_rows)
                   else "reference_list_reconciled"),
               "reference_counts": dict(reference_counts)}
    if args.paper_list:
        summary["paper_list"] = {"file": "paper_list.csv", "rows": len(paper_list)}
    try:
        if args.network:
            if counts["paper"] < args.network_min_papers:
                summary["paper_network"] = {"status": "below_minimum", "min_papers": args.network_min_papers}
            else:
                anchor = next(row for row in paper_rows if row["verified_person_id"] == args.target)
                network_dir = args.out / "paper_network"
                summary["paper_network"] = {"status": "error", "directory": str(network_dir)}
                alias_args = [option for spec in args.name_alias for option in ("--name-alias", spec)]
                if args.alias_map:
                    alias_args.extend(["--alias-map", args.alias_map])
                if args.affiliation_history:
                    alias_args.extend(["--affiliation-history", args.affiliation_history])
                build_network([
                    "--source", "local", "--input", str(args.out / "paper_authorship.csv"),
                    "--seed-name", names[args.target], "--seed-work",
                    f"{anchor['work_id']}@{anchor['author_order']}",
                    "--mode", "seed", "--community", "louvain", "--out", str(network_dir), *alias_args,
                ], quiet=True)
                summary["paper_network"]["status"] = "built"
    finally:
        (args.out / "output_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
