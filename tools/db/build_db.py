#!/usr/bin/env python3
"""Build the offline compound database for the chemistry calculator app.

Inputs (all cached, nothing is downloaded here):
  tools/db/_raw/wd_*.tsv        Wikidata extracts  (python tools/db/fetch_wikidata.py)
  tools/db/reagents_src.txt     hand-curated lab reagents
  tools/db/density_src.json     density-vs-concentration tables (with provenance)

Outputs (built into tools/db/_out/, installed into the app with --install):
  c/NNN.json   compound records  [formula, zh, en, cas, M, rank]
  n/NNN.json   name index        {nameKey: [id, ...]}   (256 shards)
  h/NNN.json   formula index     {hillKey: [id, ...]}   (128 shards)
  reagents.json, density.json, elements.json, meta.json
  tools/fonts/extra_chars.txt   (merged: every CJK character used in the outputs)

Usage:
  python tools/db/build_db.py              # build into tools/db/_out
  python tools/db/test_db.py tools/db/_out # verify
  python tools/db/build_db.py --install    # (re)build, then replace CC-uni-app-x/static/db in one step
  python tools/db/build_db.py --install-only   # just install the existing _out
"""
import collections
import datetime
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RAW = os.path.join(HERE, "_raw")
OUT = os.path.join(HERE, "_out")                               # build output (not watched by HBuilderX)
APP_DB = os.path.join(ROOT, "CC-uni-app-x", "static", "db")    # installed copy (only with --install)
FONT_EXTRA = os.path.join(ROOT, "tools", "fonts", "extra_chars.txt")

CHUNK = 1000
NAME_SHARDS = 256
FORMULA_SHARDS = 128
CURATED_BONUS = 1_000_000

