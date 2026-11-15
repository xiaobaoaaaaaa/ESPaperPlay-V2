# Final adopted candidate — supersedes the earlier ±.10 mm scenario recommendation

The user subsequently confirmed access to magnification for precise alignment and inspection. The parent adopted the following prototype candidate; magnification availability is **not evidence that the numerical registration limit has already been achieved**.

- Four ordinary 0.30/0.60 mm vias at local (±0.63, ±0.63) mm; independent via mask expansion **+.020 mm** (mask diameter .64), while peripheral pads retain +.050 mm. Calculated nominal nearest mask bridge **.102392 mm**; final exported mask must verify this. Supplier numeric mask-registration acceptance tolerance was not found, so this is nominal bridge validation only.
- One curved F.Paste aperture within a **1.55 mm square**, from `tolerance-recommended-polygon.json: local_vertices_mm`, 628 vertices. Forbidden regions are each hole center ±.105 mm in X/Y, buffered by .255 mm. The polygon uses a slightly larger, circumscribed approximation of the forbidden arcs, with a small rounding cushion.
- Conditional limits: local print registration **each axis ≤.030 mm**; hole-position analysis envelope **each axis ±.075 mm**; finished hole analysis maximum **.430 mm**; outward stencil-edge deviation **≤.020 mm**. These must be verified/accepted for actual parts and printing, not presented as measurements already performed.
- Under this envelope, paste-to-hole geometric clearance is **at least .020 mm**. The nominal aperture is **1.438535 mm² = 50.9685% of the 1.68 mm EP**, stencil area ratio **2.4850** at .100 mm thickness. Full shifted/expanded paste remains .015 mm inside the nominal EP. These are geometry results, not solder-wicking, joint void or thermal qualification.
- **About “50% coverage”: this is nominal designed aperture area, not guaranteed minimum delivered paste.** If every aperture boundary contracts by .020 mm, calculated aperture area is 1.324937 mm² (**46.944% EP**); outward .020 mm gives 1.555563 mm² (55.115% EP). Transfer efficiency adds another unmeasured factor. The chosen design balances approximately 51% nominal volume and the stated avoidance envelope; it does not certify a finished 50% solder coverage threshold.

Nominal independent via ring width is **(.600−.300)/2=.150 mm**. If maximum diameter .430 and per-axis position ±.075 are independently applied relative to fixed same-layer copper, the most adverse radial shift is √2×.075 and local ring becomes **−.021066 mm**. Interpreting .075 as a radial limit instead gives **+.010 mm**. The official position figure does not establish either interpretation or its correlation with copper-layer alignment; this stress calculation must not be called proof of real breakout or a closed annular-ring guarantee. Nominal free-process via capability, fabrication electrical/ring acceptance, and incoming inspection remain relevant. The enlarged EP copper union may support part of the ring; that does not turn the nominal annulus into a guaranteed tolerance minimum.

The original sections below retain the research history and alternate ±.10 mm calculations. Their earlier recommendation is superseded by this final candidate. No source/CAD/Git mutation was made by this reviewing agent; parent applies and verifies the chosen CAD.

---

# U101 ordinary thermal-via tolerance review — 2026-11-15

Scope: scratch review only; no formal CAD/Git edits by this agent. EP 1.68 × 1.68 mm; nominal four 0.30/0.60 mm thermal vias; 0.10 mm stencil; DIY tape-hinge registration assumed each-axis ±0.10 mm. Thermal and solder-joint performance remain unqualified.

## Official evidence and limits

- Current JLCPCB rigid capability page: hole-position tolerance **±0.075 mm**, plated through-hole diameter **+0.13/-0.08 mm**, and June 2025 LDI upgrade allowing soldermask opening 1:1 with pad. It does not specify whether position tolerance is per axis or radial; this review conservatively uses per axis. Current rendered page takes priority over search results and old official blogs claiming ±0.05 mm. https://jlcpcb.com/capabilities/pcb-capabilities
- Domestic manufacturing guide describes **+0.13/-0.08 mm for insertion PAD holes**, and says conducting vias are not necessarily compensated. Therefore 0.43 mm as the maximum size of a nominal 0.30 mm thermal via is a conservative analysis scenario, **not a demonstrated guarantee applicable to this domestic order**. https://www.jlc.com/portal/1/serviceGuide
- Domestic stencil homepage advertises accuracy “可达 ±0.02 mm”; it does not define aperture-edge vs dimension/position error or an acceptance contract. A technical article describes cutting generally within ±0.05 mm. Neither establishes a guaranteed per-edge maximum for this order. We calculate both, counting the number as outward edge deviation. https://www.jlc-gw.com/ ; https://www.jlc-gw.com/technical-documentation/49579
- The old mask design article's +0.05 mm per-side opening enlargement is a design allowance, **not a published mask-registration tolerance**. Current domestic ordering guide says LDI/1:1 opening is available; no quantitative mask-registration acceptance limit was found. https://www.jlc.com/portal/q6i34402.html ; https://m.jlc.com/portal/t7i1325.html
- Do not mix the FPC ±0.08 mm hole diameter tolerance into the FR-4 analysis. https://www.jlc.com/portal/vtechnology.html

