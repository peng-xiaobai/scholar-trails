#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
academic-faction-finder / faction_query.py

Query co-authorship factions from a scoped literature set.

Pipeline (always executed in this order, fully logged):
  1. parse query scope        (author / org / journal / zone / years)
  2. acquire records          (demo CSV, local long-table CSV, or OpenAlex API)
  3. disambiguate persons     (shared-affiliation rule, auditable)
  4. build co-author edges    (weight = number of jointly signed papers)
  5. identify peer groups and constrain membership by signed affiliations
  6. export                   (CSV + SQLite + self-contained HTML + log)

Core identity rule (as specified by the user):
  A person may carry multiple affiliations. If ANY affiliation of a new
  authorship record matches ANY affiliation previously seen for a same-name
  person, treat them as the same person.

Safeguards around that rule:
  - affiliation IDs / alias normalisation before comparison
  - ORCID is a strong identifier; conflicting ORCIDs are never merged
  - umbrella organisations listed in --ignore-orgs are excluded from evidence
  - every decision is written to merge_log.csv and the SQLite merge_log table
  - unusually large affiliation sets are flagged review_flag=1

Pure co-authorship only. No advisor/advisee inference, no interest analysis.

Usage:
  python faction_query.py --demo-out
  python faction_query.py --source demo --author "示例作者 A" --zone Q1 --min-collab 2
  python faction_query.py --source local --input my.csv --author "Example Author" --org "Example University"
  python faction_query.py --source openalex --author "Some Name" --org "Some Univ" \
      --journal "1234-5678" --zone Q1 --zone-map zones.csv --api-key KEY

Python 3.9+. Louvain uses networkx when available.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime
from itertools import combinations
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ASSETS = SKILL_DIR / "assets"
SCHEMA_PATH = SCRIPT_DIR / "schema.sql"
DEMO_PATH = ASSETS / "demo_authorship.csv"
OA_BASE = "https://api.openalex.org"

LOG = logging.getLogger("faction")
PALETTE = [
    "#56d6b1", "#f5bd6b", "#a5b8fa", "#ec9bc0", "#d5d77c",
    "#f39383", "#84c9e6", "#b0d792", "#d2aa92", "#b9b4dc",
]
ISOLATED_COLOR = "#a5b5b1"
AFFILIATION_PRIORITY = {"": 0, "same_work": 1, "paper": 2}


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------

def norm_text(value) -> str:
    s = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"\s+", " ", s)


