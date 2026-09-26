# Offline compound DB — sources, method, rebuild

Output: `CC-uni-app-x/static/db/` (built into `tools/db/_out/`, installed in one step with `--install`).

## Commands

```
python tools/db/fetch_wikidata.py            # download raw data into tools/db/_raw/ (cached; --force to refresh)
python tools/db/build_db.py                  # build tools/db/_out/ from cached raw data (no network)
python tools/db/test_db.py tools/db/_out     # end-to-end checks on the output files only
python tools/db/build_db.py --install-only   # replace CC-uni-app-x/static/db with _out in one step
                                             # (directory rename; robocopy /MIR if HBuilderX holds the folder)
python tools/db/test_db.py                   # same checks on the installed copy
```

`test_db.py` also writes `tools/db/key_vectors.json`: reference outputs of normF / hillKey / nameKey / shard / M for
a few inputs, to verify the UTS re-implementation.

`pip install requests opencc-python-reimplemented` (OpenCC is used for Traditional→Simplified).

## Data sources

| Data | Source | Licence |
|---|---|---|
| Compounds: formula (P274), CAS (P231), EC no. (P232, only as inclusion criterion), en/zh labels and aliases, sitelink & statement counts, instance-of classes | Wikidata, queried through the QLever SPARQL endpoint `https://qlever.cs.uni-freiburg.de/api/wikidata` | CC0 |
| Chinese trivial/common names | zh.wikipedia article titles of those items + redirect titles to them (MediaWiki API) | titles only (facts, CC BY-SA text not used) |
| Curated lab reagents (`reagents_src.txt`) | hand-written from standard Chinese reagent nomenclature (GB/T reagent standards, supplier catalogues); every CAS is check-digit-validated and cross-checked against Wikidata by `build_db.py` | — |
| Atomic weights (`elements.json`) | CIAAW/IUPAC abridged standard atomic weights (5 significant figures, conventional values for interval elements; Zr = 91.222 per the 2024 revision). Elements without a standard atomic weight: mass number of the longest-lived isotope (Tc 97, Pm 145, Po 209, … Og 294). Chinese names 104–118 checked against Wikidata zh-cn labels. | — |
| Density tables (`density.json`) | see "Density tables" below | — |

### Candidate set (Wikidata)
Items with a chemical formula (P274) **and** at least one of: ≥ 1 Wikimedia sitelink, a Chinese label/alias (any
zh variant), an EC number. Dropped: items with electric charge (P2200), isotopically labelled species
(label patterns like `[11C]`, `carbon-14`, `氘`), items whose instance-of class is an isotope/nuclide, alloy,
mixture, polymer, protein/peptide, functional group, radical, disambiguation etc.; alloy-style formulas (`Cu·Zn`);
combination drugs (`/` in the name); formulas that do not parse under the app's rules (charges, `ₙ`, `x`, D/T,
fractional hydrates …).

### Names
* zh display name priority: zh-cn > zh-hans > zh > zh-sg > zh-my > zh-hant > zh-tw > zh-hk > zh-mo > zhwiki title.
  Everything goes through OpenCC `t2s` (Wikidata zh-cn/zh-hans labels occasionally contain Traditional characters),
  keeping 鎓/鏻/噁 which mainland nomenclature still uses, plus a few Taiwan→mainland term fixes
  (醯→酰, 過錳酸→高锰酸, 過氯酸→高氯酸, 矽→硅 …).
* Indexed names: every zh label/alias (converted), zhwiki title and redirects, en label, up to 8 en aliases
  (3 for obscure items), CAS numbers. Aliases that are formulas, identifiers (≥ 4 digits, `:`/`=`/`/`),
  or PubChem-style `a;b` names are skipped.
* Generated variants: hydrate spellings (`五水硫酸铜` ↔ `五水合硫酸铜` ↔ `硫酸铜(五水)` ↔ `硫酸铜五水合物`),
  `无水X` / `X(无水)` for a compound whose hydrate is also present, en names without oxidation state
  (`copper(II) sulfate` → `copper sulfate`), and for curated reagents sulfate/sulphate, aluminium/aluminum,
  caesium/cesium spellings.
