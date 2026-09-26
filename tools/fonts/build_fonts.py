#!/usr/bin/env python3
"""
Build the static font assets for the uni-app x (Android) app.

Outputs (CC-uni-app-x/static/fonts/):
    ns4.ttf ns5.ttf ns7.ttf   Noto Serif SC, wght 400/500/700 (static instances of the
                              Google Fonts variable font, subset to GB2312 + app chars)
    px4.ttf px5.ttf px6.ttf   IBM Plex Serif Regular/Medium/SemiBold (full coverage)

Reports (tools/fonts/):
    metrics.json    vertical metrics + Chrome "line-height: normal" multipliers
    coverage.json   per-character glyph coverage (and what Chrome actually used in the
                    design, taking Google Fonts' unicode-range slicing into account)

Sources are the exact files Google Fonts serves, from the google/fonts GitHub repo.
Downloads are cached in tools/fonts/_work/ (use --refresh to re-download).

Run (from anywhere):
    E:/IDEProjects/Chemistry_caculator/tools/fonts/.venv/Scripts/python.exe \
        E:/IDEProjects/Chemistry_caculator/tools/fonts/build_fonts.py

Setup (once):
    python -m venv tools/fonts/.venv
    tools/fonts/.venv/Scripts/python -m pip install -i https://pypi.org/simple fonttools
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

try:
    from fontTools import subset
    from fontTools import version as FONTTOOLS_VERSION
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
except ImportError:  # pragma: no cover
    sys.exit("fontTools missing. Run:  python -m venv tools/fonts/.venv && "
             "tools/fonts/.venv/Scripts/python -m pip install -i https://pypi.org/simple fonttools")

# --------------------------------------------------------------------------- paths
HERE = Path(__file__).resolve().parent                 # tools/fonts
ROOT = HERE.parent.parent                              # E:/IDEProjects/Chemistry_caculator
APP = ROOT / "CC-uni-app-x"
DESIGN = ROOT / "_design"
WORK = HERE / "_work"
OUT = APP / "static" / "fonts"
EXTRA_CHARS = HERE / "extra_chars.txt"
METRICS_JSON = HERE / "metrics.json"
COVERAGE_JSON = HERE / "coverage.json"

RAW = "https://raw.githubusercontent.com/google/fonts/{ref}/ofl/{path}"
NOTO_SRC = "notoserifsc/NotoSerifSC%5Bwght%5D.ttf"
NOTO_LOCAL = "NotoSerifSC[wght].ttf"
PLEX = {  # stem -> (weight, style name, repo path)
    "px4": (400, "Regular", "ibmplexserif/IBMPlexSerif-Regular.ttf"),
    "px5": (500, "Medium", "ibmplexserif/IBMPlexSerif-Medium.ttf"),
    "px6": (600, "SemiBold", "ibmplexserif/IBMPlexSerif-SemiBold.ttf"),
}
WEIGHT_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium",
                600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}
# The CSS the design HTML loads (fetched with a Chrome UA to get the unicode-range slices).
GF_CSS_URL = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:wght@400;500;600"
              "&family=Noto+Serif+SC:wght@400;500;600;700&display=swap")
CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# 118 element names, in atomic-number order (Z = index + 1).
ELEMENTS = ("氢氦锂铍硼碳氮氧氟氖钠镁铝硅磷硫氯氩钾钙钪钛钒铬锰铁钴镍铜锌镓锗砷硒溴氪铷锶钇锆铌钼"
            "锝钌铑钯银镉铟锡锑碲碘氙铯钡镧铈镨钕钷钐铕钆铽镝钬铒铥镱镥铪钽钨铼锇铱铂金汞铊铅铋钋"
            "砹氡钫镭锕钍镤铀镎钚镅锔锫锎锿镄钔锘铹𬬻𬭊𬭳𬭛𬭶鿏𫟼𬬭鿔鿭𫓧镆𫟷鿬鿫")
# Spot checks of the newer (post-2000) element characters against their code points.
ELEMENT_SPOT = {104: 0x2CB3B, 105: 0x2CB4A, 106: 0x2CB73, 107: 0x2CB5B, 108: 0x2CB76,
                109: 0x9FCF, 110: 0x2B7FC, 111: 0x2CB2D, 112: 0x9FD4, 113: 0x9FED,
                114: 0x2B4E7, 115: 0x9546, 116: 0x2B7F7, 117: 0x9FEC, 118: 0x9FEB}

RANGES = [  # (a) ranges kept in Noto if the font has them
    (0x0020, 0x007E), (0x00A0, 0x00FF), (0x0370, 0x03FF), (0x2000, 0x206F),
    (0x2070, 0x209F), (0x2190, 0x21FF), (0x2200, 0x22FF), (0x25A0, 0x25FF),
    (0x3000, 0x303F), (0xFF00, 0xFFEF),
]
COVERAGE_LIST = "₀₁₂₃₄₅₆₇₈₉⁺⁻²³·×≈≥≤～~→µμρ−–—…▲△°％≈±÷⁰¹"

# Layout features to keep in Noto (default-on horizontal features + CJK spacing ones).
NOTO_FEATURES = ["ccmp", "locl", "liga", "clig", "calt", "rlig", "rvrn", "kern", "mark",
                 "mkmk", "chws", "halt", "palt"]
DROP_TABLES = ["BASE", "vhea", "vmtx", "VORG", "STAT", "DSIG", "meta", "JSTF", "LTSH",
               "PCLT", "hdmx", "VDMX"]
KEEP_NAME_IDS = [0, 5, 7, 8, 9, 10, 11, 12, 13, 14]    # copyright/version/license/etc.

SCAN_EXCLUDE_DIRS = {"unpackage", "node_modules", ".git", ".hbuilderx", ".idea", ".vscode"}


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------- download
def fetch(url: str, dest: Path, refresh: bool, headers: dict | None = None) -> Path:
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last = None
    for attempt in range(1, 4):
        try:
            log(f"  downloading {url}")
            req = urllib.request.Request(url, headers=headers or {"User-Agent": "build_fonts.py"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as fh:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
            os.replace(tmp, dest)
            return dest
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  attempt {attempt} failed: {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"download failed: {url}: {last}")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- charset
def gb2312_chars() -> tuple[list[str], list[str]]:
    """All valid 2-byte GB2312 codes -> (hanzi 0xB0A1-0xF7FE, symbols 0xA1A1-0xA9FE)."""
    def run(r1, r2):
        out = []
        for b1 in range(r1, r2 + 1):
            for b2 in range(0xA1, 0xFF):
                try:
                    out.append(bytes([b1, b2]).decode("gb2312"))
                except UnicodeDecodeError:
                    pass
        return out
    return run(0xB0, 0xF7), run(0xA1, 0xA9)


def non_ascii(text: str) -> set[str]:
    return {c for c in text if ord(c) > 0x7F and unicodedata.category(c) not in ("Cc", "Cs")}


def iter_files(base: Path, patterns: list[str]):
    for pat in patterns:
        for p in base.glob(pat):
            if p.is_file() and not (SCAN_EXCLUDE_DIRS & set(p.relative_to(base).parts)):
                yield p


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace").replace("\ufffd", "")


def json_strings(obj, acc: list[str]):
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            acc.append(str(k))
            json_strings(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            json_strings(v, acc)


def scan_sources() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    design = set()
    for p in iter_files(DESIGN, ["**/*.html"]):
        design |= non_ascii(read_text(p))
    found["design_html"] = design

    app = set()
    for p in iter_files(APP, ["**/*.uvue", "**/*.uts", "pages.json"]):
        app |= non_ascii(read_text(p))
    found["app_uvue_uts"] = app

    db = set()
    db_dir = APP / "static" / "db"
    if db_dir.is_dir():
        for p in iter_files(db_dir, ["**/*.json"]):
            raw = read_text(p)
            try:
                acc: list[str] = []
                json_strings(json.loads(raw), acc)
                db |= non_ascii("".join(acc))
            except ValueError:  # file being written / not strict JSON: scan raw + \u escapes
                log(f"  WARN: {p} is not valid JSON, scanning raw text")
                txt = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), raw)
                db |= non_ascii(txt)
    found["db_json"] = db

    extra = set()
    if EXTRA_CHARS.exists():
        for line in read_text(EXTRA_CHARS).splitlines():
            if not line.lstrip().startswith("#"):
                extra |= {c for c in line if unicodedata.category(c) not in ("Cc", "Cs")}
    found["extra_chars"] = extra
    return found


# --------------------------------------------------------------------------- font ops
def feature_lookup_mapping(font: TTFont, tag: str) -> dict[str, str]:
    """glyph -> glyph for single/alternate substitutions under GSUB feature `tag`."""
    if "GSUB" not in font:
        return {}
    gsub = font["GSUB"].table
    if not gsub.FeatureList:
        return {}
    idx = set()
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag == tag:
            idx.update(fr.Feature.LookupListIndex)
    mapping: dict[str, str] = {}
    for li in sorted(idx):
        lk = gsub.LookupList.Lookup[li]
        for st in lk.SubTable:
            typ = lk.LookupType
            if typ == 7:
                typ, st = st.ExtensionLookupType, st.ExtSubTable
            if typ == 1:
                mapping.update(st.mapping)
            elif typ == 3:
                mapping.update({g: alts[0] for g, alts in st.alternates.items() if alts})
    return mapping


def freeze_feature(font: TTFont, tag: str = "tnum") -> dict[str, str]:
    """Remap cmap entries through the feature's substitutions (so it is on by default)."""
    mapping = feature_lookup_mapping(font, tag)
    changed: dict[str, str] = {}
    if not mapping:
        return changed
    for t in font["cmap"].tables:
        if not t.isUnicode():
            continue
        for cp, g in list(t.cmap.items()):
            if g in mapping:
                t.cmap[cp] = mapping[g]
                changed[f"U+{cp:04X}"] = f"{g}->{mapping[g]}"
    return changed


