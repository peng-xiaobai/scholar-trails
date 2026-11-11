#!/usr/bin/env python3
"""Convert local RIS exports into publication candidates without network requests."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

from faction_query import write_csv


COLUMNS = ["source", "input_file", "record_number", "complete_record", "source_record_id",
           "doi", "title", "year", "venue", "type", "volume", "issue", "start_page", "end_page",
           "authors", "url"]
TAG = re.compile(r"^([A-Z0-9]{2})[ \t]+-[ \t]*(.*)$")


def ris_records(lines):
    record = None
    previous = ""
    for line in lines:
        match = TAG.match(line.rstrip("\r\n"))
        if match:
            tag, value = match.groups()
            if tag == "TY":
                if record is not None:
                    yield record, False
                record = defaultdict(list)
            if record is None:
                continue
            if tag == "ER":
                yield record, True
                record = None
                previous = ""
                continue
            record[tag].append(value.strip())
            previous = tag
        elif record is not None and previous and line.strip():
            record[previous][-1] += " " + line.strip()
    if record is not None:
        yield record, False


def candidate(record):
    def first(*tags):
        return next((value for tag in tags for value in record.get(tag, ()) if value), "")

    doi = re.sub(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", unquote(first("DO")), flags=re.I)
    year = re.match(r"[1-9]\d{3}\b", first("PY", "Y1", "DA"))
    return {
        "source_record_id": first("AN", "ID"),
        "doi": doi.lower() if re.fullmatch(r"10\.\d{4,9}/\S+", doi) else "",
        "title": first("TI", "T1", "CT", "BT"), "year": year[0] if year else "",
        "venue": first("JF", "JO", "T2", "J2", "JA"), "type": first("TY"),
        "volume": first("VL"), "issue": first("IS"), "start_page": first("SP"), "end_page": first("EP"),
        "authors": json.dumps(record.get("AU") or record.get("A1") or [], ensure_ascii=False),
        "url": first("UR"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True, help="RIS batch (repeatable)")
    parser.add_argument("--source", required=True, help="database name for these export batches")
    parser.add_argument("--encoding", default="utf-8-sig", help="encoding of the input files")
    parser.add_argument("--out", type=Path, required=True, help="candidate CSV")
    args = parser.parse_args(argv)
    rows = []
    for path in args.input:
        with path.open(encoding=args.encoding) as handle:
            records = list(ris_records(handle))
        if not records:
            parser.error(f"No RIS records in {path}")
        rows.extend({"source": args.source, "input_file": path.name, "record_number": i,
                     "complete_record": int(complete), **candidate(record)}
                    for i, (record, complete) in enumerate(records, 1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, rows, COLUMNS)
    incomplete = sum(not row["complete_record"] for row in rows)
    print(f"Imported {len(rows)} candidates from {len(args.input)} batches. Incomplete RIS records: {incomplete}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