* Hydrate consistency: a name that says "N水…/…hydrate" is never indexed on an anhydrous record and
  "无水…/anhydrous" never on a hydrate (Wikidata often lists e.g. 胆矾 on anhydrous CuSO4).
* A name explicitly listed for one curated reagent is not indexed for other curated reagents
  (so 胆矾 → CuSO4·5H2O, 绿矾 → FeSO4·7H2O, 大苏打 → Na2S2O3·5H2O).

### Rank
`rank = 16·sitelinks + 8·(has zh name) + 4·(has CAS) + min(statements/10, 3)` for Wikidata compounds;
curated reagents: `1 000 000 + 100 000·priority + min(Wikidata rank, 99 999)` (priority 1 = preferred isomer
for a shared formula, e.g. 葡萄糖 over 果糖, 蔗糖 over 乳糖). Compound ids are assigned in descending rank
order, so chunk `c/000.json` holds the 1000 most useful compounds (all curated reagents first).
Index lists are sorted by rank desc, then id.

### Curated ↔ Wikidata merge
Each curated reagent is merged into the Wikidata item with the same CAS and the same Hill formula (preferring an
item whose label matches); otherwise same Hill formula + a matching name; otherwise a new record. The merged
record takes the curated formula/zh/en/CAS and keeps all Wikidata names. A Wikidata item sharing the CAS but with an
incompatible element set (Wikidata typo, e.g. potassium chlorate `KCIO3`) is absorbed into the curated record.

## Density tables (`density.json`)

Source data with full provenance/cross-check notes: `tools/db/density_src.json` (`source`, `urls`, `note` per entry).
`w` = mass %, `rho` = g/mL (= g/cm³), original published values, no smoothing. `T` is 20 °C except where noted.