def subset_options(features) -> subset.Options:
    o = subset.Options()
    o.layout_features = features
    o.hinting = False
    o.drop_tables = sorted(set(o.drop_tables) | set(DROP_TABLES))
    o.name_IDs = KEEP_NAME_IDS
    o.name_languages = [0x0409]
    o.name_legacy = False
    o.glyph_names = False
    o.notdef_outline = True
    o.recalc_bounds = True
    o.recalc_timestamp = False
    o.prune_unicode_ranges = True
    o.legacy_kern = False
    return o


def vmetrics(font: TTFont) -> dict:
    h, o = font["hhea"], font["OS/2"]
    return {"hhea": [h.ascent, h.descent, h.lineGap],
            "typo": [o.sTypoAscender, o.sTypoDescender, o.sTypoLineGap],
            "win": [o.usWinAscent, o.usWinDescent],
            "fsSel_bit7": bool(o.fsSelection & (1 << 7))}


def match_win_metrics(font: TTFont):
    """Make hhea (used by Android/FreeType) equal to the OS/2 win metrics.

    The design was viewed in Chrome on Windows, where DirectWrite lays IBM Plex
    Serif out with usWinAscent/usWinDescent (1150/286) instead of hhea
    (1025/-275). Copying the win values into hhea makes Android place Plex
    glyphs exactly as the design rendered them.
    """
    h, o = font["hhea"], font["OS/2"]
    h.ascent, h.descent, h.lineGap = o.usWinAscent, -o.usWinDescent, 0


