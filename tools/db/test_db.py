#!/usr/bin/env python3
"""End-to-end check of the offline compound DB.

Uses ONLY the output files and an independent re-implementation of the key algorithms
(normF / formula parser / hillKey / nameKey / shard) exactly as the app implements them.

Usage:  python tools/db/test_db.py [db_dir]      (default: CC-uni-app-x/static/db)
Also writes tools/db/key_vectors.json - reference key values for checking the UTS port.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "CC-uni-app-x", "static", "db")

ELEM = json.load(open(os.path.join(DB, "elements.json"), encoding="utf-8"))
META = json.load(open(os.path.join(DB, "meta.json"), encoding="utf-8"))


# ------------------------------------------------------------------ key algorithms (spec)
def normF(s):
    out = []
    for ch in s:
        if ch.isspace() or ch == "﻿":
            continue
        o = ord(ch)
        if 0x2080 <= o <= 0x2089:
            ch = chr(48 + o - 0x2080)
        elif ch in ".*•⋅∙·":
            ch = "·"
        out.append(ch)
    return "".join(out)


def parse(s):
    s = normF(s)
    if not s:
        return None
    total = {}

    def add(dst, src, k):
        for e, n in src.items():
            dst[e] = dst.get(e, 0) + n * k

    for idx, part in enumerate(s.split("·")):
        mult = 1
        if idx > 0:
            j = 0
            while j < len(part) and part[j].isdigit():
                j += 1
            if j:
                mult, part = int(part[:j]), part[j:]
        if not part:
            return None
        stack, i = [{}], 0
        while i < len(part):
            c = part[i]
            if c in "([":
                stack.append({})
                i += 1
            elif c in ")]":
                if len(stack) < 2:
                    return None
                i += 1
                j = i
                while j < len(part) and part[j].isdigit():
                    j += 1
                k = int(part[i:j]) if j > i else 1
                i = j
                top = stack.pop()
                add(stack[-1], top, k)
            elif "A" <= c <= "Z":
                j = i + 1
                while j < len(part) and "a" <= part[j] <= "z":
                    j += 1
                sym = part[i:j]
                if sym not in ELEM:
                    return None
                i = j
                while j < len(part) and part[j].isdigit():
                    j += 1
                k = int(part[i:j]) if j > i else 1
                i = j
                stack[-1][sym] = stack[-1].get(sym, 0) + k
            else:
                return None
        if len(stack) != 1:
            return None
        add(total, stack[0], mult)
    return total


def hillKey(c):
    t = lambda e: e + (str(c[e]) if c[e] != 1 else "")
    if "C" in c:
        order = ["C"] + (["H"] if "H" in c else []) + sorted(e for e in c if e not in ("C", "H"))
    else:
        order = sorted(c)
    return "".join(t(e) for e in order)


def nameKey(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            ch = chr(o - 0xFEE0)
        elif o == 0x3000:
            ch = " "
        if "A" <= ch <= "Z":
            ch = ch.lower()
        if ch in " \t\r\n　 ":
            continue
        out.append(ch)
    return "".join(out)


def shard(key, n):
    h = 0
    b = key.encode("utf-16-le")
    for i in range(0, len(b), 2):
        h = (h * 31 + int.from_bytes(b[i:i + 2], "little")) % 1000000007
    return h % n


def mass(c):
    return round(sum(ELEM[e][1] * n for e, n in c.items()), 3)


# ------------------------------------------------------------------ DB access
_cache = {}


def load(rel):
    if rel not in _cache:
        _cache[rel] = json.load(open(os.path.join(DB, rel), encoding="utf-8"))
    return _cache[rel]


def rec(i):
    return load("c/%03d.json" % (i // META["chunk"]))[i % META["chunk"]]


def by_name(s):
    k = nameKey(s)
    return load("n/%03d.json" % shard(k, META["nameShards"])).get(k, [])


def by_formula(s):
    c = parse(s)
    if not c:
        return None, []
    k = hillKey(c)
    return k, load("h/%03d.json" % shard(k, META["formulaShards"])).get(k, [])


FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("  FAIL:", msg)
    return cond


# ------------------------------------------------------------------ 1. structure
def test_structure():
    print("[structure]")
    n = META["compounds"]
    nchunks = (n + META["chunk"] - 1) // META["chunk"]
    ranks, hill_of = [], []
    for k in range(nchunks):
        arr = load("c/%03d.json" % k)
        check(len(arr) == (META["chunk"] if k < nchunks - 1 else n - k * META["chunk"]), "chunk %d size" % k)
        for r in arr:
            check(len(r) == 6 and all(isinstance(x, str) for x in r[:4]) and isinstance(r[5], int), "record shape %r" % r)
            c = parse(r[0])
            check(c is not None and all(ord(ch) < 128 or ch == "·" for ch in r[0]), "formula parse/ASCII %r" % r[0])
            if c:
                check(abs(mass(c) - r[4]) < 1e-6, "M mismatch %r (%s)" % (r, mass(c)))
                hill_of.append(hillKey(c))
            else:
                hill_of.append(None)
            ranks.append(r[5])
    check(not os.path.exists(os.path.join(DB, "c", "%03d.json" % nchunks)), "extra chunk file")
    seen = set()
    for s in range(META["formulaShards"]):
        for k, ids in load("h/%03d.json" % s).items():
            check(shard(k, META["formulaShards"]) == s, "hill key %s in wrong shard" % k)
            check([ranks[i] for i in ids] == sorted((ranks[i] for i in ids), reverse=True), "hill %s not rank-sorted" % k)
            for i in ids:
                check(hill_of[i] == k, "id %d indexed under %s but formula gives %s" % (i, k, hill_of[i]))
                seen.add(i)
    check(len(seen) == n, "formula index covers %d of %d compounds" % (len(seen), n))
    nkeys = 0
    for s in range(META["nameShards"]):
        for k, ids in load("n/%03d.json" % s).items():
            nkeys += 1
            if not check(nameKey(k) == k and k, "name key not canonical %r" % k):
                continue
            check(shard(k, META["nameShards"]) == s, "name key %r in wrong shard" % k)
            check(all(0 <= i < n for i in ids) and len(set(ids)) == len(ids), "bad ids for %r" % k)
            check([ranks[i] for i in ids] == sorted((ranks[i] for i in ids), reverse=True), "name %r not rank-sorted" % k)
    print("  compounds %d, name keys %d, formula keys ok" % (n, nkeys))
    check(len(ELEM) == 118, "elements.json has 118 elements")


# ------------------------------------------------------------------ 2. curated reagents
REQUIRED = """NaCl 氯化钠, KCl 氯化钾, CaCl2 氯化钙, CaCl2·2H2O 二水氯化钙, MgCl2 氯化镁, MgCl2·6H2O 六水氯化镁,
MgSO4·7H2O 七水硫酸镁, Na2HPO4 磷酸氢二钠, Na2HPO4·12H2O 十二水磷酸氢二钠, KH2PO4 磷酸二氢钾, NaH2PO4 磷酸二氢钠,
NaH2PO4·2H2O 二水磷酸二氢钠, K2HPO4 磷酸氢二钾, CuSO4 硫酸铜, CuSO4·5H2O 五水硫酸铜, NaOH 氢氧化钠, KOH 氢氧化钾,
HCl 盐酸, H2SO4 硫酸, HNO3 硝酸, H3PO4 磷酸, CH3COOH 乙酸, CH3COONa 乙酸钠, CH3COONa·3H2O 三水乙酸钠, Na2CO3 碳酸钠,
NaHCO3 碳酸氢钠, AgNO3 硝酸银, BaCl2 氯化钡, BaCl2·2H2O 二水氯化钡, KMnO4 高锰酸钾, K2Cr2O7 重铬酸钾,
FeSO4·7H2O 七水硫酸亚铁, FeCl3 氯化铁, FeCl3·6H2O 六水氯化铁, Na2S2O3·5H2O 五水硫代硫酸钠, KI 碘化钾, KBr 溴化钾,
H2O2 过氧化氢, NaClO 次氯酸钠, NH4Cl 氯化铵, (NH4)2SO4 硫酸铵, Na2SO4 硫酸钠, ZnSO4·7H2O 七水硫酸锌, C6H12O6 葡萄糖,
C4H11NO3 Tris, C10H14N2Na2O8·2H2O EDTA 二钠, Pb(NO3)2 硝酸铅, Na2SO3 亚硫酸钠, Na2S 硫化钠, K2CrO4 铬酸钾,
Na2C2O4 草酸钠, H2C2O4·2H2O 二水草酸, KSCN 硫氰酸钾, KNO3 硝酸钾, NaNO3 硝酸钠, Ca(NO3)2 硝酸钙, CaCO3 碳酸钙,
C6H8O7 柠檬酸, C6H5Na3O7·2H2O 二水柠檬酸钠"""


def test_reagents():
    print("[reagents]")
    rg = load("reagents.json")
    dens = load("density.json")
    check(300 <= len(rg) <= 600, "reagent count %d" % len(rg))
    for it in rg:
        c = parse(it["f"])
        if not check(c is not None, "reagent formula %s" % it["f"]):
            continue
        check(abs(mass(c) - it["M"]) < 1e-6, "reagent M %s" % it["f"])
        check(it["kind"] in ("solid", "liquid"), "kind %s" % it["f"])
        if it["kind"] == "liquid":
            check(all(k in it for k in ("w", "wRange", "rho")) and it["wRange"][0] <= it["w"] <= it["wRange"][1],
                  "liquid fields %s" % it["f"])
        r = rec(it["id"])
        check(r[0] == it["f"] and r[1] == it["zh"] and r[5] >= 1_000_000, "reagent record %s -> %r" % (it["f"], r))
        ids = by_name(it["zh"])
        check(ids and rec(ids[0])[1] == it["zh"], "name %s first hit %r" % (it["zh"], rec(ids[0]) if ids else None))
        if it["cas"]:
            ids = by_name(it["cas"])
            check(it["id"] in ids, "CAS %s not indexed" % it["cas"])
    for k, d in dens.items():
        check(any(it["f"] == k for it in rg), "density key %s without reagent" % k)
        w = [p[0] for p in d["pts"]]
        check(w == sorted(w) and len(w) >= 5, "density %s points" % k)
    byf = {}
    for it in rg:
        byf.setdefault(it["f"], []).append(it)
    for item in REQUIRED.replace("\n", " ").split(","):
        f, zh = item.strip().split(" ", 1)
        ok = any(x["zh"] == zh for x in byf.get(f, []))
        check(ok, "required %s %s missing in reagents.json" % (f, zh))
        k, ids = by_formula(f)
        check(ids and rec(ids[0])[1] == zh, "formula %s first hit %r, want %s" % (f, rec(ids[0]) if ids else None, zh))


# ------------------------------------------------------------------ 3. spot checks
NAME_CASES = [  # query -> expected (formula of first hit)
    ("硫酸铜", "CuSO4"), ("五水硫酸铜", "CuSO4·5H2O"), ("胆矾", "CuSO4·5H2O"), ("蓝矾", "CuSO4·5H2O"),
    ("硫酸铜（五水）", "CuSO4·5H2O"), ("copper sulfate", "CuSO4"), ("Copper(II) Sulfate Pentahydrate", "CuSO4·5H2O"),
    ("7758-99-8", "CuSO4·5H2O"), ("7758-98-7", "CuSO4"), ("氯化钠", "NaCl"), ("sodium chloride", "NaCl"),
    ("葡萄糖", "C6H12O6"), ("Tris", "C4H11NO3"), ("三羟甲基氨基甲烷", "C4H11NO3"), ("EDTA二钠", "C10H14N2Na2O8·2H2O"),
    ("ＥＤＴＡ 二钠", "C10H14N2Na2O8·2H2O"), ("浓盐酸", "HCl"), ("盐酸", "HCl"), ("烧碱", "NaOH"), ("纯碱", "Na2CO3"),
    ("小苏打", "NaHCO3"), ("双氧水", "H2O2"), ("冰醋酸", "CH3COOH"), ("醋酸", "CH3COOH"), ("生石灰", "CaO"),
    ("熟石灰", "Ca(OH)2"), ("明矾", "KAl(SO4)2·12H2O"), ("绿矾", "FeSO4·7H2O"), ("皓矾", "ZnSO4·7H2O"),
    ("芒硝", "Na2SO4·10H2O"), ("大苏打", "Na2S2O3·5H2O"), ("海波", "Na2S2O3·5H2O"), ("石膏", "CaSO4·2H2O"),
    ("高锰酸钾", "KMnO4"), ("浓硫酸", "H2SO4"), ("浓硝酸", "HNO3"), ("氨水", "NH3"), ("浓氨水", "NH3"),
    ("酒精", "C2H5OH"), ("无水乙醇", "C2H5OH"), ("甘油", "C3H8O3"), ("SDS", "C12H25NaO4S"), ("HEPES", "C8H18N2O4S"),
    ("甘氨酸", "NH2CH2COOH"), ("尿素", "CO(NH2)2"), ("无水硫酸钠", "Na2SO4"), ("硼砂", "Na2B4O7·10H2O"),
    ("莫尔盐", "(NH4)2Fe(SO4)2·6H2O"), ("柠檬酸钠", "C6H5Na3O7·2H2O"), ("DMSO", "(CH3)2SO"),
    ("acetic acid", "CH3COOH"), ("hydrochloric acid", "HCl"), ("ethanol", "C2H5OH"), ("64-17-5", "C2H5OH"),
    ("β-巯基乙醇", "HSCH2CH2OH"), ("过硫酸铵", "(NH4)2S2O8"), ("考马斯亮蓝G-250", "C47H48N3NaO7S2"),
]
FORMULA_CASES = [  # formula -> (hillKey, expected zh of first hit)
    ("CuSO4·5H2O", "CuH10O9S", "五水硫酸铜"), ("CuSO4.5H2O", "CuH10O9S", "五水硫酸铜"),
    ("CuSO₄·5H₂O", "CuH10O9S", "五水硫酸铜"), ("CuSO4*5H2O", "CuH10O9S", "五水硫酸铜"),
    ("CH3COOH", "C2H4O2", "乙酸"), ("HCOOCH3", "C2H4O2", "乙酸"), ("NaCl", "ClNa", "氯化钠"),
    ("Na2HPO4", "HNa2O4P", "磷酸氢二钠"), ("Na2HPO4·12H2O", "H25Na2O16P", "十二水磷酸氢二钠"),
    ("C6H12O6", "C6H12O6", "葡萄糖"), ("C12H22O11", "C12H22O11", "蔗糖"), ("H2SO4", "H2O4S", "硫酸"),
    ("HCl", "ClH", "盐酸"), ("NH3", "H3N", "氨水"), ("C2H5OH", "C2H6O", "乙醇"), ("(NH4)2SO4", "H8N2O4S", "硫酸铵"),
    ("K3[Fe(CN)6]", "C6FeK3N6", "铁氰化钾"), ("K4[Fe(CN)6]·3H2O", "C6H6FeK4N6O3", "亚铁氰化钾"),
    ("C10H14N2Na2O8·2H2O", "C10H18N2Na2O10", "EDTA 二钠"), ("Ca(NO3)2·4H2O", "CaH8N2O10", "四水硝酸钙"),
    ("KMnO4", "KMnO4", "高锰酸钾"), ("H2O", "H2O", "水"), ("Fe2O3", "Fe2O3", "氧化铁"), ("NaOH", "HNaO", "氢氧化钠"),
    ("CH4", "CH4", "甲烷"), ("C6H6", "C6H6", "苯"),
]


def test_spot():
    print("[spot checks]")
    for q, want in NAME_CASES:
        ids = by_name(q)
        got = rec(ids[0])[0] if ids else None
        check(got == want, "name %r -> %r (want %r)" % (q, got, want))
    for f, hk, zh in FORMULA_CASES:
        k, ids = by_formula(f)
        check(k == hk, "hillKey(%s) = %s (want %s)" % (f, k, hk))
        got = rec(ids[0])[1] if ids else None
        check(got == zh, "formula %s -> %r (want %r)" % (f, got, zh))
    # glance at a few captions
    for q in ["NaCl", "CuSO4·5H2O", "CH3COOH", "C4H11NO3"]:
        k, ids = by_formula(q)
        r = rec(ids[0])
        print("   %-12s -> %s · %.2f g/mol" % (q, r[1], r[4]))
    rg = {x["zh"]: x for x in load("reagents.json")}
    for zh in ["盐酸", "硫酸", "硝酸", "磷酸", "乙酸", "氨水", "过氧化氢", "高氯酸", "氢氟酸", "甲醛", "乙醇"]:
        x = rg[zh]
        print("   %-6s %-8s w=%s%% %s rho=%s" % (zh, x["f"], x["w"], x["wRange"], x["rho"]))


def write_vectors():
    samples = ["CuSO4·5H2O", "CuSO₄·5H₂O", "CuSO4.5H2O", " CH3COOH ", "NaCl", "(NH4)2SO4", "K4[Fe(CN)6]·3H2O",
               "C10H14N2Na2O8·2H2O", "H2C2O4*2H2O", "Na2B4O7•10H2O"]
    names = ["硫酸铜", "五水硫酸铜", "Copper Sulfate", "ＥＤＴＡ　二钠", "7758-99-8", "Tris", "β-巯基乙醇", "\U0002CB3B"]
    vec = {"formulas": [], "names": []}
    for s in samples:
        c = parse(s)
        k = hillKey(c)
        vec["formulas"].append({"in": s, "normF": normF(s), "hillKey": k, "shard128": shard(k, 128), "M": mass(c)})
    for s in names:
        k = nameKey(s)
        vec["names"].append({"in": s, "nameKey": k, "shard256": shard(k, 256)})
    with open(os.path.join(HERE, "key_vectors.json"), "w", encoding="utf-8") as fo:
        json.dump(vec, fo, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    print("DB:", DB)
    test_structure()
    test_reagents()
    test_spot()
    write_vectors()
    print("\n%s (%d failures)" % ("FAILED" if FAILS else "ALL OK", len(FAILS)))
    sys.exit(1 if FAILS else 0)
