#!/usr/bin/env python3
"""Convert saved PubMed records to unverified authorship evidence without network requests."""

import argparse
import csv
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

from faction_query import clean_orcid, write_csv


TAG = re.compile(r"^([A-Z0-9]{2,4})[ \t]*-[ \t]*(.*)$")
DOI = re.compile(r"(10\.\d{4,9}/\S+)\s+\[doi\]", re.I)
RELATED_RECORDS = ("EFR", "EIN", "RIN", "ROF", "UIN", "UOF")


class PubMedText(HTMLParser):
    """Read the tagged text from a saved PubMed format page."""

    def __init__(self):
        super().__init__()
        self.in_pre = False
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self.in_pre = True
            self.parts.append("\n")
        elif self.in_pre and tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_pre = False

    def handle_data(self, data):
        if self.in_pre:
            self.parts.append(data)


def records(text: str):
    if text.lstrip().startswith("<"):
        page = PubMedText()
        page.feed(text)
        text = "".join(page.parts)

    fields = []
    for line in text.splitlines():
        match = TAG.match(line)
        if match:
            tag, value = match.groups()
            if tag == "PMID":
                if fields:
                    yield fields
                fields = []
            if fields or tag == "PMID":
                fields.append([tag, value.strip()])
        elif fields and line.startswith("      ") and line.strip():
            fields[-1][1] += " " + line.strip()
    if fields:
        yield fields


def affiliation(value: str) -> str:
    if re.match(r"^(?:these authors\s+)?contributed equally\b", value, re.I):
        return ""
    value = re.split(r"\b(?:Electronic address|E-?mail):", value, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\S+@\S+", "", value).strip(" ,;.")


def candidate_rows(fields):
    metadata = defaultdict(list)
    authors = []
    full_name_waiting_for_initials = False
    for tag, value in fields:
        metadata[tag].append(value)
        if tag == "AU" and full_name_waiting_for_initials:
            full_name_waiting_for_initials = False
        elif tag in {"FAU", "AU", "CN"}:
            authors.append({
                "name": value, "entity": "organization" if tag == "CN" else "person",
                "affiliations": [], "orcids": set(),
            })
            full_name_waiting_for_initials = tag == "FAU"
        elif tag == "AD" and authors:
            if name := affiliation(value):
                authors[-1]["affiliations"].append(name)
        elif tag == "AUID" and authors and value.startswith("ORCID:"):
            if orcid := clean_orcid(value):
                authors[-1]["orcids"].add(orcid)

    def first(tag: str) -> str:
        return next(iter(metadata[tag]), "")

    pmid = first("PMID")
    if not pmid.isascii() or not pmid.isdecimal():
        raise ValueError(f"Invalid PMID {pmid!r}")
    dois = {match[1].lower() for tag in ("AID", "LID") for value in metadata[tag]
            if (match := DOI.fullmatch(value))}
    year = (re.match(r"([1-9]\d{3})(?:\s|$)", first("DP")) if first("DP")
            else re.fullmatch(r"([1-9]\d{3})\d{4}", first("DEP")))
    languages = {"chi": "zh", "eng": "en"}
    issn = next((value for value in metadata["IS"] if value.endswith(" (Linking)")), first("IS"))
    common = {
        "result_type": "paper",
        "result_id": f"doi:{next(iter(dois))}" if len(dois) == 1 else f"pmid:{pmid}",
        "source": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "source_record_id": pmid,
        "result_subtype": " | ".join(metadata["PT"]),
        "status_as_recorded": " | ".join(f"{tag} {value}" for tag in RELATED_RECORDS for value in metadata[tag]),
        "title": first("TI"), "year": year[1] if year else "", "venue": first("JT") or first("TA"),
        "issn": issn.split(" ", 1)[0],
        "language": languages.get(first("LA"), "") if len(set(metadata["LA"])) == 1 else "",
    }
    if not authors:
        yield {**common, "entity_type": "unknown"}
    for position, author in enumerate(authors, 1):
        orcids = author["orcids"]
        for org_name in dict.fromkeys(author["affiliations"] or [""]):
            yield {
                **common, "position": position, "role": "author", "entity_type": author["entity"],
                "raw_name": author["name"], "org_name": org_name, "author_count": len(authors),
                "orcid": next(iter(orcids)) if len(orcids) == 1 and author["entity"] == "person" else "",
            }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True,
                        help="PubMed .nbib, tagged text, or saved PubMed format HTML (repeatable)")
    parser.add_argument("--out", type=Path, required=True, help="unverified evidence CSV")
    args = parser.parse_args(argv)
    template = Path(__file__).resolve().parents[1] / "assets" / "research_outputs_template.csv"
    with template.open(encoding="utf-8-sig", newline="") as handle:
        columns = next(csv.reader(handle))

    rows = []
    for path in args.input:
        try:
            batch = [row for record in records(path.read_text(encoding="utf-8-sig"))
                     for row in candidate_rows(record)]
        except (OSError, ValueError) as exc:
            parser.error(f"{path}: {exc}")
        if not batch:
            parser.error(f"No tagged PubMed records in {path}; save as PubMed format or Citation Manager .nbib")
        rows.extend(batch)
        print(f"{path.name}: {len({row['source_record_id'] for row in batch})} PMIDs")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, rows, columns)
    print(f"Wrote {len(rows)} unverified evidence rows for {len({row['source_record_id'] for row in rows})} PMIDs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