def finalize(font: TTFont, stem: str, weight: int, style17: str, src_version: str):
    """Rename families to the file stem, set weight/style bits, drop leftovers."""
    for tag in ("STAT", "fvar", "avar", "gvar", "HVAR", "MVAR", "cvar", "vhea", "vmtx"):
        if tag in font:
            del font[tag]
    bold = weight >= 700
    style2 = "Bold" if bold else "Regular"
    name = font["name"]
    name.names = [n for n in name.names
                  if n.nameID not in (1, 2, 3, 4, 6, 16, 17, 18, 21, 22, 25)]
    for nid, val in {1: stem, 2: style2, 3: f"{stem};{src_version};cc-build",
                     4: stem, 6: stem, 16: stem, 17: style17}.items():
        name.setName(val, nid, 3, 1, 0x409)
    os2 = font["OS/2"]
    os2.usWeightClass = weight
    fs = os2.fsSelection & ~0b1100001          # clear ITALIC(0), BOLD(5), REGULAR(6)
    os2.fsSelection = fs | (1 << 5 if bold else 1 << 6)   # bit 7 (USE_TYPO_METRICS) untouched
    font["head"].macStyle = (font["head"].macStyle & ~0b11) | (1 if bold else 0)
    font["post"].isFixedPitch = 0


def adv_em(font: TTFont, ch: str):
    cm = font.getBestCmap()
    g = cm.get(ord(ch))
    if g is None:
        return None
    return round(font["hmtx"][g][0] / font["head"].unitsPerEm, 4)


def font_version(font: TTFont) -> str:
    v = font["name"].getDebugName(5) or f"{font['head'].fontRevision:.3f}"
    return v.split(";")[0].replace("Version ", "").strip()