def norm_name(value) -> str:
    s = norm_text(value)
    s = "".join("-" if unicodedata.category(c) == "Pd" else c for c in s)
    s = re.sub(r"[.,;:_'`/\\()\[\]-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_org_name(value) -> str:
    s = norm_text(value)
    s = "".join(c if c.isalnum() else " " for c in s)
    s = re.sub(r"\buniv\b", "university", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_orcid(value) -> str:
    m = re.search(r"(\d{4}-\d{4}-\d{4}-[\dxX]{4})", str(value or ""))
    return m.group(1).upper() if m else ""


def orcid_profile_url(orcids) -> str:
    ids = {clean_orcid(value) for value in orcids} - {""}
    if len(ids) != 1:
        return ""
    identifier = next(iter(ids))
    return "https://orcid.org/" + identifier if re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", identifier) else ""


ROLE_FIELDS = ("is_first", "is_corresponding")
LEAD_ROLES = {"yes", "sole", "shared"}


def role_flag(value):
    if isinstance(value, bool):
        return "yes" if value else "no"
    value = norm_text(value)
    if value in {"1", "yes", "true"}:
        return "yes"
    if value in {"0", "no", "false"}:
        return "no"
    if value in {"sole", "shared", "conflict"}:
        return value
    return None


def role_status(flags):
    if flags & {"sole", "shared"}:
        flags = flags - {"yes"}
    if len(flags) > 1:
        return "conflict"
    return next(iter(flags), "unknown")


def role_score(signature):
    roles = {signature.get(field) for field in ROLE_FIELDS}
    if roles & {"yes", "sole"}:
        return 3
    if "shared" in roles:
        return 2
    return 1


def authorship_role(signature):
    first, corresponding = (signature.get(field) for field in ROLE_FIELDS)
    if first in LEAD_ROLES and corresponding in LEAD_ROLES:
        return "first_and_corresponding"
    if first in LEAD_ROLES:
        return "first"
    if corresponding in LEAD_ROLES:
        return "corresponding"
    if first == corresponding == "no":
        return "ordinary"
    return "unconfirmed"


def graph_weight(edge, args):
    if getattr(args, "edge_weight", "role") == "role":
        return edge.get("role_weight", edge["n_papers"])
    return edge["n_papers"]


def split_issn(value) -> list[str]:
    return [x.strip().upper() for x in re.split(r"[|;,/\s]+", str(value or "")) if x.strip()]


def org_key(name, oid, aliases, *, allow_partial=True) -> str:
    oid = oa_short_id(oid).lower()
    if oid:
        key = "id:" + oid
        return aliases.get(key, key)
    n = norm_org_name(name)
    if not n:
        return ""
    if n in aliases:
        return aliases[n]
    parts = re.split(r"[,;，；]", str(name))
    if allow_partial and len(parts) > 1:
        keys = {aliases[part] for value in parts if (part := norm_org_name(value)) in aliases}
        if len(keys) == 1:
            return next(iter(keys))
    return "name:" + n


def load_alias_map(path, display_names=None) -> dict:
    out = {}
    if not path:
        return out
    if not Path(path).is_file():
        raise FileNotFoundError(f"Affiliation alias map not found: {path}")
    for row in read_csv(Path(path)):
        source_key = norm_text(row.get("from_key", ""))
        k = ("id:" + oa_short_id(source_key[3:]) if source_key.startswith("id:")
             else norm_org_name(source_key))
        v = norm_text(row.get("to_key", ""))
        if k and v:
            key = ("id:" + oa_short_id(v[3:]) if v.startswith("id:")
                   else "name:" + norm_org_name(v.removeprefix("name:")))
            if out.setdefault(k, key) != key:
                raise ValueError(f"Conflicting affiliation aliases for {k}")
            label = row.get("display_name", "").strip()
            if label and display_names is not None:
                if not row.get("source", "").strip():
                    raise ValueError(f"A canonical affiliation display name needs a source: {label}")
                if display_names.setdefault(key, label) != label:
                    raise ValueError(f"Conflicting affiliation display names for {key}")
    for key in list(out.values()):
        if key.startswith("name:"):
            out.setdefault(key[5:], key)
    return out


def link_org_ids(works: list[dict], aliases: dict) -> dict:
    observed = defaultdict(set)
    for work in works:
        for author in work["authors"].values():
            for name, oid in author["orgs"]:
                label = norm_org_name(name)
                if not (oid and label):
                    continue
                key = aliases.get(label, "name:" + label)
                if key.startswith("name:"):
                    observed[key].add(org_key("", oid, aliases))
    unique = {key: next(iter(ids)) for key, ids in observed.items() if len(ids) == 1}
    return {**{key[5:]: oid for key, oid in unique.items()},
            **{name: unique.get(key, key) for name, key in aliases.items()}}


def load_ignored(path) -> tuple[set, set]:
    keys, names = set(), set()
    if not path:
        return keys, names
    for row in read_csv(Path(path)):
        v = norm_text(row.get("value", ""))
        if not v:
            continue
        if v.startswith(("id:", "name:")):
            keys.add(v)
        else:
            names.add(norm_org_name(v))
    return keys, names


def read_csv(path: Path) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [{str(k).strip(): (v or "") for k, v in row.items() if k}
                for row in csv.DictReader(fh)]


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


# --------------------------------------------------------------------------
# stage 1-2: acquire records
# --------------------------------------------------------------------------

def oa_get(path: str, params: dict, api_key: str, retries: int = 3) -> dict:
    p = dict(params)
    if api_key:
        p["api_key"] = api_key
    url = OA_BASE + path + "?" + urllib.parse.urlencode(p)
    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "academic-faction-finder/1.0 (co-authorship research)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            hint = (" Cursor paging past page 1 requires a free API key; "
                    "the script falls back to page-based paging when no key is set."
                    if exc.code == 401 else "")
            last_error = RuntimeError(
                f"OpenAlex HTTP {exc.code}: {body}. "
                "Check the API key and the daily usage allowance." + hint
            )
            if exc.code in (401, 402, 403, 429):
                break
        except Exception as exc:  # network / timeout
            last_error = exc
        time.sleep(1.2 * (attempt + 1))
    raise last_error or RuntimeError("OpenAlex request failed")


def oa_short_id(value: str) -> str:
    return str(value or "").strip().rstrip("/").rsplit("/", 1)[-1]


def oa_lookup(path: str, term: str, select: str, api_key: str, n: int = 5) -> list[dict]:
    data = oa_get(path, {"search": term, "per-page": n, "select": select}, api_key)
    return data.get("results", []) or []


def openalex_org_pairs(authorship: dict, *, signed_only=False) -> list[tuple[str, str]]:
    pairs = {}
    for inst in authorship.get("institutions") or []:
        name = (inst.get("display_name") or "").strip()
        oid = inst.get("id") or inst.get("ror") or ""
        if name or oid:
            pairs[name, oid] = None
    ids = {oa_short_id(oid) for _, oid in pairs if oid}
    names = {norm_org_name(name) for name, _ in pairs}
    original = [label.strip() for label in authorship.get("raw_affiliation_strings") or []
                if label and label.strip()]
    raw = dict.fromkeys(original)
    mapped = set()
    for affil in authorship.get("affiliations") or []:
        label = affil.get("raw_affiliation_string")
        raw.setdefault(label)
        if any(oa_short_id(oid) in ids for oid in affil.get("institution_ids") or []):
            mapped.add(label)
    if signed_only:
        by_name = defaultdict(set)
        for name, oid in pairs:
            if name and oid:
                by_name[norm_org_name(name)].add(oid)
        signed = []
        for label in dict.fromkeys(original or raw):
            if label and label.strip():
                matches = by_name[norm_org_name(label)]
                signed.append((label.strip(), next(iter(matches)) if len(matches) == 1 else ""))
        return signed or [("", "")]
    for label in raw:
        if label and label.strip() and label not in mapped and norm_org_name(label) not in names:
            pairs[label.strip(), ""] = None
    return list(pairs) or [("", "")]


def openalex_byline_orcid(authorship: dict) -> str:
    author = authorship.get("author") or {}
    raw_orcid = clean_orcid(authorship.get("raw_orcid"))
    raw_name = norm_name(authorship.get("raw_author_name"))
    if raw_orcid or (raw_name and raw_name != norm_name(author.get("display_name"))):
        return raw_orcid
    return clean_orcid(author.get("orcid"))


def openalex_works_to_dicts(results: list[dict]) -> list[dict]:
    works = []
    for w in results:
        pl = w.get("primary_location") or {}
        src = pl.get("source") or {}
        issns = set()
        for v in [src.get("issn_l"), src.get("issn")]:
            if v:
                issns.add(str(v).upper())
        for v in (src.get("issns") or []):
            if v:
                issns.add(str(v).upper())
        venue = src.get("display_name") or ""
        authors = {}
        for pos, ash in enumerate(w.get("authorships") or [], 1):
            au = ash.get("author") or {}
            name = (ash.get("raw_author_name") or "").strip() or au.get("display_name") or ""
            nk = norm_name(name)
            if not nk:
                continue
            a = authors.setdefault((nk, pos), {
                "name": name, "orcid": set(), "orgs": {}, "order": pos, "actual_order": pos,
                "role_sources": {"OpenAlex authorships"},
            })
            a["indexed_orgs"] = openalex_org_pairs(ash)
            if ash.get("author_position") == "first":
                a["is_first"] = {"yes"}
            if ash.get("is_corresponding") is True:
                a["is_corresponding"] = {"yes"}
            orcid = openalex_byline_orcid(ash)
            if orcid:
                a["orcid"].add(orcid)
            for oname, oid in openalex_org_pairs(ash, signed_only=True):
                a["orgs"][oname, oid] = None
        works.append({
            "work_id": oa_short_id(w.get("id") or w.get("doi") or ""),
            "doi": w.get("doi") or "",
            "title": w.get("title") or "",
            "year": w.get("publication_year"),
            "venue": venue,
            "issns": issns,
            "zone": "",
            "authors": authors,
        })
    return works


def fetch_openalex(args, api_key: str, aliases: dict):
    filters = []

    # Resolve the institution first: it also disambiguates common personal names.
    # A college/department is usually NOT an OpenAlex institution, so --org may
    # fail to resolve; --affil-search covers those raw affiliation strings.
    inst_ids = [oa_short_id(x) for x in (args.org_id or [])]
    for term in (args.org or []):
        key = org_key(term, "", aliases)
        if re.fullmatch(r"id:i\d+", key):
            inst_ids.append(key[3:].upper())
            continue
        query = key[5:] if key.startswith("name:") else term
        try:
            cands = oa_lookup("/institutions", query,
                              "id,display_name,country_code", api_key, n=3)
        except Exception as exc:
            LOG.warning("Institution lookup failed for '%s': %s", term, exc)
            cands = []
        exact = {oa_short_id(c.get("id")) for c in cands
                 if c.get("id") and org_key(c.get("display_name"), "", aliases) == key}
        if len(exact) == 1:
            iid = next(iter(exact))
            inst_ids.append(iid)
            LOG.info("Institution '%s' -> %s", term, iid)
        else:
            LOG.warning("No unique OpenAlex institution match for '%s'; local filter only. "
                        "Use --org-id or --affil-search after checking the institution.", term)

    # Never silently bind a name to the first fuzzy hit. With an institution in
    # scope, restrict the /authors lookup to that institution and keep only exact
    # name matches. OpenAlex often splits one real person into several author IDs,
    # so all exact matches are OR-ed together instead of taking a single ID.
    author_ids = [oa_short_id(x) for x in (args.author_id or [])]
    for name in (args.author or []):
        lookup = {"search": name, "per-page": 100,
                  "select": "id,display_name,orcid,works_count,last_known_institutions"}
        if inst_ids:
            lookup["filter"] = "last_known_institutions.id:" + "|".join(dict.fromkeys(inst_ids))
        try:
            cands = oa_get("/authors", lookup, api_key).get("results", []) or []
        except Exception as exc:
            LOG.warning("Author lookup failed for '%s': %s", name, exc)
            continue
        if not cands:
            LOG.warning("No OpenAlex author found for '%s' in scope; skipped. "
                        "Consider --seed-name to keep the name as a seed only.", name)
            continue
        LOG.info("Author candidates for '%s': %s", name,
                 ", ".join(f"{c.get('display_name')} [{oa_short_id(c.get('id'))}]"
                           for c in cands[:5]))
        target = norm_name(name)
        exact = [c for c in cands if norm_name(c.get("display_name") or "") == target]
        if not exact:
            LOG.warning("No exact-name match for '%s' inside the institution scope", name)
        for c in exact:
            author_ids.append(oa_short_id(c.get("id")))
    if args.author and not any(author_ids):
        raise ValueError("No exact author match. Verify an author ID, ORCID or publication signature.")
    if author_ids:
        filters.append("authorships.author.id:" + "|".join(dict.fromkeys(author_ids)))

    if inst_ids:
        filters.append("authorships.institutions.id:" + "|".join(dict.fromkeys(inst_ids)))
        # keep the resolved ids for the local scope filter as well
        args.org_id = list(dict.fromkeys(list(args.org_id or []) + list(inst_ids)))

    if getattr(args, "affil_search", None):
        terms = [str(x).strip() for x in args.affil_search if str(x).strip()]
        if terms:
            filters.append("raw_affiliation_strings.search:" + "|".join(terms))
            LOG.info("Raw affiliation string scope: %s", " | ".join(terms))

    if args.source_id:
        filters.append("primary_location.source.id:" +
                       "|".join(oa_short_id(x) for x in args.source_id))
    if args.from_year:
        filters.append(f"from_publication_date:{args.from_year}-01-01")
    if args.to_year:
        filters.append(f"to_publication_date:{args.to_year}-12-31")

    topics = list(args.topic or [])
    if not topics and not filters:
        raise ValueError("OpenAlex mode needs --author, --org, --topic or --source-id "
                         "to avoid downloading the entire catalogue")
    if not topics:
        topics = [""]

    # Minimal field set by default: only author-related metadata is needed.
    # Title/DOI are content-ish metadata and are opt-in; primary_location is
    # fetched only when a journal or zone filter actually needs it.
    fields = ["id", "publication_year", "authorships"]
    if args.journal or args.zone or args.source_id:
        fields.append("primary_location")
    if args.with_titles:
        fields.extend(["doi", "title"])
    LOG.info("OpenAlex select fields: %s (title/doi omitted by default)",
             ",".join(fields))

    # Cursor paging past page 1 requires a free API key (OpenAlex HTTP 401
    # "API key required for cursor paging"). Without a key, fall back to plain
    # page-based paging, which is limited to ~10,000 results but is credential-free.
    use_cursor = bool(api_key)
    if not use_cursor:
        LOG.warning("No OpenAlex API key: cursor paging needs a key, falling back to "
                    "page-based paging (works for up to ~10,000 results).")
    all_works, seen = [], set()
    for topic in topics:
        params = {
            "select": ",".join(fields),
            "per-page": 100,
        }
        if filters:
            params["filter"] = ",".join(filters)
        if topic:
            params["search"] = topic
        page = 1
        if use_cursor:
            params["cursor"] = "*"
        while len(all_works) < args.max_works:
            if not use_cursor:
                params["page"] = page
            data = oa_get("/works", params, api_key)
            batch = data.get("results", []) or []
            if not batch:
                break
            for w in batch:
                wid = oa_short_id(w.get("id") or "")
                if wid and wid not in seen:
                    seen.add(wid)
                    all_works.append(w)
            if len(all_works) >= args.max_works:
                break
            if use_cursor:
                cursor = (data.get("meta") or {}).get("next_cursor")
                if not cursor:
                    break
                params["cursor"] = cursor
            else:
                if len(batch) < 100:
                    break
                page += 1
            time.sleep(0.15)
        LOG.info("OpenAlex topic '%s': cumulative works = %d (paging=%s)",
                 topic or "(filter only)", len(all_works),
                 "cursor" if use_cursor else "page")
    truncated = len(all_works) >= args.max_works
    if truncated:
        LOG.warning("Hit --max-works=%d: the result set is TRUNCATED, not the complete "
                    "journal set. Increase --max-works or split by year / journal.",
                    args.max_works)
    return openalex_works_to_dicts(all_works[:args.max_works]), truncated


def affiliation_priority(row):
    basis = row.get("affiliation_basis", "")
    source = (urllib.parse.urlsplit(row.get("source", "")).hostname or "")
    source = source.removeprefix("www.").removeprefix("api.")
    if basis == "same_work":
        confirmation = (urllib.parse.urlsplit(row.get("affiliation_confirmation", "")).hostname or "")
        confirmation = confirmation.removeprefix("www.").removeprefix("api.")
        if not confirmation or confirmation == source or confirmation == "openalex.org":
            return -1
    elif source == "openalex.org":
        return -1
    return AFFILIATION_PRIORITY.get(basis, -1)


def verified_affiliation(row):
    return (row.get("affiliation_complete") == "yes" and bool(row.get("source"))
            and affiliation_priority(row) > 0)


def rows_to_works(rows: list[dict], *, require_verified_affiliations=True) -> list[dict]:
    works = {}
    for r in rows:
        wid = str(r.get("work_id") or "").strip()
        if not wid:
            continue
        w = works.setdefault(wid, {
            "work_id": wid,
            "doi": r.get("doi", ""),
            "title": r.get("title", ""),
            "year": int(r["year"]) if str(r.get("year", "")).isdigit() else None,
            "venue": r.get("venue", ""),
            "issns": set(split_issn(r.get("issn", ""))),
            "zone": str(r.get("zone", "") or "").strip(),
            "authors": {},
        })
        w["issns"].update(split_issn(r.get("issn", "")))
        name = str(r.get("author_name") or "").strip()
        nk = norm_name(name)
        if not nk:
            continue
        try:
            actual_order = int(r.get("author_order") or 0)
        except ValueError:
            actual_order = 0
        order = actual_order if actual_order > 0 else 999
        a = w["authors"].setdefault((nk, order), {
            "name": name, "orcid": set(), "orgs": {}, "order": order, "role_sources": set(),
        })
        if actual_order > 0:
            a["actual_order"] = actual_order
        for field in ROLE_FIELDS:
            flag = role_flag(r.get(field))
            if flag is not None:
                a.setdefault(field, set()).add(flag)
        if r.get("role_source"):
            a["role_sources"].add(r["role_source"].strip())
        verified = tuple((r.get(field) or "").strip() for field in
                         ("verified_person_id", "verified_name", "identity_source"))
        if any(verified):
            if not all(verified) or not str(r.get("author_order", "")).strip().isdecimal() or order < 1:
                raise ValueError(f"Incomplete verified signature for {wid}@{order}")
            if a.get("verified") and a["verified"][:2] != verified[:2]:
                raise ValueError(f"Conflicting verified signatures for {wid}@{order}")
            a["verified"] = verified
        if clean_orcid(r.get("orcid")):
            a["orcid"].add(clean_orcid(r.get("orcid")))
        oname = str(r.get("org_name") or "").strip()
        oid = str(r.get("org_id") or "").strip()
        if oname or oid:
            if require_verified_affiliations and not verified_affiliation(r):
                a.setdefault("indexed_orgs", set()).add((oname, oid))
            else:
                a["orgs"][(oname, oid)] = None
    return list(works.values())


def load_zone_map(path) -> dict:
    mapping = defaultdict(set)
    if not path:
        return mapping
    for row in read_csv(Path(path)):
        vals = {norm_text(row.get("zone", "")), norm_text(row.get("quartile", ""))}
        vals.discard("")
        if not vals:
            continue
        for issn in split_issn(row.get("issn", "")):
            mapping[issn].update(vals)
        vk = norm_org_name(row.get("venue", ""))
        if vk:
            mapping[vk].update(vals)
            mapping[norm_text(row.get("venue", ""))].update(vals)
    return mapping


def zones_for_work(work: dict, zone_map: dict) -> set:
    found = set()
    for issn in work["issns"]:
        found |= zone_map.get(issn, set())
    for key in (norm_org_name(work["venue"]), norm_text(work["venue"])):
        found |= zone_map.get(key, set())
    if not found and work.get("zone"):
        found.add(norm_text(work["zone"]))
    return {x for x in found if x}


def apply_scope(works: list[dict], args, zone_map: dict, aliases: dict) -> list[dict]:
    journal_issns, journal_names = set(), set()
    for term in (args.journal or []):
        t = str(term).strip()
        if re.fullmatch(r"\d{4}-\d{3}[\dxX]", t):
            journal_issns.add(t.upper())
        else:
            journal_names.add(norm_org_name(t))
    journal_names.discard("")
    org_terms = {norm_org_name(x) for x in (args.org or [])} - {""}
    org_keys = {org_key(x, "", aliases) for x in args.org or []}
    org_keys.update(org_key("", x, aliases) for x in args.org_id or [])
    org_keys.discard("")
    zone_terms = {norm_text(x) for x in (args.zone or [])} - {""}

    kept, reasons = [], Counter()
    for w in works:
        yr = w["year"]
        if args.from_year and (yr is None or yr < args.from_year):
            reasons["year"] += 1
            continue
        if args.to_year and (yr is None or yr > args.to_year):
            reasons["year"] += 1
            continue
        if journal_issns or journal_names:
            hit = bool(w["issns"] & journal_issns) or any(
                t in norm_org_name(w["venue"]) for t in journal_names
            )
            if not hit:
                reasons["journal"] += 1
                continue
        if zone_terms:
            wz = zones_for_work(w, zone_map)
            if not wz:
                reasons["zone_unknown"] += 1
                continue
            if not (wz & zone_terms):
                reasons["zone"] += 1
                continue
        if org_keys:
            orgs, keys = set(), set()
            for a in w["authors"].values():
                for oname, oid in (*a["orgs"], *a.get("indexed_orgs", ())):
                    orgs.add(norm_org_name(oname))
                    keys.add(org_key(oname, oid, aliases))
            hit = bool(keys & org_keys) or any(t in o for t in org_terms for o in orgs if o)
            if not hit:
                reasons["org"] += 1
                continue
        kept.append(w)
    if reasons:
        LOG.info("Scope filtering excluded: %s", dict(reasons))
    if zone_terms and reasons.get("zone_unknown"):
        LOG.warning("%d works had no zone information and were dropped. "
                    "Provide --zone-map for real data.", reasons["zone_unknown"])
    return kept


# --------------------------------------------------------------------------
# stage 3: disambiguation
# --------------------------------------------------------------------------

def works_to_rows(works: list[dict]) -> list[dict]:
    org_names = defaultdict(set)
    for work in works:
        for author in work["authors"].values():
            for name, oid in author["orgs"]:
                if name and oid:
                    org_names[org_key("", oid, {})].add(name)
    rows = []
    for w in works:
        for (nk, _), a in w["authors"].items():
            pairs = list(a["orgs"].keys()) or [("", "")]
            for oname, oid in pairs:
                if not oname and oid:
                    names = org_names[org_key("", oid, {})]
                    if len({norm_org_name(name) for name in names}) == 1:
                        oname = min(names)
                rows.append({
                    "work_id": w["work_id"],
                    "year": w["year"],
                    "author_name": a["name"],
                    "name_key": nk,
                    "orcid": sorted(a["orcid"])[0] if len(a["orcid"]) == 1 else "",
                    "orcid_conflict": len(a["orcid"]) > 1,
                    "org_name": oname,
                    "org_id": oid,
                    "order": a["order"],
                    "actual_order": a.get("actual_order"),
                    "is_first": a.get("is_first", set()),
                    "is_corresponding": a.get("is_corresponding", set()),
                    "role_sources": a.get("role_sources", set()),
                    "verified": a.get("verified"),
                })
    return rows


def parse_name_alias(specs) -> tuple[dict, dict]:
    """`--name-alias "Canonical=Variant A|Variant B"` -> (map, display names).

    OpenAlex and Chinese/English metadata often write one person several ways. The affiliation-overlap rule only groups
    identical name keys, so variants must be folded BEFORE disambiguation or the
    same scholar is counted as several unrelated people.
    """
    mapping, display = {}, {}
    for spec in specs or []:
        if "=" not in str(spec):
            LOG.warning("Ignoring malformed --name-alias %r (expected Canonical=Variant|Variant)", spec)
            continue
        canon, variants = str(spec).split("=", 1)
        ck = norm_name(canon)
        if not ck:
            continue
        display[ck] = canon.strip()
        for v in [canon, *variants.split("|" if "|" in variants else ",")]:
            vk = norm_name(v)
            if vk and mapping.setdefault(vk, ck) != ck:
                raise ValueError(f"Conflicting author aliases for {v.strip()}")
    return mapping, display


def resolve_entities(rows: list[dict], args, aliases: dict, ignored):
    ignored_keys, ignored_names = ignored
    ignored_keys = ignored_keys | {org_key(label, "", aliases) for label in ignored_names}
    namap, display_names = parse_name_alias(getattr(args, "name_alias", None))
    if namap:
        LOG.info("Name aliases loaded: %d spellings -> %d canonical names",
                 len(namap), len(set(namap.values())))
    instances = {}
    for r in rows:
        verified = r.get("verified")
        lookup_name = namap.get(r["name_key"], r["name_key"])
        nk = "verified:" + verified[0] if verified else lookup_name
        key = (r["work_id"], nk, r["order"])
        inst = instances.setdefault(key, {
            "work_id": r["work_id"], "year": r["year"],
            "name": display_names.get(nk, r["author_name"]),
            "raw_name": r["author_name"],
            "name_key": nk, "orcid": r["orcid"], "orcid_conflict": r["orcid_conflict"],
            "org_keys": set(), "org_names": set(), "org_pairs": set(), "signed_orgs": defaultdict(set),
            "org_display": set(), "order": r["order"],
            "verified": verified, "match_names": set(),
            "actual_order": r.get("actual_order"), "role_sources": set(),
            "is_first": set(), "is_corresponding": set(),
        })
        inst["actual_order"] = inst["actual_order"] or r.get("actual_order")
        inst["role_sources"].update(r.get("role_sources", ()))
        for field in ROLE_FIELDS:
            inst[field].update(r.get(field, ()))
        inst["match_names"].add(lookup_name)
        if verified:
            if inst["verified"][1] != verified[1]:
                raise ValueError(f"Conflicting verified names for {r['work_id']}@{r['order']}")
            canon = norm_name(verified[1])
            inst["match_names"].add(namap.get(canon, canon))
            if (inst["orcid"] and r["orcid"] and inst["orcid"] != r["orcid"]
                    or r["orcid_conflict"]):
                inst["orcid_conflict"] = True
            inst["orcid"] = inst["orcid"] or r["orcid"]
        ok = org_key(r["org_name"], r["org_id"], aliases)
        nk = norm_org_name(r["org_name"])
        if ok:
            inst["org_keys"].add(ok)
            inst["org_names"].add(nk)
            inst["org_pairs"].add((ok, r["org_name"], r["org_id"]))
            signed_key = org_key(r["org_name"], r["org_id"], aliases, allow_partial=False)
            inst["signed_orgs"][signed_key].update(filter(None, (r["org_name"],)))
            inst["org_display"].add(r["org_name"] or ok.removeprefix("id:"))
    ordered = sorted(instances.values(),
                     key=lambda x: (not x["verified"], x["year"] or 0, x["work_id"], x["name_key"]))
    signatures = Counter((inst["work_id"], inst["name_key"]) for inst in ordered)

    persons, by_name, by_orcid = {}, defaultdict(list), {}
    person_orgs, work_persons, merge_log = {}, defaultdict(set), []
    redirects = {}
    anchor_works = defaultdict(set)
    anchor_specs = {}
    for spec in dict.fromkeys(getattr(args, "seed_work", None) or []):
        wid, sep, pos = spec.rpartition("@")
        key = (wid, int(pos)) if sep and pos.isdecimal() else (spec, None)
        anchor_works[key[0]].add(key[1])
        anchor_specs[spec] = key
    seed_names = (args.author or []) + (getattr(args, "seed_name", None) or [])
    seed_keys = {namap.get(norm_name(x), norm_name(x)) for x in seed_names} - {""}
    anchor_matches = defaultdict(list)
    counter = [0]

    def new_person(inst):
        counter[0] += 1
        pid = f"P{counter[0]:04d}"
        p = {
            "person_id": pid, "display_name": inst["verified"][1] if inst["verified"] else inst["name"],
            "name_key": inst["name_key"], "match_names": set(),
            "orcid": inst["orcid"] or "", "org_keys": set(), "org_names": set(),
            "org_display": set(),
            "first_year": inst["year"], "last_year": inst["year"],
            "review_flag": 0, "works": set(), "orcids": set(), "orcid_conflict": False,
        }
        persons[pid] = p
        by_name[p["name_key"]].append(pid)
        if p["orcid"]:
            by_orcid.setdefault(p["orcid"], pid)
        return pid

    def attach(pid, inst, decision, evidence="", detail=""):
        p = persons[pid]
        p["match_names"].update(inst["match_names"])
        p["org_keys"] |= inst["org_keys"]
        p["org_names"] |= inst["org_names"]
        p["org_display"] |= inst["org_display"]
        if inst["year"]:
            p["first_year"] = min(p["first_year"] or inst["year"], inst["year"])
            p["last_year"] = max(p["last_year"] or inst["year"], inst["year"])
        if inst["orcid"]:
            p["orcids"].add(inst["orcid"])
            if not p["orcid"]:
                p["orcid"] = inst["orcid"]
                by_orcid.setdefault(p["orcid"], pid)
        if inst["orcid_conflict"]:
            p["orcid_conflict"] = True
            p["review_flag"] = 1
        for ok, oname, oid in inst["org_pairs"]:
            rec = person_orgs.setdefault((pid, ok), {
                "person_id": pid, "org_key": ok, "org_name": oname,
                "first_year": inst["year"], "last_year": inst["year"],
            })
            rec["org_name"] = rec["org_name"] or oname
            if inst["year"]:
                rec["first_year"] = min(rec["first_year"] or inst["year"], inst["year"])
                rec["last_year"] = max(rec["last_year"] or inst["year"], inst["year"])
        work_persons[inst["work_id"]].add(pid)
        p["works"].add(inst["work_id"])
        anchor_positions = anchor_works.get(inst["work_id"], ())
        if inst["order"] in anchor_positions:
            anchor_matches[inst["work_id"], inst["order"]].append(pid)
        if None in anchor_positions and inst["match_names"] & seed_keys:
            anchor_matches[inst["work_id"], None].append(pid)
        if len(p["org_keys"]) > args.max_orgs:
            p["review_flag"] = 1
        merge_log.append({
            "name_key": p["name_key"], "decision": decision, "person_id": pid,
            "work_id": inst["work_id"], "evidence": evidence, "detail": detail,
            "authorship": {
                "author_order": inst["actual_order"],
                "raw_name": inst["raw_name"],
                "affiliations": sorted(inst["org_display"]),
                "affiliation_names": inst["signed_orgs"],
                "observed_keys": inst["org_keys"],
                "timeline_keys": inst["org_keys"] - ignored_keys,
                "is_first": role_status(inst["is_first"] or ({"yes"} if inst["actual_order"] == 1 else set())),
                "is_corresponding": role_status(inst["is_corresponding"]),
                "role_source": (" | ".join(sorted(inst["role_sources"] - {""}))
                                or ("author_order" if inst["actual_order"] == 1 else "")),
            },
        })

    def compatible(pids, inst=None):
        works, orcids = set(), set()
        if len({persons[pid]["name_key"] for pid in pids
                if persons[pid]["name_key"].startswith("verified:")}) > 1:
            return False
        if inst:
            if inst["orcid_conflict"]:
                return False
            works.add(inst["work_id"])
            if inst["orcid"]:
                orcids.add(inst["orcid"])
        for pid in pids:
            p = persons[pid]
            if p["orcid_conflict"] or works & p["works"]:
                return False
            works.update(p["works"])
            orcids.update(p["orcids"])
            if len(orcids) > 1:
                return False
        return True

    def join_people(pids):
        keep, *others = sorted(pids)
        p = persons[keep]
        for pid in others:
            other = persons.pop(pid)
            by_name[other["name_key"]].remove(pid)
            redirects[pid] = keep
            for field in ("org_keys", "org_names", "org_display", "works", "orcids", "match_names"):
                p[field].update(other[field])
            for field, choose in (("first_year", min), ("last_year", max)):
                dates = [v for v in (p[field], other[field]) if v is not None]
                p[field] = choose(dates) if dates else None
            p["orcid"] = p["orcid"] or other["orcid"]
            p["review_flag"] |= other["review_flag"]
            for wid in other["works"]:
                work_persons[wid].remove(pid)
                work_persons[wid].add(keep)
            for ok in other["org_keys"]:
                rec = person_orgs.pop((pid, ok))
                rec["person_id"] = keep
                current = person_orgs.setdefault((keep, ok), rec)
                current["org_name"] = current["org_name"] or rec["org_name"]
                for field, choose in (("first_year", min), ("last_year", max)):
                    dates = [v for v in (current[field], rec[field]) if v is not None]
                    current[field] = choose(dates) if dates else None
        if p["orcid"]:
            by_orcid[p["orcid"]] = keep
        if len(p["org_keys"]) > args.max_orgs:
            p["review_flag"] = 1
        return keep

    def final_pid(pid):
        while pid in redirects:
            pid = redirects[pid]
        return pid

    # Affiliation overlap is the user's primary identity rule. Conflicting ORCIDs
    # on the same name are common in OpenAlex (duplicate registrations, or ORCIDs
    # mis-attached to a homonym). By default they no longer veto an affiliation
    # match: the record is merged but flagged for review and logged as
    # `orcid_conflict_merged`. Use --orcid-policy strict for the old behaviour.
    strict_orcid = getattr(args, "orcid_policy", "warn") == "strict"
    counts = Counter()
    for inst in ordered:
        nk, orcid = inst["name_key"], inst["orcid"]
        if inst["verified"]:
            pid = next(iter(by_name[nk]), None)
            if (inst["orcid_conflict"] or (orcid in by_orcid and by_orcid[orcid] != pid)
                    or (pid and (not compatible([pid], inst)
                                 or persons[pid]["display_name"] != inst["verified"][1]))):
                raise ValueError(f"Conflicting verified identity on {inst['work_id']}@{inst['order']}")
            pid = pid or new_person(inst)
            attach(pid, inst, "verified_signature", inst["verified"][2],
                   f"{inst['name']} -> {inst['verified'][0]} @{inst['order']}")
            counts["verified_signature"] += 1
            continue
        cands = []
        for pid in by_name.get(nk, []):
            p = persons[pid]
            if inst["work_id"] in p["works"]:
                continue
            if strict_orcid and p["orcid"] and orcid and p["orcid"] != orcid:
                continue
            ev = (inst["org_keys"] & p["org_keys"]) - ignored_keys
            if ev:
                cands.append((len(ev), pid, ev))
        cands.sort(key=lambda t: (-t[0], t[1]))

        orcid_pid = by_orcid.get(orcid)
        bridge_pids = [pid for _, pid, _ in cands]
        if (len(cands) > 1 and signatures[inst["work_id"], nk] == 1
                and (not orcid_pid or orcid_pid in bridge_pids)):
            # A single signature must add distinct affiliation evidence for each
            # cluster. Multiple people at the same affiliation are ambiguous.
            hits = Counter(key for _, _, keys in cands for key in keys)
            distinct = all(any(hits[key] == 1 for key in keys) for _, _, keys in cands)
            if distinct and compatible(bridge_pids, inst):
                pid = join_people(bridge_pids)
                attach(pid, inst, "affiliation_bridge", "|".join(sorted(hits)),
                       f"Connected prior clusters {','.join(bridge_pids)}")
                counts["affiliation_bridge"] += 1
                continue

        if orcid_pid and inst["work_id"] not in persons[orcid_pid]["works"]:
            attach(orcid_pid, inst, "orcid_match", orcid)
            counts["orcid_match"] += 1
            continue

        if len(cands) > 1 and anchor_works:
            pid = new_person(inst)
            persons[pid]["review_flag"] = 1
            attach(pid, inst, "ambiguous_split", "", f"Candidates: {','.join(bridge_pids)}")
            counts["ambiguous_split"] += 1
            continue

        if cands:
            _, pid, ev = cands[0]
            evidence = "|".join(sorted(ev))
            p = persons[pid]
            clash = bool(p["orcid"] and orcid and p["orcid"] != orcid)
            if clash and not strict_orcid:
                p["review_flag"] = 1
                attach(pid, inst, "orcid_conflict_merged", evidence,
                       f"ORCID mismatch {p['orcid']} vs {orcid}; merged by affiliation rule, "
                       f"needs review ({len(cands)} candidate(s))")
                counts["orcid_conflict_merged"] += 1
            elif len(cands) > 1:
                p["review_flag"] = 1
                attach(pid, inst, "ambiguous", evidence,
                       f"{len(cands)} same-name candidates matched; chose largest overlap")
                counts["ambiguous"] += 1
            else:
                attach(pid, inst, "org_match", evidence)
                counts["org_match"] += 1
            continue

        has_org = bool(inst["org_keys"] - ignored_keys)
        same_name = by_name.get(nk, [])
        if (not anchor_works and not has_org and len(same_name) == 1
                and not persons[same_name[0]]["org_keys"]
                and compatible(same_name, inst)):
            attach(same_name[0], inst, "no_org_unique", "", "both records lack affiliation")
            counts["no_org_unique"] += 1
            continue

        conflicting = [pid for pid in same_name
                       if persons[pid]["orcid"] and orcid
                       and persons[pid]["orcid"] != orcid]
        if conflicting:
            decision, evidence, detail = (
                "orcid_conflict", orcid,
                f"same name, different ORCID than {','.join(conflicting)}")
            counts["orcid_conflict"] += 1
        elif not has_org:
            decision, evidence, detail = (
                "unresolved", "", "no usable affiliation evidence")
            counts["unresolved"] += 1
        else:
            decision, evidence, detail = (
                "new_person", "|".join(sorted(inst["org_keys"])), "")
            counts["new_person"] += 1
        pid = new_person(inst)
        attach(pid, inst, decision, evidence, detail)

    seeds = [pid for pid, p in persons.items()
             if (p["match_names"] & seed_keys if p["name_key"].startswith("verified:")
                 else p["name_key"] in seed_keys)]
    if anchor_works:
        confirmed = {}
        for spec, key in anchor_specs.items():
            matches = anchor_matches[key]
            if len(matches) != 1:
                raise ValueError(f"--seed-work {spec}: expected one matching signature, found {len(matches)}")
            confirmed[spec] = final_pid(matches[0])
        pids = set(confirmed.values())
        if len(pids) > 1:
            if not compatible(pids):
                raise ValueError("--seed-work records conflict by ORCID or verified identity, "
                                 "or share a paper as distinct authors")
            keep = join_people(pids)
            for spec, pid in confirmed.items():
                merge_log.append({
                    "name_key": persons[keep]["name_key"], "decision": "verified_seed_work",
                    "person_id": keep, "work_id": anchor_specs[spec][0], "evidence": "|".join(confirmed),
                    "detail": f"User-verified target signature in prior cluster {pid}",
                })
            seeds = [keep]
        else:
            seeds = list(pids)

    for row in merge_log:
        row["person_id"] = final_pid(row["person_id"])
    LOG.info("Disambiguation: %d raw instances -> %d persons; decisions = %s",
             len(ordered), len(persons), dict(counts))
    LOG.info("Seed persons: %s", ", ".join(f"{persons[p]['display_name']}[{p}]" for p in seeds) or "(none)")
    flagged = [p for p, v in persons.items() if v["review_flag"]]
    if flagged:
        LOG.warning("%d persons flagged for manual review (too many affiliations / ambiguous): %s",
                    len(flagged), ", ".join(flagged[:10]))
    return persons, person_orgs, work_persons, merge_log, seeds, dict(counts), flagged


# --------------------------------------------------------------------------
# stage 4: co-authorship edges
# --------------------------------------------------------------------------

def score_authorships(work_persons: dict, authorship: dict) -> None:
    for wid, pids in work_persons.items():
        signatures = {pid: authorship[wid, pid] for pid in pids if (wid, pid) in authorship}
        for field in ROLE_FIELDS:
            leads = [sig for sig in signatures.values() if sig[field] in LEAD_ROLES]
            if len(leads) > 1:
                for sig in leads:
                    sig[field] = "conflict" if sig[field] == "sole" else "shared"
        for signature in signatures.values():
            signature["role_score"] = role_score(signature)


def build_edges(work_persons: dict, works: list[dict], authorship: dict,
                seeds: list[str]) -> list[dict]:
    years = {w["work_id"]: w["year"] for w in works}
    seed_set = set(seeds)
    pairs = defaultdict(lambda: {"papers": {}, "years": Counter()})
    for wid, pids in work_persons.items():
        yr = years.get(wid)
        scores = {pid: authorship.get((wid, pid), {}).get("role_score", 1) for pid in pids}
        for a, b in combinations(sorted(pids), 2):
            rec = pairs[(a, b)]
            rec["papers"][wid] = min(scores[a], scores[b]) if a in seed_set or b in seed_set else 1
            if yr:
                rec["years"][yr] += 1
    edges = []
    for (a, b), rec in sorted(pairs.items()):
        ys = rec["years"]
        edges.append({
            "src": a, "dst": b, "n_papers": len(rec["papers"]),
            "role_weight": sum(rec["papers"].values()), "papers": rec["papers"],
            "first_year": min(ys) if ys else "",
            "last_year": max(ys) if ys else "",
            "year_counts": json.dumps(dict(sorted(ys.items())), ensure_ascii=False),
        })
    LOG.info("Co-author pairs: %d (total joint papers = %d)",
             len(edges), sum(e["n_papers"] for e in edges))
    return edges


# --------------------------------------------------------------------------
# stage 5: factions
# --------------------------------------------------------------------------

def graph_scope(edges, persons, seeds, args):
    kept = [edge for edge in edges if edge["n_papers"] >= args.min_collab]
    nodes = set(persons)
    if args.mode == "seed" and seeds and not args.seed_work:
        neighbors = defaultdict(set)
        for edge in edges:
            a, b = edge["src"], edge["dst"]
            neighbors[a].add(b)
            neighbors[b].add(a)
        nodes = set(seeds)
        frontier = nodes.copy()
        for _ in range(max(1, args.hop)):
            frontier = {p for seed in frontier for p in neighbors[seed]} - nodes
            nodes.update(frontier)

    sub = [edge for edge in kept if edge["src"] in nodes and edge["dst"] in nodes]
    degree = dict.fromkeys(persons, 0.0)
    for edge in sub:
        weight = graph_weight(edge, args)
        degree[edge["src"]] += weight
        degree[edge["dst"]] += weight
    return kept, sub, degree, nodes


def label_num(pid: str) -> int:
    try:
        return int(str(pid)[1:])
    except ValueError:
        return 0


def detect_peer_groups(sub, seeds, args):
    # In a target-centred graph, the target connects otherwise distinct teams.
    # Discover peer groups first, then test the target's links to each group.
    discovery_edges = sub
    if args.mode == "seed":
        seed_set = set(seeds)
        discovery_edges = [e for e in sub if not seed_set.intersection((e["src"], e["dst"]))]
    discovery_nodes = {p for e in discovery_edges for p in (e["src"], e["dst"])}
    adj = defaultdict(list)
    discovery_degree = defaultdict(float)
    for e in discovery_edges:
        a, b, weight = e["src"], e["dst"], graph_weight(e, args)
        adj[a].append((b, weight))
        adj[b].append((a, weight))
        discovery_degree[a] += weight
        discovery_degree[b] += weight

    labels = {p: p for p in discovery_nodes}
    method = args.community
    if method == "louvain" and discovery_edges:
        try:
            import networkx as nx
            g = nx.Graph()
            g.add_nodes_from(sorted(discovery_nodes))
            for e in discovery_edges:
                g.add_edge(e["src"], e["dst"], weight=graph_weight(e, args))
            comms = nx.community.louvain_communities(
                g, weight="weight", resolution=args.resolution, seed=42)
            for i, c in enumerate(comms, 1):
                for p in c:
                    labels[p] = f"C{i}"
            LOG.info("Community detection: Louvain (resolution=%s)", args.resolution)
        except (ImportError, AttributeError):
            LOG.warning("Louvain unavailable; falling back to label propagation")
            method = "labelprop"
    if method == "labelprop":
        order = sorted(discovery_nodes, key=lambda p: (-discovery_degree[p], label_num(p), p))
        for _ in range(60):
            changed = False
            for n in order:
                if not adj.get(n):
                    continue
                weights = Counter()
                for m, wt in adj[n]:
                    weights[labels[m]] += wt
                best = max(weights.items(),
                           key=lambda kv: (kv[1], -label_num(kv[0])))[0]
                if best != labels[n]:
                    labels[n] = best
                    changed = True
            if not changed:
                break
        LOG.info("Community detection: weighted label propagation")

    groups = defaultdict(list)
    for p in discovery_nodes:
        groups[labels[p]].append(p)
    return sorted((set(g) for g in groups.values() if len(g) > 1),
                  key=lambda g: (-len(g), min(g))), method


def load_org_parents(path, aliases):
    parents = {}
    if path:
        for row in read_csv(Path(path)):
            unit = org_key(row.get("unit_name"), row.get("unit_id"), aliases, allow_partial=False)
            parent = org_key(row.get("parent_name"), row.get("parent_id"), aliases, allow_partial=False)
            label = str(row.get("parent_name") or "").strip()
            if not all((unit, parent, label, str(row.get("source") or "").strip())) or unit == parent:
                raise ValueError("Each parent mapping needs a distinct signed unit, parent name and source")
            if parents.setdefault(unit, (parent, label)) != (parent, label):
                raise ValueError(f"Conflicting parents for {unit}")
        if any(parent in parents for parent, _ in parents.values()):
            raise ValueError("Map each subordinate unit directly to its final parent")
    return parents


def affiliation_communities(nodes, persons, works, authorship, edges, sub, args, peer_groups,
                            parents, standalone_orgs, display_names):
    """Group authors by signed unit, including one-time collaborators."""
    labels = defaultdict(Counter)
    signed = {}
    papers_by_org = defaultdict(lambda: defaultdict(set))
    authors_per_work = Counter()
    for (wid, pid), signature in authorship.items():
        if pid not in nodes:
            continue
        signed[wid, pid] = {key: names for key, names in signature["affiliation_names"].items()
                            if key in standalone_orgs}
        for key, names in signed[wid, pid].items():
            labels[key].update(names)
            papers_by_org[key][pid].add(wid)
            authors_per_work[key, wid] += 1
    shared_units = {key for (key, _), count in authors_per_work.items() if count >= 2}
    recurring_members = set().union(*peer_groups)
    orgs = sorted(shared_units, key=lambda key: (-len(papers_by_org[key]), key))
    years = {work["work_id"]: work["year"] for work in works}
    memberships = {pid: {} for pid in persons}
    paper_groups = defaultdict(set)
    factions = []
    for group, key in enumerate(orgs, 1):
        members = papers_by_org[key]
        name = display_names.get(key) or labels[key].most_common(1)[0][0]
        _, school = parents.get(key, (key, ""))
        if school and norm_org_name(school) not in norm_org_name(name):
            name = f"{school} · {name}"
        factions.append({"faction_id": group, "faction_name": name,
                         "size": len(members),
                         "members": "; ".join(sorted(persons[p]["display_name"] for p in members))})
        for pid, papers in members.items():
            by_year = Counter(years[wid] for wid in papers if years[wid])
            affiliations = set()
            for wid in papers:
                paper_groups[wid, pid].add(group)
                affiliations.update(signed[wid, pid][key])
            memberships[pid][group] = {
                "is_base": int(pid in recurring_members),
                "role": "peripheral",
                "supporting_papers": len(papers),
                "community_partners": 0,
                "first_year": min(by_year, default=""), "last_year": max(by_year, default=""),
                "year_counts": json.dumps(dict(sorted(by_year.items()))),
                "affiliations": "; ".join(sorted(affiliations)),
                "work_ids": json.dumps(sorted(papers), ensure_ascii=False),
            }

    inside = defaultdict(Counter)
    inside_weight = Counter()
    inside_kept = Counter()
    internal_degree = defaultdict(Counter)
    partners = defaultdict(set)
    cross = defaultdict(Counter)
    outbound = Counter()
    kept_pairs = {(e["src"], e["dst"]) for e in sub}
    for edge in edges:
        a, b = pair = edge["src"], edge["dst"]
        if a not in nodes or b not in nodes:
            continue
        common = Counter()
        for wid, weight in edge["papers"].items():
            left, right = paper_groups[wid, a], paper_groups[wid, b]
            shared = left & right
            for group in shared:
                common[group] += 1
                inside_weight[group] += weight
                weighted = weight if args.edge_weight == "role" else 1
                internal_degree[group][a] += weighted
                internal_degree[group][b] += weighted
            outbound.update(left ^ right)
            if not shared:
                for first, second in {(min(x, y), max(x, y)) for x in left for y in right}:
                    cross[first, second].update(papers=1, role_weight=weight)
        edge["same_faction"] = bool(common)
        for group, count in common.items():
            inside[group][pair] = count
            inside_kept[group] += pair in kept_pairs
            partners[a, group].add(b)
            partners[b, group].add(a)

    for faction in factions:
        group = faction["faction_id"]
        pairs = inside[group]
        total = sum(pairs.values())
        core = sorted(internal_degree[group], key=lambda p: (-internal_degree[group][p], p))[:3]
        for pid in core:
            memberships[pid][group]["role"] = "core"
        faction.update(
            core_members="; ".join(persons[p]["display_name"] for p in core),
            internal_pairs=len(pairs),
            internal_collab_times=total,
            internal_role_weight=inside_weight[group],
            mean_collab_per_pair=round(total / len(pairs), 2) if pairs else 0,
            top_pairs="; ".join(f"{persons[a]['display_name']} – {persons[b]['display_name']} ({count})"
                                for (a, b), count in pairs.most_common(3)),
            cross_faction_collab_times=outbound[group],
            edges_kept_by_threshold=inside_kept[group],
        )

    cid, roles = {}, {}
    for pid, groups in memberships.items():
        for group, entry in groups.items():
            entry["community_partners"] = len(partners[pid, group])
        main = max(groups, key=lambda group: (groups[group]["supporting_papers"], -group), default=-1)
        cid[pid] = main
        roles[pid] = groups[main]["role"] if main > 0 else "isolated"
    cross_rows = [{"faction_a": a, "faction_b": b, "collab_times": tally["papers"],
                   "role_weight": tally["role_weight"]}
                  for (a, b), tally in sorted(cross.items())]
    return cid, roles, memberships, factions, cross_rows


# --------------------------------------------------------------------------
# stage 6: export
# --------------------------------------------------------------------------

TIMELINE_COLUMNS = ["person_id", "name", "verified_person_id", "orcid", "org_key", "org_name",
                    "relationship", "basis", "start_date", "end_date", "ongoing", "source",
                    "observed_first_year", "observed_last_year", "observed_papers", "work_ids",
                    "later_org", "later_first_year", "later_last_year", "later_work_ids"]


def affiliation_timeline(works, persons, person_orgs, authorship, estimate_for, history, aliases):
    years = {work["work_id"]: work["year"] for work in works}
    observed = defaultdict(lambda: defaultdict(set))
    by_person = defaultdict(list)
    for (wid, pid), signature in authorship.items():
        orgs = signature["timeline_keys"]
        for org in orgs:
            observed[pid, org][years[wid]].add(wid)
        if orgs and years[wid] and pid in estimate_for:
            by_person[pid].append((years[wid], wid, orgs))

    identities = {pid: {"person_id": pid, "name": person["display_name"], "orcid": person["orcid"],
                        "verified_person_id": (person["name_key"][9:]
                                               if person["name_key"].startswith("verified:") else "")}
                  for pid, person in persons.items()}
    documented = defaultdict(list)
    if history:
        path = Path(history)
        if not path.is_file():
            raise FileNotFoundError(f"Affiliation history not found: {path}")
        for row in read_csv(path):
            row = {key: value.strip() for key, value in row.items()}
            verified = row.get("verified_person_id", "")
            orcid = clean_orcid(row.get("orcid", ""))
            key = org_key(row.get("org_name", ""), row.get("org_id", ""), aliases)
            if not ((verified or orcid) and key and row.get("source") and row.get("relationship")):
                raise ValueError("Affiliation history requires an identity, organization, relationship and source")
            matches = [pid for pid, identity in identities.items()
                       if (not verified or verified == identity["verified_person_id"])
                       and (not orcid or orcid == identity["orcid"])]
            if len(matches) != 1:
                LOG.warning("Affiliation history row matched %d persons: %s / %s", len(matches), verified, orcid)
                continue
            start, end, ongoing = (row.get(field, "") for field in ("start_date", "end_date", "ongoing"))
            for value in filter(None, (start, end)):
                if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
                    raise ValueError(f"Invalid affiliation history date: {value}")
                date.fromisoformat(value + {4: "-01-01", 7: "-01", 10: ""}[len(value)])
            precision = min(len(start), len(end))
            if ongoing not in ("", "yes") or (ongoing and end) or start[:precision] > end[:precision]:
                raise ValueError(f"Conflicting affiliation history dates for {verified or orcid}: {key}")
            documented[matches[0], key].append({
                "org_name": row.get("org_name", "") or key, "relationship": row["relationship"],
                "basis": "documented", "start_date": start, "end_date": end,
                "ongoing": ongoing, "source": row["source"],
            })

    rows = []
    for pid, org in sorted(observed.keys() | documented.keys()):
        papers_by_year = observed.get((pid, org), {})
        dated = sorted(y for y in papers_by_year if y)
        first, last = (dated[0], dated[-1]) if dated else ("", "")
        work_ids = sorted({wid for ids in papers_by_year.values() for wid in ids})
        common = {**identities[pid], "org_key": org,
                  "observed_first_year": first, "observed_last_year": last,
                  "observed_papers": len(work_ids), "work_ids": json.dumps(work_ids, ensure_ascii=False)}
        if (pid, org) in documented:
            rows.extend({**common, **record} for record in documented[pid, org])
            continue

        row = {**common, "org_name": person_orgs[pid, org]["org_name"] or org,
               "relationship": "publication_affiliation", "basis": "observed"}
        if len(dated) >= 2 and pid in estimate_for:
            replacements = defaultdict(lambda: defaultdict(set))
            for year, wid, orgs in by_person[pid]:
                if year > last:
                    for other in orgs - {org}:
                        replacements[other][year].add(wid)
            candidates = [key for key, dates in replacements.items()
                          if len(dates) >= 3 and max(dates) - last >= 3]
            if candidates:
                other = min(candidates, key=lambda key: (-len(replacements[key]), key))
                dates = replacements[other]
                row.update(basis="estimated", start_date=first, end_date=last,
                           later_org=person_orgs[pid, other]["org_name"] or other,
                           later_first_year=min(dates), later_last_year=max(dates),
                           later_work_ids=json.dumps(sorted({w for ids in dates.values() for w in ids}),
                                                     ensure_ascii=False))
        rows.append(row)
    return rows


def write_db(path, args, run_id, works, persons, person_orgs, work_persons,
             merge_log, edges, cid, degree, roles, method, stats, npapers, authorship,
             membership_rows):
    if path.exists():
        path.unlink()
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT OR REPLACE INTO work VALUES (?,?,?,?,?,?,?)",
        [(w["work_id"], w["doi"], w["title"], w["year"], w["venue"],
          "|".join(sorted(w["issns"])), w["zone"]) for w in works],
    )
    con.executemany(
        "INSERT INTO person VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(p["person_id"], p["display_name"], p["name_key"], p["orcid"],
          json.dumps(sorted(p["org_keys"]), ensure_ascii=False),
          json.dumps(sorted(x for x in p["org_names"] if x), ensure_ascii=False),
          p["first_year"], p["last_year"],
          npapers[p["person_id"]], p["review_flag"]) for p in persons.values()],
    )
    con.executemany(
        "INSERT OR REPLACE INTO person_org VALUES (?,?,?,?,?)",
        [(r["person_id"], r["org_key"], r["org_name"], r["first_year"], r["last_year"])
         for r in person_orgs.values()],
    )
    con.executemany(
        "INSERT OR REPLACE INTO authorship VALUES (?,?,?,?,?,?)",
        [(wid, pid, sig.get("author_order"), sig.get("is_first", "unknown"),
          sig.get("is_corresponding", "unknown"), sig.get("role_source", ""))
         for (wid, pid), sig in authorship.items()],
    )
    con.executemany(
        "INSERT INTO merge_log (name_key,decision,person_id,work_id,evidence,detail) "
        "VALUES (?,?,?,?,?,?)",
        [(r["name_key"], r["decision"], r["person_id"], r["work_id"],
          r["evidence"], r["detail"]) for r in merge_log],
    )
    con.executemany(
        "INSERT INTO coauthor_edge VALUES (?,?,?,?,?,?,?)",
        [(e["src"], e["dst"], e["n_papers"], e["first_year"] or None,
          e["last_year"] or None, e["year_counts"], e.get("role_weight", e["n_papers"])) for e in edges],
    )
    con.executemany(
        "INSERT INTO faction VALUES (?,?,?,?,?,?,?)",
        [(run_id, p, cid[p], method,
          json.dumps({"min_collab": args.min_collab, "mode": args.mode,
                      "hop": args.hop,
                      "edge_weight": getattr(args, "edge_weight", "role")}),
          degree[p], roles[p]) for p in persons],
    )
    con.executemany(
        "INSERT INTO faction_membership VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(run_id, r["person_id"], r["faction_id"], r["is_primary"], r["is_base"], r["role"],
          r["supporting_papers"], r["community_partners"], r["first_year"] or None,
          r["last_year"] or None, r["year_counts"], r["affiliations"], r["work_ids"])
         for r in membership_rows],
    )
    con.execute("INSERT INTO run_meta VALUES (?,?,?,?,?)", (
        run_id, datetime.now().isoformat(timespec="seconds"),
        json.dumps({"author": args.author, "org": args.org, "journal": args.journal,
                    "zone": args.zone, "from_year": args.from_year,
                    "to_year": args.to_year}, ensure_ascii=False),
        json.dumps({"min_collab": args.min_collab, "mode": args.mode,
                    "community": method, "source": args.source}, ensure_ascii=False),
        json.dumps(stats, ensure_ascii=False),
    ))
    con.commit()
    con.close()