# --------------------------------------------------------------------------------------------
# Elements: Z, symbol, atomic weight, zh, en.
# Weights: CIAAW/IUPAC abridged standard atomic weights (5 significant figures; conventional
# values for elements with an interval: H, Li, B, C, N, O, Mg, Si, S, Cl, Ar, Br, Tl, Pb).
# Zr uses the 2024 revision (91.222). Elements without a standard atomic weight: mass number
# of the longest-lived / conventionally quoted isotope.
ELEMENTS = [
    (1, "H", 1.008, "氢", "hydrogen"), (2, "He", 4.0026, "氦", "helium"),
    (3, "Li", 6.94, "锂", "lithium"), (4, "Be", 9.0122, "铍", "beryllium"),
    (5, "B", 10.81, "硼", "boron"), (6, "C", 12.011, "碳", "carbon"),
    (7, "N", 14.007, "氮", "nitrogen"), (8, "O", 15.999, "氧", "oxygen"),
    (9, "F", 18.998, "氟", "fluorine"), (10, "Ne", 20.180, "氖", "neon"),
    (11, "Na", 22.990, "钠", "sodium"), (12, "Mg", 24.305, "镁", "magnesium"),
    (13, "Al", 26.982, "铝", "aluminium"), (14, "Si", 28.085, "硅", "silicon"),
    (15, "P", 30.974, "磷", "phosphorus"), (16, "S", 32.06, "硫", "sulfur"),
    (17, "Cl", 35.45, "氯", "chlorine"), (18, "Ar", 39.95, "氩", "argon"),
    (19, "K", 39.098, "钾", "potassium"), (20, "Ca", 40.078, "钙", "calcium"),
    (21, "Sc", 44.956, "钪", "scandium"), (22, "Ti", 47.867, "钛", "titanium"),
    (23, "V", 50.942, "钒", "vanadium"), (24, "Cr", 51.996, "铬", "chromium"),
    (25, "Mn", 54.938, "锰", "manganese"), (26, "Fe", 55.845, "铁", "iron"),
    (27, "Co", 58.933, "钴", "cobalt"), (28, "Ni", 58.693, "镍", "nickel"),
    (29, "Cu", 63.546, "铜", "copper"), (30, "Zn", 65.38, "锌", "zinc"),
    (31, "Ga", 69.723, "镓", "gallium"), (32, "Ge", 72.630, "锗", "germanium"),
    (33, "As", 74.922, "砷", "arsenic"), (34, "Se", 78.971, "硒", "selenium"),
    (35, "Br", 79.904, "溴", "bromine"), (36, "Kr", 83.798, "氪", "krypton"),
    (37, "Rb", 85.468, "铷", "rubidium"), (38, "Sr", 87.62, "锶", "strontium"),
    (39, "Y", 88.906, "钇", "yttrium"), (40, "Zr", 91.222, "锆", "zirconium"),
    (41, "Nb", 92.906, "铌", "niobium"), (42, "Mo", 95.95, "钼", "molybdenum"),
    (43, "Tc", 97, "锝", "technetium"), (44, "Ru", 101.07, "钌", "ruthenium"),
    (45, "Rh", 102.91, "铑", "rhodium"), (46, "Pd", 106.42, "钯", "palladium"),
    (47, "Ag", 107.87, "银", "silver"), (48, "Cd", 112.41, "镉", "cadmium"),
    (49, "In", 114.82, "铟", "indium"), (50, "Sn", 118.71, "锡", "tin"),
    (51, "Sb", 121.76, "锑", "antimony"), (52, "Te", 127.60, "碲", "tellurium"),
    (53, "I", 126.90, "碘", "iodine"), (54, "Xe", 131.29, "氙", "xenon"),
    (55, "Cs", 132.91, "铯", "caesium"), (56, "Ba", 137.33, "钡", "barium"),
    (57, "La", 138.91, "镧", "lanthanum"), (58, "Ce", 140.12, "铈", "cerium"),
    (59, "Pr", 140.91, "镨", "praseodymium"), (60, "Nd", 144.24, "钕", "neodymium"),
    (61, "Pm", 145, "钷", "promethium"), (62, "Sm", 150.36, "钐", "samarium"),
    (63, "Eu", 151.96, "铕", "europium"), (64, "Gd", 157.25, "钆", "gadolinium"),
    (65, "Tb", 158.93, "铽", "terbium"), (66, "Dy", 162.50, "镝", "dysprosium"),
    (67, "Ho", 164.93, "钬", "holmium"), (68, "Er", 167.26, "铒", "erbium"),
    (69, "Tm", 168.93, "铥", "thulium"), (70, "Yb", 173.05, "镱", "ytterbium"),
    (71, "Lu", 174.97, "镥", "lutetium"), (72, "Hf", 178.49, "铪", "hafnium"),
    (73, "Ta", 180.95, "钽", "tantalum"), (74, "W", 183.84, "钨", "tungsten"),
    (75, "Re", 186.21, "铼", "rhenium"), (76, "Os", 190.23, "锇", "osmium"),
    (77, "Ir", 192.22, "铱", "iridium"), (78, "Pt", 195.08, "铂", "platinum"),
    (79, "Au", 196.97, "金", "gold"), (80, "Hg", 200.59, "汞", "mercury"),
    (81, "Tl", 204.38, "铊", "thallium"), (82, "Pb", 207.2, "铅", "lead"),
    (83, "Bi", 208.98, "铋", "bismuth"), (84, "Po", 209, "钋", "polonium"),
    (85, "At", 210, "砹", "astatine"), (86, "Rn", 222, "氡", "radon"),
    (87, "Fr", 223, "钫", "francium"), (88, "Ra", 226, "镭", "radium"),
    (89, "Ac", 227, "锕", "actinium"), (90, "Th", 232.04, "钍", "thorium"),
    (91, "Pa", 231.04, "镤", "protactinium"), (92, "U", 238.03, "铀", "uranium"),
    (93, "Np", 237, "镎", "neptunium"), (94, "Pu", 244, "钚", "plutonium"),
    (95, "Am", 243, "镅", "americium"), (96, "Cm", 247, "锔", "curium"),
    (97, "Bk", 247, "锫", "berkelium"), (98, "Cf", 251, "锎", "californium"),
    (99, "Es", 252, "锿", "einsteinium"), (100, "Fm", 257, "镄", "fermium"),
    (101, "Md", 258, "钔", "mendelevium"), (102, "No", 259, "锘", "nobelium"),
    (103, "Lr", 266, "铹", "lawrencium"), (104, "Rf", 267, "\U0002CB3B", "rutherfordium"),
    (105, "Db", 268, "\U0002CB4A", "dubnium"), (106, "Sg", 269, "\U0002CB73", "seaborgium"),
    (107, "Bh", 270, "\U0002CB5B", "bohrium"), (108, "Hs", 269, "\U0002CB76", "hassium"),
    (109, "Mt", 278, "鿏", "meitnerium"), (110, "Ds", 281, "\U0002B7FC", "darmstadtium"),
    (111, "Rg", 282, "\U0002CB2D", "roentgenium"), (112, "Cn", 285, "鿔", "copernicium"),
    (113, "Nh", 286, "鿭", "nihonium"), (114, "Fl", 289, "\U0002B4E7", "flerovium"),
    (115, "Mc", 290, "镆", "moscovium"), (116, "Lv", 293, "\U0002B7F7", "livermorium"),
    (117, "Ts", 294, "鿬", "tennessine"), (118, "Og", 294, "鿫", "oganesson"),
]
WEIGHT = {e[1]: e[2] for e in ELEMENTS}
assert len(WEIGHT) == 118

# --------------------------------------------------------------------------------------------
# Canonical keys (the app re-implements exactly these)
DOT_CHARS = {".", "*", "•", "⋅", "∙", "·"}
# whitespace = JavaScript \s
WS = set(" \f\n\r\t\v      　﻿") | {chr(c) for c in range(0x2000, 0x200B)}


def normF(s):
    out = []
    for ch in s:
        if ch in WS:
            continue
        o = ord(ch)
        if 0x2080 <= o <= 0x2089:
            ch = chr(o - 0x2080 + 48)
        elif ch in DOT_CHARS:
            ch = "·"
        out.append(ch)
    return "".join(out)


def _digits(s, i):
    j = i
    while j < len(s) and "0" <= s[j] <= "9":
        j += 1
    return (int(s[i:j]), j) if j > i else (None, i)


def _parse_part(part):
    stack = [collections.Counter()]
    i, n = 0, len(part)
    while i < n:
        c = part[i]
        if c in "([":
            stack.append(collections.Counter())
            i += 1
        elif c in ")]":
            if len(stack) == 1:
                return None
            k, i = _digits(part, i + 1)
            k = 1 if k is None else k
            if k == 0:
                return None
            top = stack.pop()
            for el, v in top.items():
                stack[-1][el] += v * k
        elif "A" <= c <= "Z":
            j = i + 1
            while j < n and "a" <= part[j] <= "z":
                j += 1
            sym = part[i:j]
            if sym not in WEIGHT:
                return None
            k, i = _digits(part, j)
            k = 1 if k is None else k
            if k == 0:
                return None
            stack[-1][sym] += k
        else:
            return None
    if len(stack) != 1:
        return None
    return stack[0]


