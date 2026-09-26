#!/usr/bin/env python3
"""Fetch raw compound data from Wikidata (via the QLever SPARQL endpoint).

Writes compact TSV files into tools/db/_raw/ :
  wd_items.tsv    qid  formula  sitelinks  statements  charge(P2200)
  wd_labels.tsv   qid  lang  label
  wd_aliases.tsv  qid  lang  alias
  wd_cas.tsv      qid  cas
  wd_zhwiki.tsv   qid  title           (zh.wikipedia article title)
  wd_p31.tsv      qid  class-qid       (instance of, used to drop isotopes, alloys, polymers ...)
  wd_p31_labels.tsv class-qid  en-label
  zhwiki_redirects.tsv  article-title  redirect-title   (zh.wikipedia redirect+page SQL dumps)

Candidate set = items with a chemical formula (P274) AND at least one of:
  * >= 1 Wikimedia sitelink
  * a Chinese label or alias (any zh variant)
  * an EC number (P232)  -> commercially registered substance

Usage:  python tools/db/fetch_wikidata.py [--force]
Re-running skips files that already exist unless --force is given.
"""
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "_raw")
ENDPOINT = "https://qlever.cs.uni-freiburg.de/api/wikidata"
UA = "ChemCalcOfflineDB-builder/1.0 (offline chemistry calculator; python-requests)"

PREFIX = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

ZH = '"zh","zh-hans","zh-cn","zh-hant","zh-tw","zh-hk","zh-sg","zh-my","zh-mo"'
LANGS = '"en",' + ZH

# NB: QLever currently mis-evaluates FILTER(?s >= 1) directly on wikibase:sitelinks,
# the BIND(...) FILTER(?b) form works.
CAND = """{ SELECT DISTINCT ?i WHERE {
    ?i wdt:P274 ?f0 .
    { ?i wikibase:sitelinks ?s0 BIND(?s0 >= 1 AS ?b0) FILTER(?b0) }
    UNION { ?i rdfs:label ?l0 FILTER(LANG(?l0) IN (%s)) }
    UNION { ?i skos:altLabel ?a0 FILTER(LANG(?a0) IN (%s)) }
    UNION { ?i wdt:P232 ?ec0 }
} }""" % (ZH, ZH)

QUERIES = {
    "wd_items.tsv": (
        ["i", "f", "sl", "st", "ch"],
        "SELECT ?i ?f ?sl ?st ?ch WHERE { %s ?i wdt:P274 ?f . ?i wikibase:sitelinks ?sl . "
        "OPTIONAL { ?i wikibase:statements ?st } OPTIONAL { ?i wdt:P2200 ?ch } }" % CAND,
    ),
    "wd_labels.tsv": (
        ["i", "@l", "l"],
        "SELECT ?i ?l WHERE { %s ?i rdfs:label ?l FILTER(LANG(?l) IN (%s)) }" % (CAND, LANGS),
    ),
    "wd_aliases.tsv": (
        ["i", "@a", "a"],
        "SELECT ?i ?a WHERE { %s ?i skos:altLabel ?a FILTER(LANG(?a) IN (%s)) }" % (CAND, LANGS),
    ),
    "wd_cas.tsv": (
        ["i", "c"],
        "SELECT ?i ?c WHERE { %s ?i wdt:P231 ?c }" % CAND,
    ),
    "wd_p31.tsv": (
        ["i", "c"],
        "SELECT ?i ?c WHERE { %s ?i wdt:P31 ?c }" % CAND,
    ),
    "wd_p31_labels.tsv": (
        ["c", "l"],
        "SELECT DISTINCT ?c ?l WHERE { %s ?i wdt:P31 ?c . ?c rdfs:label ?l FILTER(LANG(?l)=\"en\") }" % CAND,
    ),
    "wd_zhwiki.tsv": (
        ["i", "t"],
        "SELECT ?i ?t WHERE { %s ?art schema:about ?i ; schema:isPartOf <https://zh.wikipedia.org/> ; "
        "schema:name ?t }" % CAND,
    ),
}