def build_html(path, nodes, edges, persons, cid, memberships, degree, args, faction_rows,
               *, seeds, paper_count, pending_affiliations, joint_units, seed_collaborations):
    palette_size = len(PALETTE)
    faction_names = {row["faction_id"]: row["faction_name"] for row in faction_rows}
    node_rows = []
    for pid in sorted(nodes):
        p = persons[pid]
        c = cid.get(pid, -1)
        orgs = sorted(x for x in p["org_display"] if x)
        node_rows.append({
            "id": pid,
            "name": p["display_name"],
            "orgs": ", ".join(orgs),
            "joint_units": sorted(joint_units[pid]),
            "c": c,
            "groups": [{"id": g, "name": faction_names[g], "color": PALETTE[(g - 1) % palette_size],
                        "papers": r["supporting_papers"],
                        "first": r["first_year"], "last": r["last_year"]}
                       for g, r in memberships[pid].items()],
            "color": ISOLATED_COLOR if c <= 0 else PALETTE[(c - 1) % palette_size],
            "deg": degree.get(pid, 0),
            "seed_collaborations": seed_collaborations.get(pid, []),
            "seed": pid in seeds,
        })
    link_rows = [{"src": e["src"], "dst": e["dst"], "n": e["n_papers"], "w": graph_weight(e, args)}
                 for e in edges if e["src"] in nodes and e["dst"] in nodes]
    payload = {
        "nodes": node_rows, "edges": link_rows,
        "demo": args.source == "demo",
        "seed_names": list(dict.fromkeys(persons[pid]["display_name"] for pid in seeds)),
        "seed_orcids": [
            {"name": persons[pid]["display_name"],
             "url": orcid_profile_url(persons[pid]["orcids"])
             if not persons[pid]["orcid_conflict"]
             and (persons[pid]["name_key"].startswith("verified:") or args.seed_work) else ""}
            for pid in seeds
        ],
        "paper_count": paper_count, "pending_affiliations": pending_affiliations,
        "author_count": len(persons),
        "edge_weight": getattr(args, "edge_weight", "role"),
        "factions": [{"id": r["faction_id"], "name": r["faction_name"], "size": r["size"],
                      "color": PALETTE[(r["faction_id"] - 1) % palette_size],
                      "collab": r["internal_collab_times"]}
                     for r in faction_rows],
    }
    data_js = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = HTML_TEMPLATE.replace("__DATA__", data_js)
    path.write_text(html, encoding="utf-8")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>合作网络｜Scholar Trails</title>