# --------------------------------------------------------------------------- GF css
def parse_gf_css(css: str) -> dict[str, dict[int, set[int]]]:
    out: dict[str, dict[int, set[int]]] = {}
    for block in re.findall(r"@font-face\s*{(.*?)}", css, re.S):
        fam = re.search(r"font-family:\s*'([^']+)'", block)
        wt = re.search(r"font-weight:\s*(\d+)", block)
        ur = re.search(r"unicode-range:\s*([^;]+);", block)
        if not (fam and wt):
            continue
        cps = out.setdefault(fam.group(1), {}).setdefault(int(wt.group(1)), set())
        if not ur:
            cps.update(range(0, 0x110000))
            continue
        for part in ur.group(1).split(","):
            part = part.strip().upper().replace("U+", "")
            if "?" in part:
                a, b = int(part.replace("?", "0"), 16), int(part.replace("?", "F"), 16)
            elif "-" in part:
                a, b = (int(x, 16) for x in part.split("-"))
            else:
                a = b = int(part, 16)
            cps.update(range(a, b + 1))
    return out


# --------------------------------------------------------------------------- metrics
def design_font_sizes() -> list[float]:
    sizes = set()
    for p in iter_files(DESIGN, ["**/*.html"]):
        t = read_text(p)
        sizes |= {float(x) for x in re.findall(r"font-size:\s*([0-9.]+)px", t)}
        sizes |= {float(x) for x in re.findall(r"fontSize:\s*['\"]?([0-9.]+)", t)}
    return sorted(s for s in sizes if s > 0)


def chrome_metrics(font: TTFont) -> dict:
    upm = font["head"].unitsPerEm
    h, o = font["hhea"], font["OS/2"]
    use_typo = bool(o.fsSelection & (1 << 7))
    if use_typo:
        nonwin = (o.sTypoAscender, -o.sTypoDescender, o.sTypoLineGap)
        win = nonwin
    else:
        # Skia/FreeType (Android, Linux, ChromeOS) and CoreText (Mac): hhea.
        nonwin = (h.ascent, -h.descent, h.lineGap)
        # DirectWrite: win metrics; line gap = max(0, hhea total - win total).
        extra = max(0, (h.ascent - h.descent + h.lineGap) - (o.usWinAscent + o.usWinDescent))
        win = (o.usWinAscent, o.usWinDescent, extra)
    res = {}
    for key, (a, d, g) in (("android_linux_chromeos_mac", nonwin), ("windows", win)):
        res[key] = {"ascent_em": round(a / upm, 4), "descent_em": round(d / upm, 4),
                    "lineGap_em": round(g / upm, 4),
                    "line_height_normal": round((a + d + g) / upm, 4)}
    return res