| key | zh | T °C | w range | source (cross-check) |
|---|---|---|---|---|
| HCl | 盐酸 | 20 | 0.5–40 | CRC Handbook 85th ed., *Concentrative Properties of Aqueous Solutions* (Perry's 8th ed. Table 2-59, en.wikipedia: agree ≤ 0.0003) |
| H2SO4 | 硫酸 | 20 | 0.5–100 | CRC (Perry's Table 2-103 / ICT; max 1.8361 at 98 %) |
| HNO3 | 硝酸 | 20 | 0.5–100 | CRC 0.5–40 %, Perry's Table 2-68 (ICT vol. 3) 45–100 % (overlap agrees ≤ 0.0003; Merck table consistent) |
| H3PO4 | 磷酸 | 20 | 0.5–100 | CRC 0.5–40 %, International Critical Tables vol. 3 p. 61 45–100 % (85 % = 1.689) |
| CH3COOH | 乙酸 | 20 | 0.5–100 | CRC (Perry's/ICT 0.0004–0.002 higher; max ≈ 1.068 at 80 %) |
| NH3 | 氨水 | 20 | 0.5–30 | CRC, w = % NH3 (Perry's Table 2-34 ≤ 0.0001) |
| NaOH | 氢氧化钠 | 20 | 0.5–50 | CRC 0.5–40 %, Perry's Table 2-92 (ICT) 44–50 % |
| KOH | 氢氧化钾 | **15** | 1–50 | ICT vol. 3 p. 86 (CRC 20 °C column is 0.3–0.8 % lower than ICT, OxyChem and Merck tables, so ICT was used; 20 °C values ≈ 0.002 lower) |
| H2O2 | 过氧化氢 | **18** | 1–100 | ICT vol. 3 p. 54 (Evonik 20 °C: 30 % = 1.111; ICT 18 °C ≈ 0.001–0.002 higher) |
| C2H5OH | 乙醇 | 20 | 0.5–100 | CRC (en.wikipedia *Ethanol (data page)* / Lange agree) |
| HClO4 | 高氯酸 | 20 | 0–70 | L. H. Brickwedde, *J. Res. NBS* 42, 309 (1949), Table 2 (ICT 0.002–0.004 lower) |
| HBr | 氢溴酸 | 20 | 1–65 | ICT vol. 3 p. 55 (de.wikipedia 65 % = 1.7675 identical) |
| HF | 氢氟酸 | 20 | 5–50 | ICT vol. 3 p. 54 (= Perry's Table 2-60) |
| HCOOH | 甲酸 | 20 | 0–100 | ICT vol. 3 pp. 122–123 (CRC only to 68–70 % and inconsistent with ICT, so not spliced) |
| HCHO | 甲醛 | **18** | 0–50 | J. F. Walker, *Formaldehyde* (ACS Monograph 1944) Table 8, **methanol-free** solutions. Commercial 37 % formalin with 10–15 % methanol is ≈ 1.08–1.09, which is why `reagents.json` uses ρ = 1.09 for 甲醛 |
| NaCl | 氯化钠 | 20 | 0.5–26 | CRC (en.wikipedia NaCl data page identical) |
| C3H8O3 | 甘油 | 20 | 0.5–100 | CRC (Perry's Table 2-117, Bosart & Snoddy: ≤ 0.001) |
| HI | 氢碘酸 | 20 | 1–45 | ICT vol. 3 p. 55 (the 57 % azeotrope, ρ ≈ 1.70, is not covered) |
| HOCH2CH2OH | 乙二醇 | 20 | 0.5–60 | CRC (table ends at 60 %) |
| CH3OH | 甲醇 | 20 | 0.5–100 | CRC (Perry's Table 2-111 ≤ 0.0002) |

Default label values in `reagents.json` (w %, typical range, ρ at 20 °C): 盐酸 37 [36–38] 1.184 · 硫酸 98 [95–98] 1.836 ·
硝酸 65 [65–68] 1.391 · 磷酸 85 [85–87] 1.689 · 冰醋酸 99.5 [99.5–100] 1.049 · 氨水 25 [25–28] 0.907 · 过氧化氢 30 [30–31] 1.112 ·
高氯酸 70 [70–72] 1.672 · 氢溴酸 47 [40–48] 1.474 · 氢碘酸 47 [45–57] 1.50 (label value, beyond the table) · 氢氟酸 40 [40–42] 1.13 ·
甲酸 88 [88–90] 1.201 · 甲醛 37 [37–40] 1.09 (methanol-stabilised) · 无水乙醇 99.7 → 0.790 · 甲醇 99.5 → 0.793 ·
乙二醇 99 → 1.113 (pure-liquid value; table ends at 60 %) · 甘油 99 → 1.259. Pure solvents: CRC/Merck 20 °C densities.

The raw material used to read the tables (web pages, public-domain ICT/NBS scans, parse scripts) is in
`tools/db/_raw/density/` (`build_density_src.py` regenerates `density_src.json`); the full handbook PDFs that were
downloaded for reading were deleted afterwards. Ranges follow the Chinese reagent standards (e.g. GB/T 622 盐酸 36.0–38.0 %,
GB/T 625 硫酸 95.0–98.0 %, GB/T 626 硝酸 65.0–68.0 %, GB/T 631 氨水 25.0–28.0 %, GB/T 623 高氯酸 70.0–72.0 %,
GB/T 620 氢氟酸 ≥ 40 %, GB/T 6684 过氧化氢 ≥ 30 %, GB/T 685 甲醛 37.0–40.0 %).

## Conventions for liquid reagents (`reagents.json`)
* `f` is always the **solute** formula and `w` its mass fraction in % — 盐酸 `f:"HCl"`, 氨水 `f:"NH3"`
  (w = NH3 content, as printed on Chinese labels "含量(NH3) 25%~28%"), 甲醛 `f:"HCHO"`, 过氧化氢 `f:"H2O2"`.
* Pure liquids (solvents) use `w` = typical assay (AR grade) and `rho` = density of the pure liquid at 20 °C.
* `rho` of the aqueous reagents is interpolated from `density.json` at the default `w` (so both files agree);
  where a table is missing, the label value is used.
* Optional extra fields: `note` (Chinese remark, e.g. 95% 乙醇 is v/v) and `id` (compound id of the reagent's
  record in `c/`).