## Original cross fails combined tolerance

Four holes at ±0.60; cross length 1.48, width .60. Nominal nearest paste-to-hole gap is .150 mm. Subtract DIY registration .100, hole position .075, hole-radius increase .065, and stencil-edge .020/.050: worst signed gap is **−.110/−.140 mm**. The previously quoted remaining .050 mm considered registration alone.

For a cross, signed gap = c − w/2 − dmax/2 − registration_axis − drill_position_axis − aperture_edge_error. Negative values mean possible overlap, not measured overlap on manufactured boards.

## Maximum connected curved aperture under stated DIY model

Let C be a hole center, U = .100 + .075 = .175 mm, R = .215 + stencil_edge + .020 mm. For each of four holes, prohibit a square C±U in both axes buffered by radius R. Subtract all prohibited regions from an EP-inset square of side L = 1.68 − 2×(.100 + stencil_edge). This gives a single connected aperture. This construction is the largest aperture inside the selected inset square under these translation, circular hole, and outward-edge assumptions. It does not model paste slump or reflow wicking.

| Hole centers (each axis) | Stencil edge scenario | L / R mm | Area mm² | Coverage of EP | Area ratio, .10 mm thick |
|---|---:|---:|---:|---:|---:|
| ±.60 | .020 | 1.44 / .255 | .919418 | 32.576% | 1.7275 |
| ±.60 | .050 | 1.38 / .285 | .764125 | 27.074% | 1.5189 |
| ±.62 | .020 | 1.44 / .255 | 1.005818 | 35.637% | 1.8899 |
| ±.62 | .050 | 1.38 / .285 | .850525 | 30.135% | 1.6907 |
| ±.63 | .020 | 1.44 / .255 | 1.047818 | 37.125% | 1.9688 |
| ±.63 | .050 | 1.38 / .285 | .892525 | 31.623% | 1.7742 |

All rows retain a **.020 mm geometric gap under the corresponding assumed worst-case stack**, and fit the translated/edge-expanded paste within the nominal EP. All rows are below typical 50–70% stencil coverage guidance; this is a solder-volume and joint-quality concern, not a proof they cannot solder. An area-ratio pass alone does not prove adequate solder volume or thermal resistance. At .10 mm thickness the conservative ±.60 row deposits only .0764 mm³ nominal paste (before transfer-efficiency loss).

## Superseded initial recommendation under ±.10 mm registration

Keep **four centers at ±.60 mm** unless the parent explicitly redesigns the local mask. With inherited .05 mm mask expansion, moving centers to ±.63 reduces the EP/outer-pad mask bridge from approximately .106 to .08 mm (parent's mask measurement), so nominal copper clearance alone is insufficient. Do not rely on an isolated tiny mask island or guaranteed free in-pad oil plugging.

If the intent is a genuinely conservative geometric prototype under the existing ±.10 DIY assumption, use the **1.38 mm square with four rounded forbidden regions (U=.175, R=.285)**. It retains four thermal paths and accommodates the .05 stencil scenario, but mark the resulting **27.1% nominal EP paste coverage as requiring first-board solder-joint/thermal validation**. It is not a production-ready equivalent to filled/capped vias. If the team prefers more paste, use the .02 scenario only with a corresponding actual stencil/print acceptance check; do not silently assume the marketing figure is guaranteed.

If first-board solder volume is judged unacceptable, the free-process trade-off requires changing an assumption: fewer in-pad holes with thermal reassessment, measured tighter local registration, or a different charge/thermal target. Arbitrarily relaxing a calculation limit does not close manufacturing tolerance.

## Alternatives, not assumed achieved

At centers ±.63 and each-axis registration ≤.035, an aperture inside a 1.55 square excluding C±.110 buffered by .255 gives 1.418143 mm² (50.246% EP), area ratio 2.4525, and .020 mm remaining hole clearance in the .020 stencil-edge scenario. A simpler 1.55×.55 cross gives 49.69% and needs registration ≤.025 for the same .020 residual. These require stringent local print verification and mask redesign; they are **not the default tape-hinge capability**.

Actual U101 copper polygon measurements (nominal .60 land): nearest different-net copper = .205779 at c=.60, .183379 at .62, .172392 at .63, .161561 at .64, .150891 at .65. Moving to .65 consumes practically all .15 design clearance, so is not preferred.

## Verification still needed

- Parent's final exact Gerber/Excellon geometry and full-board DRC, including local mask bridge and exposed-copper clearances.
- Incoming via/print geometry against the analysis envelope; do not certify actual finished size from nominal drill data alone.
- First-board inspection for insufficient EP solder, wicking and voiding, followed by staged charge/load thermal measurements. Geometric clearance does not prevent molten solder entering an open thermal hole.

Numerical sweep: `tolerance-scan.py`, `tolerance-scan.json`. No quotation of a typical supplier value here is intended as a production guarantee.