def chrome_px_table(m: dict, sizes: list[float]) -> dict:
    """Blink: LineSpacing = round(ascent) + round(descent) + round(lineGap), in px."""
    out = {}
    for key, v in m.items():
        out[key] = {f"{s:g}": int(round(v["ascent_em"] * s + 1e-9) + round(v["descent_em"] * s + 1e-9)
                                  + round(v["lineGap_em"] * s + 1e-9)) for s in sizes}
    return out


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-download sources and GF css")
    ap.add_argument("--ref", default="main", help="google/fonts git ref (default: main)")
    ap.add_argument("--noto-weights", default="400,500,700",
                    help="comma list of Noto Serif SC weights to build as ns<w/100>.ttf")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.time()
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if not EXTRA_CHARS.exists():
        EXTRA_CHARS.write_text("# One or more extra characters per line to force into the Noto (ns*) fonts.\n"
                               "# Lines starting with '#' are ignored.\n", encoding="utf-8")

    # ---- sources
    log("[1/6] sources")
    noto_path = fetch(RAW.format(ref=args.ref, path=NOTO_SRC), WORK / NOTO_LOCAL, args.refresh)
    plex_paths = {stem: fetch(RAW.format(ref=args.ref, path=p), WORK / Path(p).name, args.refresh)
                  for stem, (_, _, p) in PLEX.items()}
    gf = {}
    try:
        css = fetch(GF_CSS_URL, WORK / "gf_css2.css", args.refresh, {"User-Agent": CHROME_UA})
        gf = parse_gf_css(css.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log(f"  WARN: could not get Google Fonts CSS ({e}); coverage will be cmap-only")

    # ---- charset
    log("[2/6] charset")
    hanzi, gb_symbols = gb2312_chars()
    assert len(hanzi) == 6763, len(hanzi)
    assert len(ELEMENTS) == 118 and len(set(ELEMENTS)) == 118, (len(ELEMENTS), len(set(ELEMENTS)))
    for z, cp in ELEMENT_SPOT.items():
        assert ord(ELEMENTS[z - 1]) == cp, (z, ELEMENTS[z - 1], hex(cp))
    scanned = scan_sources()
    ranges = {chr(c) for a, b in RANGES for c in range(a, b + 1)}
    groups = {"gb2312_hanzi": set(hanzi), "gb2312_symbols": set(gb_symbols),
              "elements": set(ELEMENTS), "ranges": ranges, "coverage_list": set(COVERAGE_LIST),
              **scanned}
    wanted = set().union(*groups.values())
    for k, v in groups.items():
        log(f"  {k:15s} {len(v):6d}")

    noto_src = TTFont(noto_path)
    noto_cmap = noto_src.getBestCmap()
    noto_codes = sorted(ord(c) for c in wanted if ord(c) in noto_cmap)
    missing = {k: sorted(c for c in v if ord(c) not in noto_cmap)
               for k, v in groups.items() if k != "ranges"}
    for k, v in missing.items():
        if v:
            log(f"  WARN: {len(v)} {k} chars not in Noto Serif SC: {''.join(v[:80])}")
    (WORK / "noto_charset.txt").write_text("".join(chr(c) for c in noto_codes), encoding="utf-8")
    log(f"  Noto subset: {len(noto_codes)} code points")

    # ---- Noto: freeze tnum -> subset VF -> instance each weight
    log("[3/6] Noto Serif SC")
    noto_version = font_version(noto_src)
    noto_src_metrics = vmetrics(noto_src)
    noto_has_tnum = bool(feature_lookup_mapping(noto_src, "tnum"))
    noto_tnum = freeze_feature(noto_src, "tnum")
    log(f"  tnum substitutions frozen: {len(noto_tnum)}")
    ts = time.time()
    subsetter = subset.Subsetter(subset_options(NOTO_FEATURES))
    subsetter.populate(unicodes=noto_codes)
    subsetter.subset(noto_src)
    vf_sub = WORK / "NotoSerifSC-subset-VF.ttf"
    noto_src.save(vf_sub)
    del noto_src
    log(f"  VF subset: {vf_sub.stat().st_size/1e6:.2f} MB ({time.time()-ts:.0f}s)")

    builds = []  # (stem, path, family, weight, src_metrics, has_tnum, tnum_remap, expected_cmap)
    weights = [int(w) for w in args.noto_weights.split(",") if w.strip()]
    for w in weights:
        ts = time.time()
        stem = f"ns{w // 100}"
        vf = TTFont(vf_sub)
        inst = instancer.instantiateVariableFont(vf, {"wght": w}, inplace=False,
                                                 updateFontNames=False, static=True)
        finalize(inst, stem, w, WEIGHT_NAMES[w], noto_version)
        dest = OUT / f"{stem}.ttf"
        inst.save(dest)
        builds.append((stem, dest, "Noto Serif SC", w, noto_src_metrics, noto_has_tnum, noto_tnum,
                       len(noto_codes)))
        log(f"  {stem}.ttf  {dest.stat().st_size/1e6:.2f} MB ({time.time()-ts:.0f}s)")

    # ---- Plex
    log("[4/6] IBM Plex Serif")
    for stem, (w, style, _) in PLEX.items():
        f = TTFont(plex_paths[stem])
        ver = font_version(f)
        src_m = vmetrics(f)
        codes = sorted(f.getBestCmap())
        has_tnum = bool(feature_lookup_mapping(f, "tnum"))
        tn = freeze_feature(f, "tnum")
        ss = subset.Subsetter(subset_options(["*"]))
        ss.populate(unicodes=codes)
        ss.subset(f)
        finalize(f, stem, w, style, ver)
        match_win_metrics(f)
        dest = OUT / f"{stem}.ttf"
        f.save(dest)
        builds.append((stem, dest, "IBM Plex Serif", w, src_m, has_tnum, tn, len(codes)))
        log(f"  {stem}.ttf  {dest.stat().st_size/1e3:.0f} KB  (tnum frozen: {len(tn)})")

    # ---- validate + metrics
    log("[5/6] validate + metrics.json")
    sizes = design_font_sizes()
    metrics = {"generated": _dt.datetime.now().isoformat(timespec="seconds"),
               "fonttools": FONTTOOLS_VERSION,
               "notes": [
                   "line_height_normal is the Chrome 'line-height: normal' multiplier of font-size.",
                   "Android/Linux/ChromeOS (Skia+FreeType) and Mac (CoreText) use hhea asc+|desc|+lineGap; "
                   "Windows (DirectWrite) uses usWinAscent+usWinDescent (+max(0, hheaTotal-winTotal)); "
                   "USE_TYPO_METRICS (fsSelection bit 7) switches both to OS/2 typo metrics. It is off in all 6 fonts.",
                   "Blink rounds each part separately: px = round(asc*fs)+round(desc*fs)+round(gap*fs); "
                   "see chrome_line_height_px for the font sizes used in the design.",
                   "Android native text (Paint.getFontMetrics, Skia/FreeType) uses the same hhea values "
                   "because USE_TYPO_METRICS is off.",
                   "Vertical metrics are unchanged from the Google Fonts sources.",
               ],
               "design_font_sizes_px": sizes, "fonts": {}}
    outputs = {}
    problems = []
    for stem, dest, family, w, src_m, has_tnum, tn, expected in builds:
        f = TTFont(dest)
        for tag in f.keys():            # force full decompile
            f[tag]
        for gn in f.getGlyphOrder():
            f["glyf"][gn]
        cm = f.getBestCmap()
        if len(cm) != expected:
            problems.append(f"{stem}: cmap {len(cm)} != expected {expected}")
        if vmetrics(f) != src_m:
            problems.append(f"{stem}: vertical metrics changed {vmetrics(f)} vs {src_m}")
        digit_w = [f["hmtx"][cm[c]][0] for c in range(0x30, 0x3A)]
        digits_equal = len(set(digit_w)) == 1
        if family == "IBM Plex Serif" and not digits_equal:
            problems.append(f"{stem}: digits not tabular {digit_w}")
        h, o = f["hhea"], f["OS/2"]
        cm_info = chrome_metrics(f)
        outputs[stem] = f
        metrics["fonts"][stem] = {
            "file": f"static/fonts/{stem}.ttf", "bytes": dest.stat().st_size,
            "family_in_design": family, "weight": w,
            "internal_family_name": f["name"].getDebugName(1),
            "source_version": f["name"].getDebugName(3),
            "glyphs": f["maxp"].numGlyphs, "cmap_size": len(cm),
            "unitsPerEm": f["head"].unitsPerEm,
            "hhea": {"ascender": h.ascent, "descender": h.descent, "lineGap": h.lineGap},
            "os2": {"typoAscender": o.sTypoAscender, "typoDescender": o.sTypoDescender,
                    "typoLineGap": o.sTypoLineGap, "winAscent": o.usWinAscent,
                    "winDescent": o.usWinDescent,
                    "USE_TYPO_METRICS": bool(o.fsSelection & (1 << 7)),
                    "xHeight": getattr(o, "sxHeight", None), "capHeight": getattr(o, "sCapHeight", None),
                    "usWeightClass": o.usWeightClass},
            "chrome": cm_info,
            "chrome_line_height_px": chrome_px_table(cm_info, sizes),
            "advance_em": {**{c: adv_em(f, c) for c in "0123456789"},
                           ".": adv_em(f, "."), "space": adv_em(f, " "), ",": adv_em(f, ","),
                           "-": adv_em(f, "-"), "\u2212": adv_em(f, "\u2212"),
                           "\u00b7": adv_em(f, "\u00b7"), "\u4e00": adv_em(f, "\u4e00")},
            "digits_equal_width": digits_equal,
            "tnum": {"source_has_tnum_feature": has_tnum, "cmap_entries_remapped": tn},
        }
    METRICS_JSON.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- coverage
    log("[6/6] coverage.json")
    ordered = []
    for c in COVERAGE_LIST + "".join(sorted(scanned["design_html"])):
        if c not in ordered:
            ordered.append(c)
    gf_px = set().union(*gf.get("IBM Plex Serif", {}).values()) if gf.get("IBM Plex Serif") else None
    gf_ns = set().union(*gf.get("Noto Serif SC", {}).values()) if gf.get("Noto Serif SC") else None
    noto_ns = [s for s in outputs if s.startswith("ns")]
    plex_px = [s for s in outputs if s.startswith("px")]
    rows, missing_px, served_elsewhere, missing_all = [], [], [], []
    for c in ordered:
        cp = ord(c)
        has = {s: cp in outputs[s].getBestCmap() for s in outputs}
        in_px = all(has[s] for s in plex_px)
        in_ns = all(has[s] for s in noto_ns)
        row = {"char": c, "cp": f"U+{cp:04X}", "name": unicodedata.name(c, "?"),
               "in_coverage_list": c in COVERAGE_LIST, "in_design": c in scanned["design_html"],
               "has_glyph": has}
        if gf_px is not None:
            px_ok = in_px and cp in gf_px
            ns_ok = in_ns and gf_ns is not None and cp in gf_ns
            row["gf_unicode_range"] = {"px": cp in gf_px, "ns": gf_ns is not None and cp in gf_ns}
            row["chrome_design_font_in_plex_text"] = "px" if px_ok else ("ns" if ns_ok else "system")
            row["chrome_design_font_in_noto_text"] = "ns" if ns_ok else "system"
            if in_px and not px_ok:
                served_elsewhere.append(c)
        if not in_px:
            missing_px.append(c)
        if not in_px and not in_ns:
            missing_all.append(c)
        rows.append(row)
    cov = {
        "generated": metrics["generated"],
        "notes": [
            "has_glyph = the built font's cmap contains the character.",
            "gf_unicode_range = the character is inside the unicode-range of the Google Fonts CSS the "
            "design loads (Chrome only uses a web font for characters inside its unicode-range).",
            "chrome_design_font_in_plex_text = which family Chrome actually drew the character with in "
            "elements styled \"font-family: 'IBM Plex Serif', 'Noto Serif SC', ...\": px, ns, or system "
            "(neither web font covers it). The served Noto slices' unicode-ranges are generic and list "
            "code points the font has no glyph for (e.g. U+2080-2083), so has_glyph is checked too.",
            "chrome_design_font_in_noto_text = same for elements styled \"font-family: 'Noto Serif SC', serif\".",
            "Use chrome_design_font_in_plex_text (not has_glyph) to decide which runs must be set in ns*.",
        ],
        "summary": {
            "missing_from_px": "".join(missing_px),
            "missing_from_px_non_cjk": "".join(c for c in missing_px
                                               if not unicodedata.name(c, "").startswith("CJK UNIFIED")),
            "in_px_but_chrome_used_ns_or_system": "".join(served_elsewhere),
            "chrome_used_ns_in_plex_text": "".join(r["char"] for r in rows
                                                   if r.get("chrome_design_font_in_plex_text") == "ns"
                                                   and not r["name"].startswith("CJK UNIFIED")),
            "missing_from_px_and_ns": "".join(missing_all),
            "chrome_used_system_in_plex_text": "".join(r["char"] for r in rows
                                                       if r.get("chrome_design_font_in_plex_text") == "system"),
            "chrome_used_system_in_noto_text": "".join(r["char"] for r in rows
                                                       if r.get("chrome_design_font_in_noto_text") == "system"),
            "element_chars_missing_from_ns": "".join(missing.get("elements", [])),
            "scanned_chars_missing_from_ns": {k: "".join(missing.get(k, []))
                                              for k in ("design_html", "app_uvue_uts", "db_json", "extra_chars")},
        },
        "chars": rows,
    }
    COVERAGE_JSON.write_text(json.dumps(cov, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- summary
    total = 0
    log("\nresult:")
    for stem, dest, *_ in builds:
        m = metrics["fonts"][stem]
        total += m["bytes"]
        log(f"  {stem}.ttf {m['bytes']/1e6:6.2f} MB  glyphs={m['glyphs']:5d} cmap={m['cmap_size']:5d} "
            f"lh(android)={m['chrome']['android_linux_chromeos_mac']['line_height_normal']} "
            f"lh(win)={m['chrome']['windows']['line_height_normal']} digitsEqual={m['digits_equal_width']}")
    log(f"  total {total/1e6:.2f} MB   ({time.time()-t0:.0f}s)")
    log(f"  missing from px: {cov['summary']['missing_from_px_non_cjk']} (+CJK)")
    log(f"  in px but Chrome used Noto/system: {cov['summary']['in_px_but_chrome_used_ns_or_system']}")
    if problems:
        log("PROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