<style>
:root {
  color-scheme: light;
  --ink: #152c25;
  --muted: #52665e;
  --paper: #f3f1e7;
  --panel: #fffcf4;
  --border: #d6ddce;
  --plot: #102a24;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
       font: 14px/1.5 "Instrument Sans", "Microsoft YaHei", sans-serif; }
main { max-width: 1344px; margin: auto; padding: 36px 42px 42px; }
.brand { display: flex; align-items: center; justify-content: space-between; gap: 14px;
         padding: 0 0 15px; border-bottom: 1px solid var(--border); color: #265545; }
.brand-name { font-weight: 700; letter-spacing: .055em; }
.brand-name span { margin-left: 9px; font-size: 12px; }
.demo-label { padding: 4px 10px; border-radius: 20px; background: #e1eddd;
              color: #285540; font-size: 12px; font-weight: 700; }
header { display: flex; align-items: end; justify-content: space-between; flex-wrap: wrap;
         gap: 20px 32px; padding: 26px 0 22px; }
h1 { margin: 0; font: 700 clamp(32px, 5vw, 46px)/1.2 "Noto Serif CJK SC", "SimSun", serif;
     letter-spacing: -.03em; }
#subject { margin: 9px 0 0; color: var(--muted); overflow-wrap: anywhere; }
.stats { display: flex; gap: 0; margin: 0; align-items: end; }
.stats div { display: flex; flex-direction: column; min-width: 98px;
             border-left: 1px solid #ccd6c9; padding: 0 17px 1px; }
.stats dt { color: var(--muted); font-size: 12px; white-space: nowrap; }
.stats dd { order: -1; margin: 0 0 4px; font: 700 32px/1 "Instrument Serif", Georgia, serif;
            font-variant-numeric: lining-nums tabular-nums; }
.wrap { display: grid; grid-template-columns: minmax(0, 1fr) 236px; gap: 16px; align-items: start; }
.plot, aside { min-width: 0; background: var(--panel); border: 1px solid var(--border);
               border-radius: 14px; overflow: hidden; }
.toolbar { padding: 11px 13px; display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
input, button { color: var(--ink); background: #fffef9; border: 1px solid #cdd9cc;
                border-radius: 7px; font: inherit; padding: 6px 10px; }
input { width: min(100%, 225px); }
input::placeholder { color: #576961; }
button { min-width: 34px; cursor: pointer; }
button:hover { background: #e5efe3; }
:focus-visible { outline: 2px solid #267957; outline-offset: 2px; }
.controls { display: flex; gap: 5px; }
#svg { display: block; width: 100%; height: auto; touch-action: none; cursor: grab; user-select: none;
       background-color: var(--plot);
       background-image: radial-gradient(circle, #91b6a538 1px, transparent 1.3px),
                         radial-gradient(ellipse at 45% 30%, #244d40, transparent 78%);
       background-size: 20px 20px, 100% 100%; }
#svg.dragging, #svg.dragging .node { cursor: grabbing; }
.plot-note { margin: 0; padding: 9px 13px; color: var(--muted); font-size: 12px; }
aside { padding: 17px 15px; }
aside h2 { margin: 0 0 10px; font-size: 16px; }
.legend { display: flex; align-items: flex-start; gap: 10px; padding: 10px 0;
          border-top: 1px solid #e0e5d9; }
.legend strong, .legend small { display: block; }
.legend small { margin-top: 2px; color: var(--muted); font-size: 12px; }
.dot { width: 12px; height: 12px; margin-top: 4px; border-radius: 50%; flex: none;
       border: 1px solid #102a2455; }
.hint { margin: 9px 0 0; color: var(--muted); font-size: 12px; line-height: 1.65; }
.node { cursor: grab; }
.node:active { cursor: grabbing; }
.node text { fill: #eef7ed; stroke: var(--plot); stroke-width: 3px; paint-order: stroke;
             font-size: 14px; font-weight: 650; text-anchor: middle; pointer-events: none; }
.node.seed text { fill: #fff; font-weight: 750; }
.node .node-unit { fill: #c6ded2; font-size: 10px; font-weight: 500; }
.dense .node text { visibility: hidden; }
.dense .node:is(.seed, .hit, :hover) text { visibility: visible; }
.node.hit .marker { stroke: #fff; stroke-width: 3px; }
.dim { opacity: .2; }
#tip { position: fixed; z-index: 1; pointer-events: none; padding: 10px 12px;
       background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
       max-width: min(290px, calc(100vw - 20px)); box-shadow: 0 5px 20px #102a2424;
       overflow-wrap: anywhere; font-size: 12px; }
@media (max-width: 760px) {
  main { padding: 20px 16px 24px; }
  .wrap { grid-template-columns: minmax(0, 1fr); }
  .stats div { min-width: 76px; padding: 0 12px; }
  .stats dd { font-size: 26px; }
}
</style>
</head>
<body>
<main>
  <div class="brand">
    <div class="brand-name">Scholar Trails <span>学缘寻踪</span></div>
    <span class="demo-label" id="demo-label" hidden>虚构数据演示</span>
  </div>
  <header>
    <div><h1>合作网络</h1><p id="subject"></p><p id="pending" hidden></p></div>
    <dl class="stats">
      <div><dt>图内论文</dt><dd id="s1"></dd></div>
      <div><dt>已核验作者</dt><dd id="s2"></dd></div>
      <div><dt>合作社区</dt><dd id="s3"></dd></div>
    </dl>
  </header>
  <div class="wrap">
    <section class="plot" aria-label="合著关系图">
      <div class="toolbar">
        <input type="search" id="q" aria-label="搜索姓名或单位" placeholder="搜索姓名或单位">
        <div class="controls">
          <button type="button" id="zoom-out" aria-label="缩小">−</button>
          <button type="button" id="zoom-in" aria-label="放大">+</button>
          <button type="button" id="reset">重置视图</button>
        </div>
      </div>
      <svg id="svg" viewBox="0 0 900 510" role="img" aria-label="作者及其合著关系"></svg>
      <p class="plot-note" id="s4"></p>
    </section>
    <aside>
      <h2>合作社区</h2>
      <div id="legend"></div>
      <p class="hint">按合著关系识别社区。单位归属须有本人论文署名支持。白色外圈标记检索对象。</p>
      <p class="hint">拖动画布空白处可平移。悬停作者可查看单位和所属社区，连线越粗表示合作权重越高。</p>
    </aside>
  </div>
</main>
<div id="tip" hidden></div>
<script>
const D = __DATA__;
const N = D.nodes, E = D.edges;
const escapeText = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
const W = 900, H = 510, CX = W/2, CY = H/2;
const idx = Object.fromEntries(N.map((n,i)=>[n.id,i]));
const spaced = N.length <= 48 && D.factions.length >= 2 && D.factions.length <= 6;
const anchors = new Map(D.factions.map((f,i)=>{
  const a = -Math.PI/2 - Math.PI/D.factions.length + 2*Math.PI*i/D.factions.length;
  return [f.id, [CX + W*.26*Math.cos(a), CY + H*.27*Math.sin(a)]];
}));
N.forEach((n,i)=>{
  const a = 2*Math.PI*i/Math.max(1,N.length);
  n.anchor = spaced ? (anchors.get(n.c) || [W*.83,H*.79]) : [CX,CY];
  const spread = spaced ? 44 : H*.39;
  n.x = n.anchor[0] + spread*Math.cos(a) + ((i*37)%23-11);
  n.y = n.anchor[1] + spread*Math.sin(a) + ((i*53)%23-11);
  n.vx=0; n.vy=0;
});
const L = E.filter(e=>idx[e.src]!==undefined && idx[e.dst]!==undefined)
           .map(e=>({a:idx[e.src], b:idx[e.dst], n:e.n, w:e.w}));
const STEPS = Math.max(60, Math.min(320, Math.floor(3000000/Math.max(1,N.length*N.length/2))));
for (let step=0; step<STEPS; step++) {
  for (let i=0;i<N.length;i++) for (let j=i+1;j<N.length;j++) {
    const dx=N[i].x-N[j].x, dy=N[i].y-N[j].y, d2=dx*dx+dy*dy+0.01, d=Math.sqrt(d2), f=5200/d2;
    const fx=dx/d*f, fy=dy/d*f;
    N[i].vx+=fx; N[i].vy+=fy; N[j].vx-=fx; N[j].vy-=fy;
  }
  for (const l of L) {
    const A=N[l.a], B=N[l.b], dx=B.x-A.x, dy=B.y-A.y, d=Math.sqrt(dx*dx+dy*dy)+0.01;
    const rest=Math.max(45,105-Math.min(45,l.w*6)), f=0.015*(d-rest);
    const fx=dx/d*f, fy=dy/d*f;
    A.vx+=fx; A.vy+=fy; B.vx-=fx; B.vy-=fy;
  }
  if (step%5===0) {
    const cen={}; N.forEach(n=>{ const c=n.c; if(c<=0) return;
      if(!cen[c]) cen[c]={x:0,y:0,k:0}; cen[c].x+=n.x; cen[c].y+=n.y; cen[c].k++; });
    Object.values(cen).forEach(o=>{o.x/=o.k;o.y/=o.k;});
    N.forEach(n=>{ const c=cen[n.c]; if(c){ n.vx+=(c.x-n.x)*0.006; n.vy+=(c.y-n.y)*0.006; } });
  }
  N.forEach(n=>{
    const pull = spaced ? 0.014 : 0.0025;
    n.vx+=(n.anchor[0]-n.x)*pull; n.vy+=(n.anchor[1]-n.y)*pull;
    n.vx*=0.82; n.vy*=0.82;
    n.x+=Math.max(-14,Math.min(14,n.vx)); n.y+=Math.max(-14,Math.min(14,n.vy));
    n.x=Math.max(48,Math.min(W-48,n.x));
    n.y=Math.max(28,Math.min(H-42-13*n.joint_units.length,n.y));
  });
}
const svg=document.getElementById('svg');
svg.classList.toggle('dense', N.length > 48);
let out='<g id="vp">';
for(const l of L){ const A=N[l.a],B=N[l.b];
  const color=A.c>0 && A.c===B.c ? A.color : '#9aada5';
  const sw=Math.min(1+Math.log2(l.w+1)*1.25,7);
  out+='<line x1="'+A.x+'" y1="'+A.y+'" x2="'+B.x+'" y2="'+B.y+'" stroke="'+color+'" stroke-width="'+sw+'" opacity=".57" stroke-linecap="round"><title>合著 '+l.n+' 篇 · 合作权重 '+l.w+'</title></line>'; }
for(const n of N){
  const r=6+Math.min(Math.sqrt(n.deg)*2.2,10);
  out+='<g class="node'+(n.seed?' seed':'')+'" data-id="'+n.id+'" transform="translate('+n.x+','+n.y+')"><circle class="marker" r="'+r+'" fill="'+n.color+'" stroke="#102a24" stroke-width="1.8"/>';
  if(n.groups.length>1){
    n.groups.forEach((g,i)=>{out+='<circle r="'+(r+2)+'" fill="none" stroke="'+g.color+'" stroke-width="2.5" pathLength="'+n.groups.length+'" stroke-dasharray=".88 '+(n.groups.length-.88)+'" stroke-dashoffset="'+(-i)+'" pointer-events="none"/>';});
  }
  if(n.seed) out+='<circle r="'+(r+(n.groups.length>1?6:3))+'" fill="none" stroke="#fff" stroke-width="1.5" pointer-events="none"/>';
  out+='<text y="'+(r+20)+'">'+escapeText(n.name);
  for(const unit of n.joint_units){ out+='<tspan class="node-unit" x="0" dy="13">'+escapeText(unit)+'</tspan>'; }
  out+='</text></g>';
}
out+='</g>';
svg.innerHTML=out;
document.getElementById('demo-label').hidden=!D.demo;
document.getElementById('subject').textContent=D.seed_names.length ? '检索对象 · '+D.seed_names.join('、') : '当前范围内的合著关系';
D.seed_orcids.forEach(profile=>{
  const label=D.seed_orcids.length>1 ? profile.name+' ORCID' : 'ORCID';
  const subject=document.getElementById('subject');
  if(!profile.url){ subject.append(' · '+label+' 未找到'); return; }
  const link=document.createElement('a');
  link.href=profile.url; link.target='_blank'; link.rel='noopener';
  link.textContent=label+' '+profile.url.split('/').pop();
  subject.append(' · ', link);
});
const pending=document.getElementById('pending');
pending.hidden=!D.pending_affiliations;
pending.textContent='作者与连线仅按已核实署名展示。';
document.getElementById('s1').textContent=D.paper_count;
document.getElementById('s2').textContent=D.author_count;
document.getElementById('s3').textContent=D.factions.length;
const weighting=D.edge_weight==='role'&&D.seed_names.length ? '检索对象按署名角色加权' : '按共同论文篇数计权';
document.getElementById('s4').textContent='图中 '+N.length+' 位作者 · '+L.length+' 条连线 · '+weighting;
document.getElementById('legend').innerHTML = D.factions.map(f=>
  '<div class="legend"><span class="dot" style="background:'+f.color+'"></span><div><strong>'+escapeText(f.name)+'</strong><small>'+f.size+' 位作者 · '+f.collab+' 次组内合著</small></div></div>').join('')
  || '<p class="hint">当前范围没有符合条件的合作社区。</p>';
let scale=1, tx=0, ty=0;
const vp=document.getElementById('vp');
const nodeElements=vp.querySelectorAll('.node');
const edgeElements=vp.querySelectorAll('line');
const tip=document.getElementById('tip');
function apply(){ vp.setAttribute('transform','translate('+tx+','+ty+') scale('+scale+')'); }
function svgPoint(e){
  return new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
}
function zoom(factor,x,y){
  const next=Math.max(.4,Math.min(4,scale*factor));
  tx=x-(x-tx)*next/scale;
  ty=y-(y-ty)*next/scale;
  scale=next;
  apply();
  tip.hidden=true;
}
svg.addEventListener('wheel',e=>{
  e.preventDefault();
  const p=svgPoint(e);
  zoom(e.deltaY<0?1.12:1/1.12,p.x,p.y);
},{passive:false});
document.getElementById('zoom-out').onclick=()=>zoom(1/1.2,CX,CY);
document.getElementById('zoom-in').onclick=()=>zoom(1.2,CX,CY);
document.getElementById('reset').onclick=()=>{
  scale=1; tx=0; ty=0; apply(); tip.hidden=true;
};
let drag=null;
svg.addEventListener('pointerdown',e=>{
  if(drag || e.button!==0) return;
  const g=e.target.closest('.node');
  const p=svgPoint(e);
  if(g){
    const i=idx[g.dataset.id], n=N[i], links=[];
    L.forEach((l,j)=>{
      if(l.a===i || l.b===i) links.push([edgeElements[j],l.a===i?'1':'2']);
    });
    drag={g,n,links,pointer:e.pointerId,ox:(p.x-tx)/scale-n.x,oy:(p.y-ty)/scale-n.y};
  }else{
    drag={pointer:e.pointerId,ox:p.x-tx,oy:p.y-ty};
  }
  tip.hidden=true;
  svg.classList.add('dragging');
  svg.setPointerCapture(e.pointerId);
});
svg.addEventListener('pointermove',e=>{
  if(drag){
    if(e.pointerId!==drag.pointer) return;
    const p=svgPoint(e), {n,g,links,ox,oy}=drag;
    if(!g){
      tx=p.x-ox; ty=p.y-oy;
      apply();
      return;
    }
    n.x=(p.x-tx)/scale-ox;
    n.y=(p.y-ty)/scale-oy;
    g.setAttribute('transform','translate('+n.x+','+n.y+')');
    links.forEach(([line,end])=>{
      line.setAttribute('x'+end,n.x); line.setAttribute('y'+end,n.y);
    });
    return;
  }
  const g=e.target.closest('.node');
  if(!g){ tip.hidden=true; return; }
  const n=N[idx[g.dataset.id]];
  const groups=n.groups.map(g=>escapeText(g.name)+' · '+g.papers+' 篇署名记录'+(g.first?' · '+g.first+(g.last!==g.first?'–'+g.last:''):'')).join('<br>');
  const weights=n.seed_collaborations.length
    ? n.seed_collaborations.map(c=>'与'+escapeText(c.name)+'的合作权重：'+c.weight).join('<br>')
    : '图内合作权重合计：'+n.deg;
  tip.innerHTML='<b>'+escapeText(n.name)+'</b><br>署名单位：'+escapeText(n.orgs)+'<br>'+(groups||'未归入社区')+'<br>'+weights;
  tip.hidden=false;
  tip.style.left=Math.max(8,Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8))+'px';
  tip.style.top=Math.max(8,Math.min(e.clientY+14,innerHeight-tip.offsetHeight-8))+'px';
});
svg.addEventListener('lostpointercapture',e=>{
  if(drag?.pointer!==e.pointerId) return;
  drag=null;
  svg.classList.remove('dragging');
});
svg.addEventListener('pointerleave',()=>{tip.hidden=true;});
const authorSearch=document.getElementById('q');
authorSearch.addEventListener('input',()=>{
  const q=authorSearch.value.trim().toLowerCase();
  const matches=N.map(n=>n.name.toLowerCase().includes(q)||n.orgs.toLowerCase().includes(q));
  nodeElements.forEach((g,i)=>{
    g.classList.toggle('hit',!!q&&matches[i]); g.classList.toggle('dim',!matches[i]);
  });
  edgeElements.forEach((line,i)=>{
    const edge=L[i];
    line.classList.toggle('dim',!matches[edge.a]&&!matches[edge.b]);
  });
});
</script>
</body>
</html>
"""


def export_all(out: Path, args, run_id, works, persons, person_orgs, work_persons,
               merge_log, edges, kept, cid, degree, roles, method, seeds,
               factions, cross_rows, stats, memberships, nodes, authorship, *, standalone_orgs):
    name = lambda p: persons[p]["display_name"]
    es = lambda s: "; ".join(sorted(x for x in s if x))

    # Precompute all per-person aggregates once (linear in edges + authorships).
    kept_keys = {(e["src"], e["dst"]) for e in kept}
    npapers = Counter()
    role_counts = defaultdict(Counter)
    authorship_rows = []
    for pids in work_persons.values():
        for p in pids:
            npapers[p] += 1
    for (wid, p), sig in sorted(authorship.items()):
        category = authorship_role(sig)
        for field in ROLE_FIELDS:
            role_counts[p][field] += sig.get(field) in LEAD_ROLES
        role_counts[p][category] += 1
        authorship_rows.append({"work_id": wid, "person_id": p, "name": name(p),
                                "is_first": "unknown", "is_corresponding": "unknown", "role_score": 1,
                                **sig, "role": category})
    write_csv(out / "authorship_roles.csv", authorship_rows,
              ["work_id", "person_id", "name", "author_order", "is_first", "is_corresponding",
               "role", "role_score", "role_source"])
    ncols = Counter()
    total_collab = Counter()
    edges_by_person = defaultdict(list)
    for e in edges:
        ncols[e["src"]] += 1
        ncols[e["dst"]] += 1
        total_collab[e["src"]] += e["n_papers"]
        total_collab[e["dst"]] += e["n_papers"]
        edges_by_person[e["src"]].append(e)
        edges_by_person[e["dst"]].append(e)

    write_csv(out / "edges.csv", [{
        "src": e["src"], "dst": e["dst"],
        "src_name": name(e["src"]), "dst_name": name(e["dst"]),
        "coauthored_papers": e["n_papers"],
        "role_weight": e.get("role_weight", e["n_papers"]),
        "first_year": e["first_year"], "last_year": e["last_year"],
        "year_counts": e["year_counts"],
        "kept_by_threshold": int((e["src"], e["dst"]) in kept_keys),
        "same_faction": int(e.get("same_faction", False)),
    } for e in edges],
        ["src", "dst", "src_name", "dst_name", "coauthored_papers", "role_weight",
         "first_year", "last_year", "year_counts", "kept_by_threshold", "same_faction"])

    write_csv(out / "coauthors.csv", [{
        "person_id": p,
        "name": v["display_name"],
        "orcid": v["orcid"],
        "affiliations": es(v["org_display"]),
        "n_affiliations": len(v["org_keys"]),
        "papers_in_scope": npapers[p],
        "first_author_papers": role_counts[p]["is_first"],
        "corresponding_author_papers": role_counts[p]["is_corresponding"],
        "both_roles_papers": role_counts[p]["first_and_corresponding"],
        "ordinary_author_papers": role_counts[p]["ordinary"],
        "unconfirmed_role_papers": role_counts[p]["unconfirmed"],
        "n_coauthors": ncols[p],
        "total_collab_times": total_collab[p],
        "faction_id": cid.get(p, -1),
        "faction_ids": "|".join(map(str, memberships[p])),
        "role": roles.get(p, "isolated"),
        "is_seed": int(p in seeds),
        "review_flag": v["review_flag"],
        "first_year": v["first_year"] or "", "last_year": v["last_year"] or "",
    } for p, v in sorted(persons.items())],
        ["person_id", "name", "orcid", "affiliations", "n_affiliations",
         "papers_in_scope", "first_author_papers", "corresponding_author_papers",
         "both_roles_papers", "ordinary_author_papers", "unconfirmed_role_papers",
         "n_coauthors", "total_collab_times", "faction_id",
         "faction_ids", "role", "is_seed", "review_flag", "first_year", "last_year"])

    faction_names = {row["faction_id"]: row["faction_name"] for row in factions}
    membership_rows = [
        {"person_id": p, "name": name(p), "faction_id": group, "faction_name": faction_names[group],
         "is_primary": int(group == cid[p]), **evidence}
        for p, groups in sorted(memberships.items()) for group, evidence in groups.items()
    ]
    write_csv(out / "faction_memberships.csv", membership_rows,
              ["person_id", "name", "faction_id", "is_primary", "is_base", "role", "supporting_papers",
               "community_partners", "first_year", "last_year", "year_counts", "affiliations", "work_ids",
               "faction_name"])
    write_csv(out / "factions.csv", factions,
              ["faction_id", "size", "members", "core_members", "internal_pairs",
               "internal_collab_times", "internal_role_weight", "mean_collab_per_pair", "top_pairs",
               "cross_faction_collab_times", "edges_kept_by_threshold", "faction_name"])
    write_csv(out / "faction_cross.csv", cross_rows,
              ["faction_a", "faction_b", "collab_times", "role_weight"])

    seed_rows = []
    for s in seeds:
        for e in sorted(edges_by_person[s], key=lambda x: -graph_weight(x, args)):
            other = e["dst"] if e["src"] == s else e["src"]
            seed_rows.append({
                "seed": name(s), "seed_id": s, "coauthor": name(other),
                "coauthor_id": other, "coauthored_papers": e["n_papers"],
                "role_weight": e.get("role_weight", e["n_papers"]),
                "first_year": e["first_year"], "last_year": e["last_year"],
                "affiliations": es(persons[other]["org_display"]),
                "coauthor_faction_id": cid.get(other, -1),
                "coauthor_faction_ids": "|".join(map(str, memberships[other])),
                "kept_by_threshold": int((e["src"], e["dst"]) in kept_keys),
            })
    write_csv(out / "seed_coauthors.csv", seed_rows,
              ["seed", "seed_id", "coauthor", "coauthor_id", "coauthored_papers", "role_weight",
               "first_year", "last_year", "affiliations", "coauthor_faction_id",
               "coauthor_faction_ids", "kept_by_threshold"])

    write_csv(out / "merge_log.csv", merge_log,
              ["name_key", "decision", "person_id", "work_id", "evidence", "detail"])

    viz_nodes = set(nodes)
    if len(viz_nodes) > args.max_nodes:
        viz_nodes = set(sorted(nodes, key=lambda p: (p not in seeds, -degree[p], p))[:args.max_nodes])
        LOG.warning("Visualisation truncated to %d nodes", args.max_nodes)
    if args.no_html:
        LOG.info("Skipping network.html (--no-html); CSV and SQLite outputs are complete")
    else:
        seed_set = set(seeds)
        viz_edges = [e for e in edges if e["src"] in viz_nodes and e["dst"] in viz_nodes
                     and (e["n_papers"] >= args.min_collab or e.get("same_faction")
                          or e["src"] in seed_set or e["dst"] in seed_set)]
        if len(viz_edges) > args.max_edges:
            viz_edges = sorted(viz_edges, key=lambda e: -graph_weight(e, args))[:args.max_edges]
            LOG.warning("Visualisation truncated to top %d edges by collaboration "
                        "count (raise --max-edges if needed)", args.max_edges)
        joint_units = defaultdict(set)
        for (_, pid), signature in authorship.items():
            if pid in viz_nodes:
                for key, names in signature.get("affiliation_names", {}).items():
                    if key not in standalone_orgs:
                        joint_units[pid].update(names)
        seed_collaborations = defaultdict(list)
        viz_degree = Counter()
        for edge in viz_edges:
            viz_degree[edge["src"]] += graph_weight(edge, args)
            viz_degree[edge["dst"]] += graph_weight(edge, args)
        for seed in seeds:
            for edge in edges_by_person[seed]:
                other = edge["dst"] if edge["src"] == seed else edge["src"]
                if other in viz_nodes and not viz_degree[other]:
                    seed_collaborations[other].append({"name": name(seed), "weight": graph_weight(edge, args)})
        build_html(out / "network.html", viz_nodes, viz_edges, persons, cid, memberships,
                   viz_degree, args, factions, seeds=seeds, joint_units=joint_units,
                   paper_count=stats["works_in_network"],
                   pending_affiliations=bool(stats["works_pending_affiliation"]),
                   seed_collaborations=seed_collaborations)

    write_csv(out / "person_affiliations.csv", [
        {**rec, "name": name(pid), "orcid": persons[pid]["orcid"],
         "review_flag": persons[pid]["review_flag"]}
        for (pid, _), rec in sorted(person_orgs.items())
    ], ["person_id", "name", "orcid", "org_key", "org_name",
        "first_year", "last_year", "review_flag"])
    write_db(out / "factions.db", args, run_id, works, persons, person_orgs,
             work_persons, merge_log, edges, cid, degree, roles, method, stats, npapers, authorship,
             membership_rows)
    outputs = ["coauthors.csv", "edges.csv", "factions.csv", "faction_cross.csv",
               "seed_coauthors.csv", "merge_log.csv", "factions.db",
               "summary.json", "run.log"]
    outputs.extend(["authorship_roles.csv", "person_affiliations.csv", "faction_memberships.csv",
                    "affiliation_timeline.csv"])
    if not args.no_html:
        outputs.insert(6, "network.html")
    if args.reference_works:
        outputs.append("reference_coverage.csv")
    (out / "summary.json").write_text(
        json.dumps({"run_id": run_id, "query": {
            "author": args.author, "seed_name": getattr(args, "seed_name", None),
            "seed_work": args.seed_work,
            "reference_works": args.reference_works,
            "affiliation_history": args.affiliation_history,
            "org_parents": args.org_parents,
            "name_alias": getattr(args, "name_alias", None),
            "author_id": args.author_id,
            "org": args.org, "org_id": args.org_id,
            "affil_search": getattr(args, "affil_search", None),
            "journal": args.journal, "zone": args.zone,
            "from_year": args.from_year, "to_year": args.to_year,
            "topic": args.topic, "mode": args.mode, "hop": args.hop,
        }, "params": {
            "source": args.source, "min_collab": args.min_collab,
            "community": method, "resolution": args.resolution,
            "edge_weight": getattr(args, "edge_weight", "role"),
            "max_works": args.max_works,
            "orcid_policy": getattr(args, "orcid_policy", "warn"),
        }, "stats": stats, "outputs": outputs},
            ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# CLI / orchestration
# --------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Find co-authorship factions and collaboration counts within a scoped literature set.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--source", choices=["demo", "local", "openalex"], default="demo")
    p.add_argument("--input", help="long-table CSV for --source local")
    p.add_argument("--author", action="append",
                   help="seed author name (repeatable); in OpenAlex mode also resolves to author-id filters")
    p.add_argument("--seed-name", action="append",
                   help="seed author name WITHOUT adding an OpenAlex author-id filter (repeatable); "
                        "use when the person is split across several OpenAlex author IDs")
    p.add_argument("--seed-work", action="append", metavar="WORK_ID[@POSITION]",
                   help="verified publication or exact 1-based author position (repeatable); "
                        "retain only works attributed to that researcher")
    p.add_argument("--reference-works", metavar="CSV",
                   help="independent bibliography with work_id,source; requires --seed-work")
    p.add_argument("--author-id", action="append", help="OpenAlex author id (repeatable)")
    p.add_argument("--org", action="append", help="affiliation scope (repeatable)")
    p.add_argument("--org-id", action="append", help="OpenAlex/ROR institution id (repeatable)")
    p.add_argument("--affil-search", action="append",
                   help="match raw affiliation strings, e.g. a college/department name "
                        "that OpenAlex has no institution ID for (repeatable, OR)")
    p.add_argument("--journal", action="append", help="journal name or ISSN (repeatable)")
    p.add_argument("--source-id", action="append", help="OpenAlex source id (repeatable)")
    p.add_argument("--zone", action="append", help="zone/quartile value, e.g. Q1 (repeatable)")
    p.add_argument("--zone-map", help="CSV: issn,venue,zone,quartile")
    p.add_argument("--topic", action="append", help="OpenAlex free-text search (repeatable)")
    p.add_argument("--from-year", type=int)
    p.add_argument("--to-year", type=int)
    p.add_argument("--mode", choices=["scope", "seed", "all"], default="all")
    p.add_argument("--hop", type=int, default=1, help="neighbourhood radius in seed mode")
    p.add_argument("--min-collab", type=int, default=2,
                   help="minimum co-authored papers for peer discovery and drawn edges")
    p.add_argument("--edge-weight", choices=["role", "papers"], default="role",
                   help="visualization weight; threshold still uses paper counts")
    p.add_argument("--community", choices=["labelprop", "louvain"], default="louvain")
    p.add_argument("--resolution", type=float, default=1.0)
    p.add_argument("--org-parents", help="CSV of sourced subordinate-unit to parent mappings")
    p.add_argument("--affiliation-gaps", help="CSV of publication author positions pending affiliation review")
    p.add_argument("--max-works", type=int, default=500)
    p.add_argument("--max-orgs", type=int, default=8,
                   help="flag a person for review above this many affiliations")
    p.add_argument("--orcid-policy", choices=["warn", "strict"], default="warn",
                   help="warn: conflicting ORCIDs do not veto an affiliation match (merge + review flag); "
                        "strict: conflicting ORCIDs always split the person")
    p.add_argument("--max-nodes", type=int, default=600)
    p.add_argument("--max-edges", type=int, default=4000,
                   help="cap drawn edges (highest collaboration counts are kept)")
    p.add_argument("--no-html", action="store_true",
                   help="skip the interactive HTML graph for very large runs")
    p.add_argument("--api-key", default=os.environ.get("OPENALEX_API_KEY", ""))
    p.add_argument("--with-titles", action="store_true",
                   help="also fetch DOI and title (off by default: author data only)")
    p.add_argument("--name-alias", action="append",
                   help="normalize verified name spellings before disambiguation, "
                        "format: Canonical=Variant A|Variant B (repeatable)")
    p.add_argument("--alias-map", help="CSV: from_key,to_key (normalised org aliases)")
    p.add_argument("--affiliation-history", help="CSV of sourced employment, education or visiting dates")
    p.add_argument("--ignore-orgs", help="CSV: value,note (umbrella orgs excluded from evidence)")
    p.add_argument("--out", help="output directory (default: ./faction_output)")
    p.add_argument("--demo-out", action="store_true",
                   help="print the demo quick-start command and exit")
    args = p.parse_args(argv)
    if args.seed_work and len((args.author or []) + (args.seed_name or [])) != 1:
        p.error("--seed-work requires exactly one --seed-name or --author")
    if args.reference_works and (not args.seed_work or args.source != "local"):
        p.error("--reference-works requires --source local and --seed-work")
    return args


def check_reference_coverage(path, out, work_persons, evidence_ids, in_scope, seed):
    by_work = defaultdict(set)
    for row in read_csv(Path(path)):
        wid, source = (row.get(key, "").strip() for key in ("work_id", "source"))
        if not wid or not source:
            raise ValueError("--reference-works needs a work_id and independent source on each row")
        by_work[wid].add(source)
    if not by_work:
        raise ValueError("--reference-works is empty")
    rows = []
    for wid, sources in by_work.items():
        if wid not in evidence_ids:
            status = "missing_from_input"
        elif seed not in work_persons.get(wid, ()):
            status = "unresolved_attribution"
        elif wid not in in_scope:
            status = "outside_scope"
        else:
            status = "counted"
        rows.append({"work_id": wid, "source": " | ".join(sorted(sources)), "status": status})
    write_csv(out / "reference_coverage.csv", rows, ["work_id", "source", "status"])
    counts = Counter(row["status"] for row in rows)
    gaps = counts["missing_from_input"] + counts["unresolved_attribution"]
    if gaps:
        LOG.warning("%d known publications missing or unresolved. See reference_coverage.csv.", gaps)
    return {"status": "gaps_found" if gaps else "reference_list_reconciled",
            "reference_works": len(by_work), "counts": dict(counts)}


def setup_logging(out: Path, quiet=False):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    fh = logging.FileHandler(out / "run.log", mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    LOG.addHandler(fh)
    if not quiet:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        LOG.addHandler(sh)


def main(argv=None, *, quiet=False):
    args = parse_args(argv)
    if args.demo_out:
        print("python faction_query.py --source demo --author \"示例作者 A\" "
              "--zone Q1 --min-collab 2 --out ./faction_output")
        return 0
    out = Path(args.out).resolve() if args.out else Path.cwd() / "faction_output"
    out.mkdir(parents=True, exist_ok=True)
    setup_logging(out, quiet=quiet)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    LOG.info("=== academic-faction-finder run %s ===", run_id)
    LOG.info("Output: %s", out)

    # stage 1
    t0 = time.time()
    display_names = {}
    aliases = load_alias_map(ASSETS / "org_alias_template.csv", display_names)
    if args.alias_map:
        aliases.update(load_alias_map(args.alias_map, display_names))
    ignored = load_ignored(args.ignore_orgs or ASSETS / "org_ignored_template.csv")
    zone_map = load_zone_map(args.zone_map)
    LOG.info("Stage 1/6 query scope: author=%s org=%s journal=%s zone=%s years=%s..%s mode=%s",
             args.author, args.org, args.journal, args.zone,
             args.from_year, args.to_year, args.mode)
    if args.zone and not args.zone_map and args.source != "demo":
        LOG.warning("--zone given without --zone-map; only works carrying an inline "
                    "zone column can be filtered. See assets/zone_map_template.csv")

    # stage 2
    if args.source == "openalex":
        api_key = args.api_key or ""
        if not api_key:
            LOG.warning("No OpenAlex API key; anonymous daily allowance is small "
                        "(set OPENALEX_API_KEY or --api-key)")
        works, truncated = fetch_openalex(args, api_key, aliases)
        LOG.info("Stage 2/6 acquired %d works from OpenAlex (truncated=%s)",
                 len(works), truncated)
    else:
        truncated = False
        src = Path(args.input) if args.source == "local" else DEMO_PATH
        if not src.exists():
            raise FileNotFoundError(f"Input CSV not found: {src}")
        rows = read_csv(src)
        LOG.info("Stage 2/6 loaded %d long-table rows from %s", len(rows), src)
        works = rows_to_works(rows, require_verified_affiliations=args.source == "local")
    aliases = link_org_ids(works, aliases)
    display_names = {org_key(key[5:], "", aliases) if key.startswith("name:") else key: label
                     for key, label in display_names.items()}
    scoped_works = apply_scope(works, args, zone_map, aliases)
    LOG.info("Stage 2/6 works matching scope filters: %d", len(scoped_works))
    if not scoped_works and not args.reference_works:
        raise ValueError("No works matched the scope. Relax --zone/--org/--journal/year filters.")

    # When a target is anchored, out-of-scope signatures can establish identity.
    evidence_works = works if args.seed_work else scoped_works
    flat = works_to_rows(evidence_works)
    # stage 3
    (persons, person_orgs, work_persons, merge_log, seeds,
     merge_counts, flagged) = resolve_entities(flat, args, aliases, ignored)
    candidate_works = len(evidence_works)
    works = scoped_works
    coverage = {"status": "reference_list_not_checked"}
    if args.seed_work:
        seed = seeds[0]
        works = [w for w in works if seed in work_persons[w["work_id"]]]
        if args.reference_works:
            coverage = check_reference_coverage(
                args.reference_works, out, work_persons, {w["work_id"] for w in evidence_works},
                {w["work_id"] for w in works}, seed
            )
        if not works:
            raise ValueError("No publications of the verified author matched the reporting scope.")
        work_persons = {w["work_id"]: work_persons[w["work_id"]] for w in works}
        active = {pid for pids in work_persons.values() for pid in pids}
        persons = {pid: p for pid, p in persons.items() if pid in active}
        person_orgs = {key: rec for key, rec in person_orgs.items() if key[0] in active}
        LOG.info("Verified seed retained %d of %d candidate works", len(works), candidate_works)
    # stage 4
    authorship = {(row["work_id"], row["person_id"]): row["authorship"] for row in merge_log
                  if "authorship" in row and row["person_id"] in work_persons.get(row["work_id"], ())}
    gaps = read_csv(Path(args.affiliation_gaps)) if args.affiliation_gaps else []
    pending_positions = {(row["work_id"], row["author_order"]) for row in gaps if row["author_order"]}
    affiliation_authorship = {
        (wid, pid): signature for (wid, pid), signature in authorship.items()
        if args.source != "openalex" and any(signature["affiliation_names"].values())
        and (wid, str(signature["author_order"] or "")) not in pending_positions
    }
    missing = {wid for wid, _ in authorship.keys() - affiliation_authorship.keys()}
    missing.update(row["work_id"] for row in gaps)
    pending_works = sorted(missing & work_persons.keys())
    if pending_works:
        LOG.warning("%d in-scope papers await affiliation verification", len(pending_works))
    # Score against the full byline before excluding unverified author positions.
    score_authorships(work_persons, authorship)
    resolved_person_count = len(persons)
    work_persons = {wid: set() for wid in work_persons}
    for wid, pid in affiliation_authorship:
        work_persons[wid].add(pid)
    eligible = {pid for _, pid in affiliation_authorship}
    persons = {pid: person for pid, person in persons.items() if pid in eligible}
    seeds = [pid for pid in seeds if pid in eligible]
    dates_by_org = defaultdict(list)
    years = {work["work_id"]: work["year"] for work in works}
    for person in persons.values():
        person["org_display"] = set()
        person["org_keys"] = set()
        person["org_names"] = set()
    for (wid, pid), signature in affiliation_authorship.items():
        for key, names in signature["affiliation_names"].items():
            label = display_names.get(key)
            persons[pid]["org_display"].update([label] if label else names)
        persons[pid]["org_keys"].update(signature["observed_keys"])
        persons[pid]["org_names"].update(norm_org_name(name) for name in signature["affiliations"])
        for key in signature["observed_keys"]:
            dates = dates_by_org[pid, key]
            if years[wid]:
                dates.append(years[wid])
    person_orgs = {
        key: {**person_orgs[key], "first_year": min(dates, default=None),
              "last_year": max(dates, default=None)}
        for key, dates in dates_by_org.items()
    }
    edges = build_edges(work_persons, works, affiliation_authorship, seeds)
    # stage 5
    kept, sub, degree, nodes = graph_scope(edges, persons, seeds, args)
    peer_groups, method = detect_peer_groups(sub, seeds, args)
    parents = load_org_parents(args.org_parents, aliases)
    # A sole affiliation is established by one complete author byline, not a career history.
    standalone_orgs = {next(iter(units)) for signature in affiliation_authorship.values()
                       if len(units := signature["affiliation_names"]) == 1}
    cid, roles, memberships, factions, cross_rows = affiliation_communities(
        nodes, persons, works, affiliation_authorship, edges, sub, args, peer_groups,
        parents, standalone_orgs, display_names)
    # stage 6
    seed_set = set(seeds)
    restricted = any(getattr(args, flag) is not None for flag in (
        "from_year", "to_year", "org", "org_id", "affil_search", "journal", "source_id", "zone", "topic"))
    estimate_for = {pid for pid in seed_set if args.source == "local" and args.seed_work
                    and not restricted and not persons[pid]["orcid_conflict"]
                    and (persons[pid]["name_key"].startswith("verified:") or not persons[pid]["review_flag"])}
    timeline = affiliation_timeline(works, persons, person_orgs, affiliation_authorship, estimate_for,
                                    args.affiliation_history, aliases)
    write_csv(out / "affiliation_timeline.csv", timeline, TIMELINE_COLUMNS)
    stats = {
        "works_in_scope": len(works),
        "works_in_network": sum(bool(pids & nodes) for pids in work_persons.values()),
        "works_pending_affiliation": pending_works,
        "candidate_works": candidate_works,
        "reference_coverage": coverage,
        "long_table_rows": len(flat),
        "author_instances": sum(merge_counts.values()),
        "persons_after_disambiguation": resolved_person_count,
        "persons_in_network": len(nodes),
        "merge_decisions": merge_counts,
        "persons_flagged_for_review": sum(pid in persons for pid in flagged),
        "total_coauthor_pairs": len(edges),
        "pairs_kept_by_threshold": len(kept),
        "total_coauthorship_events": sum(e["n_papers"] for e in edges),
        "role_coverage": {field: dict(Counter(sig[field] for sig in affiliation_authorship.values()))
                          for field in ROLE_FIELDS},
        "factions_detected": len([r for r in factions if r["faction_id"] > 0]),
        "persons_without_faction": sum(1 for c in cid.values() if c <= 0),
        "persons_in_multiple_factions": sum(len(groups) > 1 for groups in memberships.values()),
        "affiliation_timeline": dict(Counter(row["basis"] for row in timeline)),
        "seed_persons": len(seeds),
        "seed_coauthor_rows": sum(1 for e in edges
                                  if e["src"] in seed_set or e["dst"] in seed_set),
        "truncated_by_max_works": truncated,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    export_all(out, args, run_id, works, persons, person_orgs, work_persons,
               merge_log, edges, kept, cid, degree, roles, method, seeds,
               factions, cross_rows, stats, memberships, nodes, affiliation_authorship,
               standalone_orgs=standalone_orgs)
    delivered = json.loads((out / "summary.json").read_text(encoding="utf-8"))["outputs"]
    LOG.info("Stage 6/6 export complete: %s", ", ".join(delivered))
    LOG.info("SUMMARY %s", json.dumps(stats, ensure_ascii=False))
    if not quiet:
        print("\n派系摘要：")
        for r in factions:
            print(f"  {r['faction_name']}: {r['size']} 人, 内部合著 {r['internal_collab_times']} 次, "
                  f"跨派系 {r['cross_faction_collab_times']} 次 | 核心: {r['core_members']}")
        print(f"\n输出目录: {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        LOG.exception("FAILED: %s", exc)
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