def clean(v):
    return v.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def run(query):
    for attempt in range(5):
        try:
            r = requests.post(
                ENDPOINT,
                data={"query": PREFIX + query},
                headers={"Accept": "application/sparql-results+json", "User-Agent": UA},
                timeout=600,
            )
            if r.status_code == 200:
                return r.json()
            print("  HTTP", r.status_code, r.text[:300])
        except Exception as e:  # network hiccup
            print("  error:", e)
        time.sleep(10 * (attempt + 1))
    raise SystemExit("query failed repeatedly")


DUMP = "https://dumps.wikimedia.org/zhwiki/latest/zhwiki-latest-%s.sql.gz"


def download(url, dest):
    if os.path.exists(dest):
        return
    print("  download", url)
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": UA}) as r:
        r.raise_for_status()
        with open(dest + ".part", "wb") as fo:
            for chunk in r.iter_content(1 << 20):
                fo.write(chunk)
    os.replace(dest + ".part", dest)


def sql_rows(path, row_re):
    """Yield regex matches for every row tuple of the INSERT statements in a MediaWiki SQL dump."""
    import gzip
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("INSERT INTO"):
                yield from row_re.finditer(line)


def sql_unescape(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "0": ""}.get(m.group(1), m.group(1)), s)


def fetch_zhwiki_redirects(force):
    """Redirect titles pointing at the zh.wikipedia articles of our items (trivial/common names).

    Uses the zhwiki `redirect` and `page` SQL dumps (the API is heavily rate limited for anonymous clients).
    The dumps are deleted after extraction; the result is cached in zhwiki_redirects.tsv.
    """
    path = os.path.join(RAW, "zhwiki_redirects.tsv")
    if os.path.exists(path) and not force:
        print("skip (cached) zhwiki_redirects.tsv")
        return
    targets = set()
    with open(os.path.join(RAW, "wd_zhwiki.tsv"), encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) == 2 and p[1]:
                targets.add(p[1].replace(" ", "_"))
    red_gz = os.path.join(RAW, "zhwiki-redirect.sql.gz")
    page_gz = os.path.join(RAW, "zhwiki-page.sql.gz")
    download(DUMP % "redirect", red_gz)
    download(DUMP % "page", page_gz)
    # redirect: (rd_from, rd_namespace, 'rd_title', 'rd_interwiki', 'rd_fragment')
    rd_re = re.compile(r"\((\d+),(-?\d+),'((?:[^'\\]|\\.)*)',")
    src = {}
    for m in sql_rows(red_gz, rd_re):
        if m.group(2) == "0":
            t = sql_unescape(m.group(3))
            if t in targets:
                src[int(m.group(1))] = t
    print("  redirects into our articles:", len(src))
    # page: (page_id, page_namespace, 'page_title', page_is_redirect, ...)
    pg_re = re.compile(r"\((\d+),(-?\d+),'((?:[^'\\]|\\.)*)',(\d),")
    n = 0
    with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as fo:
        for m in sql_rows(page_gz, pg_re):
            pid = int(m.group(1))
            if pid in src and m.group(2) == "0":
                fo.write("%s\t%s\n" % (clean(src[pid].replace("_", " ")),
                                       clean(sql_unescape(m.group(3)).replace("_", " "))))
                n += 1
    os.replace(path + ".tmp", path)
    for pth in (red_gz, page_gz):
        os.remove(pth)
    print("  %d redirects" % n)


def main():
    force = "--force" in sys.argv
    os.makedirs(RAW, exist_ok=True)
    for fname, (cols, q) in QUERIES.items():
        path = os.path.join(RAW, fname)
        if os.path.exists(path) and not force:
            print("skip (cached)", fname)
            continue
        print("query", fname, "...")
        t0 = time.time()
        js = run(q)
        rows = js["results"]["bindings"]
        n = 0
        with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as fo:
            for b in rows:
                out = []
                for c in cols:
                    if c.startswith("@"):
                        v = b.get(c[1:], {}).get("xml:lang", "")
                    else:
                        v = b.get(c, {}).get("value", "")
                        if c in ("i", "c"):
                            v = v.rsplit("/", 1)[-1]
                    out.append(clean(v))
                fo.write("\t".join(out) + "\n")
                n += 1
        os.replace(path + ".tmp", path)
        print("  %d rows in %.1fs" % (n, time.time() - t0))
        time.sleep(2)  # be polite
    fetch_zhwiki_redirects(force)


if __name__ == "__main__":
    main()