def parse_formula(s):
    """Element counts (hydrate water included) or None if unparseable."""
    s = normF(s)
    if not s:
        return None
    total = collections.Counter()
    for idx, part in enumerate(s.split("·")):
        mult = 1
        if idx > 0:
            k, j = _digits(part, 0)
            if k is not None:
                if k == 0:
                    return None
                mult, part = k, part[j:]
        if not part:
            return None
        c = _parse_part(part)
        if c is None or not c:
            return None
        for el, v in c.items():
            total[el] += v * mult
    return total


def hill_key(counts):
    def term(el):
        n = counts[el]
        return el + (str(n) if n != 1 else "")
    els = [e for e in counts if counts[e] > 0]
    if "C" in els:
        rest = sorted(e for e in els if e not in ("C", "H"))
        order = ["C"] + (["H"] if "H" in els else []) + rest
    else:
        order = sorted(els)
    return "".join(term(e) for e in order)


def molar_mass(counts):
    return round(sum(WEIGHT[e] * n for e, n in counts.items()), 3)


NK_WS = {" ", "\t", "\r", "\n", "　", " "}


def name_key(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            ch = chr(o - 0xFEE0)
        elif o == 0x3000:
            ch = " "
        if "A" <= ch <= "Z":
            ch = chr(ord(ch) + 32)
        if ch in NK_WS:
            continue
        out.append(ch)
    return "".join(out)


def shard(key, n):
    h = 0
    b = key.encode("utf-16-le")
    for i in range(0, len(b), 2):
        h = (h * 31 + (b[i] | (b[i + 1] << 8))) % 1000000007
    return h % n


# --------------------------------------------------------------------------------------------
# helpers
def cas_ok(cas):
    m = re.fullmatch(r"(\d{2,7})-(\d{2})-(\d)", cas)
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum((i + 1) * int(d) for i, d in enumerate(digits)) % 10 == int(m.group(3))


def is_hill_string(s, counts):
    return re.sub(r"(?<=[A-Za-z])1(?![0-9])", "", s) == hill_key(counts)


CJK_RE = re.compile("[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]")
HAN_ONLY_PUNCT = re.compile("[　-〿＀-￯]")

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
except Exception:  # pragma: no cover
    _T2S = None
    print("WARN: opencc not available; traditional Chinese labels will not be converted "
          "(pip install opencc-python-reimplemented)")

# Taiwan chemistry nomenclature -> mainland (applied after t2s on converted traditional names)
TW_FIX = [("醯", "酰"), ("過", "过"), ("过锰酸", "高锰酸"), ("过氯酸", "高氯酸"), ("过碘酸", "高碘酸"),
          ("过溴酸", "高溴酸"), ("过铼酸", "高铼酸"), ("过锝酸", "高锝酸"), ("矽", "硅"), ("鎝", "锝")]
T2S_KEEP = set("鎓鏻噁")  # onium / phosphonium / oxazole-type names are written this way in mainland usage
_t2s_cache = {}


def to_simplified(s):
    if s in _t2s_cache:
        return _t2s_cache[s]
    r = _T2S.convert(s) if _T2S else s
    if len(r) == len(s):  # keep characters that mainland chemistry nomenclature still uses
        r = "".join(o if o in T2S_KEEP else c for o, c in zip(s, r))
    r = r.replace("𫍩", "鎓").replace("𫍸", "鏻")
    for a, b in TW_FIX:
        r = r.replace(a, b)
    _t2s_cache[s] = r
    return r


def clean_name(s):
    s = re.sub(r"\s+", " ", s.replace(" ", " ")).strip()
    return s


# --------------------------------------------------------------------------------------------
# Wikidata
ZH_PRIORITY = ["zh-cn", "zh-hans", "zh", "zh-sg", "zh-my", "zh-hant", "zh-tw", "zh-hk", "zh-mo"]
ZH_SIMPLIFIED = {"zh-cn", "zh-hans", "zh-sg", "zh-my"}


def read_tsv(name):
    path = os.path.join(RAW, name)
    if not os.path.exists(path):
        sys.exit("missing %s - run: python tools/db/fetch_wikidata.py" % path)
    with open(path, encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\n").split("\t")


def zh_norm(lang, s):
    # zh-cn / zh-hans labels on Wikidata occasionally contain Traditional characters too,
    # so everything goes through t2s (identity on Simplified text).
    return to_simplified(clean_name(s))


# isotopically labelled species (their P274 often looks like the unlabelled formula)
ISO_EN = re.compile(r"<sup>|\[\s*\d{1,3}m?\s*[A-Z][a-z]?\s*\]|\(\s*\d{2,3}m?\s*(?:C|N|O|F|P|I|Tc|Ga|In|Tl|Xe|Kr|Rb|Cu|Zr|Lu|Br|Y)\s*\)|"
                    r"\b(?:hydrogen|carbon|nitrogen|oxygen|fluorine|phosphorus|sulfur|iodine|technetium|gallium|indium|"
                    r"thallium|rubidium|xenon|krypton)-\d{1,3}\b|tritiated|deuterated|\blabell?ed\b|\bdeuterium\b|\btritium\b", re.I)
ISO_ZH = re.compile(r"<sup>|[氢碳氮氧氟磷硫碘锝镓铟铊铷氙氪]-\d{1,3}|\[\s*\d{1,3}m?\s*[A-Z][a-z]?\s*\]|氘|氚")

BAD_ALIAS = re.compile(r"\d{4,}|[:=#@\\/|]|^inchi|^unii|^nsc\b|^einecs|^ec\s|^cas\b|^chebi|^cid\b", re.I)


def load_wikidata():
    items = {}
    for qid, f, sl, st, ch in read_tsv("wd_items.tsv"):
        it = items.get(qid)
        if it is None:
            it = items[qid] = {"q": qid, "formulas": [], "sl": int(float(sl or 0)),
                               "st": int(float(st or 0)), "charged": False,
                               "labels": {}, "aliases": collections.defaultdict(list), "cas": [], "zhwiki": ""}
        if f and f not in it["formulas"]:
            it["formulas"].append(f)
        if ch:
            try:
                if float(ch) != 0:
                    it["charged"] = True
            except ValueError:
                it["charged"] = True
    for qid, lang, lab in read_tsv("wd_labels.tsv"):
        if qid in items and lab:
            items[qid]["labels"][lang] = lab
    for qid, lang, al in read_tsv("wd_aliases.tsv"):
        if qid in items and al:
            items[qid]["aliases"][lang].append(al)
    for qid, cas in read_tsv("wd_cas.tsv"):
        if qid in items and cas and cas not in items[qid]["cas"]:
            items[qid]["cas"].append(cas)
    for qid, title in read_tsv("wd_zhwiki.tsv"):
        if qid in items:
            items[qid]["zhwiki"] = title
    rpath = os.path.join(RAW, "zhwiki_redirects.tsv")
    if os.path.exists(rpath):
        by_title = collections.defaultdict(list)
        for title, rd in read_tsv("zhwiki_redirects.tsv"):
            by_title[title].append(rd)
        for it in items.values():
            if it["zhwiki"]:
                it["redirects"] = by_title.get(it["zhwiki"], [])
    else:
        print("WARN: zhwiki_redirects.tsv missing (run fetch_wikidata.py) - building without redirects")
    cls_label = {c: l for c, l in read_tsv("wd_p31_labels.tsv")}
    for qid, c in read_tsv("wd_p31.tsv"):
        if qid in items:
            items[qid].setdefault("classes", []).append(cls_label.get(c, c))
    return items


# instance-of classes that are not weighable pure compounds (isotopes, alloys, mixtures, polymers ...)
BAD_CLASS = re.compile(r"isotope|nuclide|nuclear isomer|exotic atom|alloy|cupronickel|steel|bronze|brass|"
                       r"combination drug|material|disambiguation|wikimedia|ambiguous|scholarly|"
                       r"currency|price|^colou?r$|trademark|brand name|model series|chemical process|protein|"
                       r"peptide|enzyme|antibod|asparaginase|polymer|plastic|polysaccharide|macromolecule|"
                       r"chemical group|alkyl group|acyl group|alkenyl group|radical|misidentified|hypothetical|"
                       r"commodity|coating", re.I)


def is_alloy_notation(f):
    parts = normF(f).split("·")
    return len(parts) > 1 and all(re.fullmatch(r"[A-Z][a-z]?", p) for p in parts)


def choose_formula(it):
    """Pick (display formula, counts) for a Wikidata item, or None."""
    parsed = []
    for f in it["formulas"]:
        c = parse_formula(f)
        if c:
            parsed.append((normF(f), c))
    if not parsed:
        return None
    by_hill = collections.defaultdict(list)
    for f, c in parsed:
        by_hill[hill_key(c)].append((f, c))
    # most frequent hill, then fewest atoms
    best = sorted(by_hill.values(), key=lambda v: (-len(v), sum(v[0][1].values())))[0]
    counts = best[0][1]
    # prefer a non-Hill (condensed / hydrate) spelling among the P274 values
    cands = [f for f, _ in best]
    non_hill = [f for f in cands if not is_hill_string(f, counts)]
    disp = sorted(non_hill, key=lambda f: ("·" not in f, len(f)))[0] if non_hill else cands[0]
    if is_hill_string(disp, counts):
        # look for a conventional spelling among labels/aliases (e.g. CuSO4·5H2O, CH3COOH)
        alts = []
        for lang, vals in it["aliases"].items():
            for a in vals:
                a2 = normF(a)
                if len(a2) > 30 or not re.fullmatch(r"[A-Za-z0-9()\[\]·]+", a2):
                    continue
                if re.fullmatch(r"\[[^\[\]]*\]|\([^()]*\)", a2):  # "[SH2]", "[CO2]" coordination-style wrappers
                    continue
                ca = parse_formula(a2)
                if ca and ca == counts and not is_hill_string(a2, counts):
                    alts.append(a2)
        if alts:
            disp = sorted(set(alts), key=lambda f: ("·" not in f, len(f), f))[0]
    return disp, counts


# --------------------------------------------------------------------------------------------
# Chinese / English name variants
CN_NUM = "一二两三四五六七八九十半"
HYD_A = re.compile("^([%s]+)水(合)?(.{2,})$" % CN_NUM)             # 五水(合)硫酸铜
HYD_B = re.compile("^(.{2,}?)([%s]+)水合物$" % CN_NUM)              # 硫酸铜五水合物
HYD_C = re.compile("^(.{2,}?)[（(]([%s]+)水(合物)?[)）]$" % CN_NUM)  # 硫酸铜（五水）
ROMAN = re.compile(r"\s*\((?:I|II|III|IV|V|VI|VII|VIII)\)")


def hydrate_base(zh):
    """('五', '硫酸铜') for any of the recognised hydrate spellings, else None."""
    for rx, gi, gb in ((HYD_A, 1, 3), (HYD_B, 2, 1), (HYD_C, 2, 1)):
        m = rx.match(zh)
        if m:
            base = m.group(gb)
            if base.startswith("合"):
                return None
            return m.group(gi), base
    return None


HYDRATE_EN = re.compile(r"(?<!an)hydrate\b|\bhydrated\b", re.I)
ANHYD = re.compile(r"^无水|[（(]无水[)）]|\banhydrous\b", re.I)


def names_hydrate_ok(n, comp_is_hydrate):
    says_h = bool(hydrate_base(n)) or bool(HYDRATE_EN.search(n))
    says_anh = bool(ANHYD.search(n))
    if says_h and not comp_is_hydrate:
        return False
    if says_anh and comp_is_hydrate:
        return False
    return True


def zh_variants(zh, is_hydrate):
    out = set()
    if not is_hydrate:
        return out
    hb = hydrate_base(zh)
    if hb:
        n, base = hb
        out |= {n + "水" + base, n + "水合" + base, base + "(" + n + "水)", base + n + "水合物"}
    out.discard(zh)
    return out


def en_variants(en, curated=False):
    out = set()
    if not en:
        return out
    s = ROMAN.sub("", en).strip()
    if s and s != en:
        out.add(s)
    if curated:
        for base in [en] + list(out):
            if "sulf" in base:
                out.add(base.replace("sulf", "sulph"))
            elif "sulph" in base:
                out.add(base.replace("sulph", "sulf"))
            if "aluminium" in base:
                out.add(base.replace("aluminium", "aluminum"))
            if "caesium" in base:
                out.add(base.replace("caesium", "cesium"))
    out.discard(en)
    return out


# --------------------------------------------------------------------------------------------
# curated reagents
def load_curated():
    path = os.path.join(HERE, "reagents_src.txt")
    out = []
    for ln, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = [x.strip() for x in line.split("|")]
        if len(p) < 5:
            sys.exit("reagents_src.txt:%d: too few fields" % ln)
        f, zh, aliases, en, cas = p[:5]
        prio = 0
        if zh.startswith("!"):
            prio, zh = 1, zh[1:]
        r = {"f": f, "zh": zh, "alias": [a.strip() for a in aliases.split(";") if a.strip()],
             "en": en, "cas": cas, "kind": "solid", "prio": prio, "line": ln}
        if len(p) > 5 and p[5].upper() == "L":
            r["kind"] = "liquid"
            r["w"] = float(p[6])
            lo, hi = p[7].split("-")
            r["wRange"] = [float(lo), float(hi)]
            r["rho"] = p[8]
            if len(p) > 9 and p[9]:
                r["note"] = p[9]
        elif len(p) > 9 and p[9]:
            r["note"] = p[9]
        c = parse_formula(f)
        if not c:
            sys.exit("reagents_src.txt:%d: unparseable formula %s" % (ln, f))
        if normF(f) != f or not re.fullmatch(r"[A-Za-z0-9()\[\]·]+", f):
            sys.exit("reagents_src.txt:%d: formula must be plain ASCII with · : %r" % (ln, f))
        if cas and not cas_ok(cas):
            sys.exit("reagents_src.txt:%d: bad CAS check digit %s" % (ln, cas))
        r["counts"] = c
        r["hill"] = hill_key(c)
        r["M"] = molar_mass(c)
        out.append(r)
    return out


def num(x):
    """JSON-friendly number: ints stay ints."""
    return int(x) if float(x).is_integer() else x


def interp(pts, w):
    pts = sorted(pts)
    if w <= pts[0][0]:
        return pts[0][1] if w == pts[0][0] else None
    for (w0, r0), (w1, r1) in zip(pts, pts[1:]):
        if w0 <= w <= w1:
            return r0 + (r1 - r0) * (w - w0) / (w1 - w0) if w1 > w0 else r0
    return None


# label densities used if a table is missing (g/mL, 20 °C)
RHO_FALLBACK = {"HCl": 1.19, "H2SO4": 1.84, "HNO3": 1.40, "H3PO4": 1.69, "CH3COOH": 1.05, "NH3": 0.91,
                "H2O2": 1.11, "HClO4": 1.67, "HBr": 1.49, "HI": 1.50, "HF": 1.13, "HCOOH": 1.20,
                "HCHO": 1.08, "CH3OH": 0.791, "C2H5OH": 0.789, "HOCH2CH2OH": 1.113, "C3H8O3": 1.261}


# --------------------------------------------------------------------------------------------
def main():
    t0 = datetime.datetime.now()
    items = load_wikidata()
    print("wikidata items loaded:", len(items))

    # ---------------- Wikidata compounds
    comps = []  # dicts: formula zh en cas(list) counts names(set) base_rank q
    stats = collections.Counter()
    for q, it in items.items():
        if it["charged"]:
            stats["skip_charged"] += 1
            continue
        if any(BAD_CLASS.search(c) for c in it.get("classes", [])):
            stats["skip_class"] += 1
            continue
        if any(is_alloy_notation(f) for f in it["formulas"]) or "/" in it["labels"].get("en", ""):
            stats["skip_mixture"] += 1
            continue
        if ISO_EN.search(it["labels"].get("en", "")) or \
                any(ISO_ZH.search(v) for k, v in it["labels"].items() if k.startswith("zh")):
            stats["skip_isotope"] += 1
            continue
        fc = choose_formula(it)
        if not fc:
            stats["skip_formula"] += 1
            continue
        disp, counts = fc
        labels = it["labels"]
        zh = ""
        for lang in ZH_PRIORITY:
            if labels.get(lang):
                zh = zh_norm(lang, labels[lang])
                break
        if not zh and it["zhwiki"]:
            zh = to_simplified(clean_name(it["zhwiki"]))
        en = clean_name(labels.get("en", ""))
        if re.search(r"[;${}^]", en):  # auto-generated PubChem-style names ("azane;cobalt(2+);dichloride")
            en = ""
        if not zh and not en:
            stats["skip_noname"] += 1
            continue
        names = set()
        for lang in ZH_PRIORITY:
            if labels.get(lang):
                names.add(zh_norm(lang, labels[lang]))
            for a in it["aliases"].get(lang, []):
                a = zh_norm(lang, a)
                if a and not parse_formula(a) and not BAD_ALIAS.search(a):
                    names.add(a)
        if it["zhwiki"]:
            names.add(to_simplified(clean_name(it["zhwiki"])))
        if en:
            names.add(en)
        popular = it["sl"] >= 5 or bool(zh)
        n_en = 0
        for a in it["aliases"].get("en", []):
            a = clean_name(a)
            if not a or len(a) > 60 or BAD_ALIAS.search(a) or parse_formula(a) or re.search(r"[;${}^]", a):
                continue
            names.add(a)
            n_en += 1
            if n_en >= (8 if popular else 3):
                break
        for a in it.get("redirects", []):  # zh.wikipedia redirect titles (trivial / common names)
            a = to_simplified(clean_name(a))
            if a and len(a) <= 40 and not parse_formula(a) and not BAD_ALIAS.search(a):
                names.add(a)
        # hydrate consistency: never index "五水…"/"…hydrate" names on an anhydrous record and vice versa
        comp_h = ("·" in disp and "H2O" in disp) or bool(hydrate_base(zh)) or bool(HYDRATE_EN.search(en))
        names = {n for n in names if names_hydrate_ok(n, comp_h)}
        cas = [c for c in it["cas"] if cas_ok(c)]
        base = it["sl"] * 16 + (8 if zh else 0) + (4 if cas else 0) + min(it["st"] // 10, 3)
        comps.append({"q": q, "qn": int(q[1:]), "formula": disp, "zh": zh, "en": en, "cas": cas,
                      "counts": counts, "hill": hill_key(counts), "names": names, "base": base,
                      "rank": base, "curated": None, "hydrate": "·" in disp or None})
        stats["kept"] += 1
    print("wikidata:", dict(stats))

    # ---------------- curated reagents: merge into Wikidata records or add new ones
    curated = load_curated()
    by_cas = collections.defaultdict(list)
    by_hill = collections.defaultdict(list)
    for c in comps:
        for x in c["cas"]:
            by_cas[x].append(c)
        by_hill[c["hill"]].append(c)
    used = set()
    warnings = []
    new_records = []
    for r in curated:
        rnames = {name_key(x) for x in [r["zh"], r["en"]] + r["alias"]}
        cands = [c for c in by_cas.get(r["cas"], []) if c["hill"] == r["hill"] and c["q"] not in used]
        other = [c for c in by_cas.get(r["cas"], []) if c["hill"] != r["hill"]]
        if other and not cands:
            warnings.append("CAS %s (%s %s): Wikidata item(s) with that CAS have formula %s" % (
                r["cas"], r["f"], r["zh"], ", ".join("%s=%s" % (c["q"], c["hill"]) for c in other[:3])))
        for c in other:
            ce, re_ = set(c["counts"]), set(r["counts"])
            if not (ce <= re_ or re_ <= ce) and ({name_key(n) for n in c["names"]} & rnames) and c["q"] not in used:
                used.add(c["q"])
                c["absorbed"] = True
                r.setdefault("absorbed", []).append(c)
                warnings.append("absorbed %s (formula %s looks wrong) into %s %s" % (c["q"], c["formula"], r["f"], r["zh"]))
        if not cands:  # fall back: same formula and a matching name
            cands = [c for c in by_hill.get(r["hill"], []) if c["q"] not in used and
                     ({name_key(n) for n in c["names"]} & rnames)]
        if cands:
            cands.sort(key=lambda c: (-(name_key(c["zh"]) in rnames or name_key(c["en"]) in rnames),
                                      -c["base"], c["qn"]))
            c = cands[0]
            used.add(c["q"])
            if c["cas"] and r["cas"] not in c["cas"]:
                warnings.append("note: %s %s merged with %s (CAS %s) by name/formula" % (
                    r["f"], r["zh"], c["q"], "/".join(c["cas"])))
        else:
            c = {"q": None, "qn": 10 ** 9, "names": set(), "cas": [],
                 "base": max([a["base"] for a in r.get("absorbed", [])] or [0])}
            new_records.append(c)
            warnings.append("new (no Wikidata match): %s %s %s" % (r["f"], r["zh"], r["cas"]))
        c.update({"formula": r["f"], "zh": r["zh"], "en": r["en"], "counts": r["counts"],
                  "hill": r["hill"], "curated": r,
                  "rank": CURATED_BONUS + r["prio"] * 100000 + min(c["base"], 99999)})
        if r["cas"]:
            c["cas"] = [r["cas"]] + [x for x in c["cas"] if x != r["cas"]]
        for a in r.get("absorbed", []):
            c["names"] |= a["names"]
            c["cas"] += [x for x in a["cas"] if x not in c["cas"]]
        c["names"] |= {r["zh"], r["en"]} | set(r["alias"]) | en_variants(r["en"], True)
        for a in r["alias"]:
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,()'\-]+", a):
                c["names"] |= en_variants(a, True)
        r["rec"] = c
    comps.extend(new_records)
    comps = [c for c in comps if not c.get("absorbed")]
    for w in warnings:
        print("  ", w)

    # ---------------- generated variants
    zh_nonhyd = collections.defaultdict(list)
    for c in comps:
        c["names"] |= en_variants(c["en"])
        c["is_h"] = "·" in c["formula"] or (
            c["counts"].get("O", 0) >= 1 and c["counts"].get("H", 0) >= 2 and hydrate_base(c["zh"] or "") is not None)
        if c["zh"]:
            for n in list(c["names"]):
                if CJK_RE.search(n):
                    c["names"] |= zh_variants(n, c["is_h"])
        if c["zh"] and not c["is_h"]:
            zh_nonhyd[c["zh"]].append(c)
    for c in comps:
        hb = hydrate_base(c["zh"]) if c["zh"] and c["is_h"] else None
        if hb:
            for base_c in zh_nonhyd.get(hb[1], []):
                base_c["names"] |= {"无水" + hb[1], hb[1] + "(无水)"}

    # ---------------- ids by rank
    comps.sort(key=lambda c: (-c["rank"], c["qn"], c["formula"]))
    for i, c in enumerate(comps):
        c["id"] = i

    # ---------------- write outputs
    if os.path.isdir(OUT):
        for sub in ("c", "n", "h"):
            shutil.rmtree(os.path.join(OUT, sub), ignore_errors=True)
    for sub in ("c", "n", "h"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)

    def dump(path, obj):
        with open(path, "w", encoding="utf-8", newline="\n") as fo:
            json.dump(obj, fo, ensure_ascii=False, separators=(",", ":"))

    records = []
    for c in comps:
        records.append([c["formula"], c["zh"] or "", c["en"] or "", c["cas"][0] if c["cas"] else "",
                        molar_mass(c["counts"]), int(c["rank"])])
    for k in range(0, len(records), CHUNK):
        dump(os.path.join(OUT, "c", "%03d.json" % (k // CHUNK)), records[k:k + CHUNK])

    order = {c["id"]: (-c["rank"], c["id"]) for c in comps}
    # a name explicitly listed for one curated reagent is not indexed for *other* curated reagents
    # (e.g. Wikidata lists 胆矾 as an alias of anhydrous CuSO4; the curated list assigns it to CuSO4·5H2O)
    claimed = collections.defaultdict(set)
    for r in curated:
        for x in [r["zh"], r["en"], r["cas"]] + r["alias"]:
            claimed[name_key(x)].add(id(r))
    name_idx = collections.defaultdict(set)
    dropped = 0
    for c in comps:
        keys = {name_key(n) for n in c["names"] if n} | {name_key(x) for x in c["cas"]}
        if c["curated"] is not None:
            own = id(c["curated"])
            bad = {k for k in keys if claimed.get(k) and own not in claimed[k]}
            dropped += len(bad)
            keys -= bad
        for k in keys:
            if k:
                name_idx[k].add(c["id"])
    form_idx = collections.defaultdict(set)
    for c in comps:
        form_idx[c["hill"]].add(c["id"])

    def write_index(idx, n, sub):
        shards = [dict() for _ in range(n)]
        for k in sorted(idx):
            shards[shard(k, n)][k] = sorted(idx[k], key=lambda i: order[i])
        for s in range(n):
            dump(os.path.join(OUT, sub, "%03d.json" % s), shards[s])

    write_index(name_idx, NAME_SHARDS, "n")
    write_index(form_idx, FORMULA_SHARDS, "h")

    # ---------------- density tables
    density = {}
    dsrc_path = os.path.join(HERE, "density_src.json")
    if os.path.exists(dsrc_path):
        dsrc = json.load(open(dsrc_path, encoding="utf-8"))
        for key, d in dsrc.items():
            pts = sorted([[num(w), num(r)] for w, r in d["pts"]])
            density[key] = {"zh": d["zh"], "T": num(d.get("T", 20)), "pts": pts}
    else:
        print("WARN: density_src.json missing -> density.json will be empty")

    # ---------------- reagents.json
    reagents = []
    for r in curated:
        item = {"f": r["f"], "zh": r["zh"], "alias": r["alias"], "en": r["en"], "cas": r["cas"],
                "M": r["M"], "kind": r["kind"]}
        if r["kind"] == "liquid":
            item["w"] = num(r["w"])
            item["wRange"] = [num(x) for x in r["wRange"]]
            rho = r["rho"]
            tab = density.get(r["f"])
            if rho == "=":
                v = interp(tab["pts"], r["w"]) if tab else None
                if v is None:
                    v = RHO_FALLBACK[r["f"]]
                    print("  rho fallback for %s: %s" % (r["f"], v))
                rho = round(v, 3)
            else:
                rho = float(rho)
                if tab:
                    v = interp(tab["pts"], r["w"])
                    if v is not None and abs(v - rho) > 0.02:
                        print("  WARN rho %s: label %.3f vs table %.3f" % (r["f"], rho, v))
            item["rho"] = num(rho)
        if r.get("note"):
            item["note"] = r["note"]
        item["id"] = r["rec"]["id"]
        reagents.append(item)
    dump(os.path.join(OUT, "reagents.json"), reagents)
    missing = [k for k in density if k not in {r["f"] for r in curated}]
    if missing:
        print("WARN: density keys without a reagent entry:", missing)
    dump(os.path.join(OUT, "density.json"), density)

    # ---------------- elements.json, meta.json
    dump(os.path.join(OUT, "elements.json"), {e[1]: [e[0], e[2], e[3], e[4]] for e in ELEMENTS})
    meta = {"version": datetime.date.today().isoformat(), "compounds": len(records),
            "nameShards": NAME_SHARDS, "formulaShards": FORMULA_SHARDS, "chunk": CHUNK,
            "curated": len(curated), "nameKeys": len(name_idx), "formulaKeys": len(form_idx),
            "sources": [
                "Wikidata (CC0) via QLever SPARQL: P274 chemical formula, P231 CAS, labels/aliases "
                "(en, zh variants; Traditional converted with OpenCC t2s), sitelink counts",
                "Hand-curated lab reagent list (tools/db/reagents_src.txt)",
                "Density tables: see tools/db/SOURCES.md (CRC Handbook / Perry's / cited reproductions)",
                "Atomic weights: CIAAW/IUPAC abridged standard atomic weights",
            ]}
    dump(os.path.join(OUT, "meta.json"), meta)

    # ---------------- font chars
    chars = set()

    def collect(obj):
        if isinstance(obj, str):
            for ch in obj:
                if CJK_RE.match(ch) or HAN_ONLY_PUNCT.match(ch):
                    chars.add(ch)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                collect(k)
                collect(v)
        elif isinstance(obj, list):
            for v in obj:
                collect(v)
    collect(records)
    collect(list(name_idx.keys()))
    collect(reagents)
    collect(density)
    collect({e[1]: e[3] for e in ELEMENTS})
    # merge: keep every other line of the file, replace only our own (marked) line
    mark = ("# chemistry DB: auto-generated by tools/db/build_db.py - every CJK character used in "
            "static/db (next line is rewritten on each build)")
    kept, skip = [], False
    if os.path.exists(FONT_EXTRA):
        for line in open(FONT_EXTRA, encoding="utf-8").read().splitlines():
            if skip:
                skip = False
                continue
            if line.strip() == mark:
                skip = True
                continue
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    with open(FONT_EXTRA, "w", encoding="utf-8", newline="\n") as fo:
        for line in kept + [mark, "".join(sorted(chars))]:
            fo.write(line + "\n")

    # ---------------- report
    total = 0
    for dp, dn, fn in os.walk(OUT):
        for f in fn:
            total += os.path.getsize(os.path.join(dp, f))
    print("compounds: %d (curated %d, new %d) | name keys %d | formula keys %d | CJK chars %d" % (
        len(records), len(curated), len(new_records), len(name_idx), len(form_idx), len(chars)))
    print("static/db size: %.2f MB  (%s)" % (total / 1e6, datetime.datetime.now() - t0))


def install():
    """Replace CC-uni-app-x/static/db with _out in one step (HBuilderX watches static/)."""
    stage = os.path.join(HERE, "_stage_db")
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(OUT, stage)                       # stage on the same drive, outside the app
    try:
        if os.path.isdir(APP_DB):
            old = os.path.join(HERE, "_old_db")
            shutil.rmtree(old, ignore_errors=True)
            os.rename(APP_DB, old)                    # one move out ...
            os.rename(stage, APP_DB)                  # ... one move in
            shutil.rmtree(old, ignore_errors=True)
        else:
            os.rename(stage, APP_DB)
        print("installed (rename) ->", APP_DB)
        return
    except OSError as e:  # folder locked (e.g. HBuilderX watcher holds a handle): mirror it in one robocopy run
        print("rename not possible (%s); using robocopy /MIR" % e)
    shutil.rmtree(stage, ignore_errors=True)
    if os.name == "nt":
        import subprocess
        rc = subprocess.run(["robocopy", OUT, APP_DB, "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
                             "/R:3", "/W:1"]).returncode
        if rc >= 8:
            sys.exit("robocopy failed with code %d" % rc)
    else:
        shutil.rmtree(APP_DB, ignore_errors=True)
        shutil.copytree(OUT, APP_DB)
    print("installed (mirror) ->", APP_DB)


if __name__ == "__main__":
    if "--install-only" not in sys.argv:
        main()
    if "--install" in sys.argv or "--install-only" in sys.argv:
        install()
