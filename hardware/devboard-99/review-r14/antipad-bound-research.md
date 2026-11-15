# KiCad 10.0.8 own-through antipad envelope research

Date: 2026-11-15. Read-only investigation of `build/pcb-99/r14/general-complete.kicad_pcb`; no CAD, fill, or validator-script changes.

## Finding

The missing term is KiCad's **ExtraFillMargin = 0.0005 mm**, not an arbitrary relaxation of the 0.005 mm arc approximation setting. The correct nominal knockout input for the examined 1.8 mm circular PTH is therefore **0.9 + 0.15 + 0.0005 = 1.0505 mm** before `ERROR_OUTSIDE` polygon conversion. `radius + clearance + max_error` is not a strict bound for that conversion because the segment-count calculation rounds to the nearest integer, and the exterior correction uses the actual secant error of that count.

## Version and configuration evidence

- Installed RPM: `kicad-10.0.8-1.fc45.x86_64`; the supplied venv's `pcbnew.Version()` returns `10.0.8`.
- Current `KICAD_CONFIG_HOME` and `XDG_CONFIG_HOME` are unset.
- Neither `/home/xiaobao/.config/kicad/10.0/kicad_advanced` nor `/home/xiaobao/.config/kicad/kicad_advanced` exists. No `ExtraFillMargin` override was found in the KiCad user configuration directory.
- `ADVANCED_CFG` initializes `m_ExtraClearance = 0.0005`; `ExtraFillMargin` is its configuration key. The source reads `kicad_advanced` from `PATHS::GetUserSettingsPath()`, whose normal Linux path includes the KiCad major/minor directory. This establishes the default for the current process/environment; it does not independently prove which environment generated an older saved fill.

Sources: [advanced_config.cpp, 10.0.8, lines 216–245 and 412–413](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/common/advanced_config.cpp#L216-L245), [setting documentation](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/include/advanced_config.h#L131-L141), [configuration path construction](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/common/paths.cpp#L634-L668).

## Exact source path

1. `ZONE_FILLER::buildCopperItemClearances` obtains `extra_margin` from `m_ExtraClearance`. It adds that margin to the resolved pad clearance before `addKnockout`. The comment expressly attributes the added margin to curve approximation and rounding. Pad hole clearance is handled separately and also receives the margin. [zone_filler.cpp, lines 2144–2205](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/pcbnew/zone_filler.cpp#L2144-L2205)
2. `addKnockout` calls `TransformShapeToPolygon(..., gap, m_maxError, ERROR_OUTSIDE)`. [zone_filler.cpp, lines 1697–1734](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/pcbnew/zone_filler.cpp#L1697-L1734)
3. A circular pad uses its layer-specific copper radius plus clearance, minimum 16 circle segments, and `ShapePos(layer)` (important if the pad has an offset). [pad.cpp, lines 2637–2662](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/pcbnew/pad.cpp#L2637-L2662)
4. Circle conversion rounds the segment count up to a multiple of eight, then increases the radius by `CircleToEndSegmentDeltaRadius`. That delta is the rounded value of `r * (sec(pi/n) - 1)`. The initial segment-count calculation itself uses `KiROUND`, not `ceil`. [circle polygon conversion](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/libs/kimath/src/convert_basic_shapes_to_polygon.cpp#L80-L109), [segment count and secant correction](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/libs/kimath/src/geometry/geometry_utils.cpp#L42-L83)

## Measured J301.3 result

Board object: J301 pin 3, net `EPD_SCLK`, position `(46.08, 55.0)` mm; circular copper diameter 1.8 mm. Board `m_MaxError = 5000 IU = 0.005 mm`.

The following values were obtained by calling the installed native `pad.TransformShapeToPolygon` on In1.Cu and In2.Cu. The 33 reported points include closure; there are 32 distinct vertices.

| Clearance argument | Maximum vertex distance from pad center |
| --- | --- |
| 0.1500 mm | 1.055081459213458 mm |
| 0.1505 mm | 1.055583385410172 mm |

Consequently, even `0.9 + 0.1505 + 0.005 = 1.0555 mm` falls short of the actual native polygon's maximum radius by 0.0000833854 mm. Using the native result avoids assuming that the user-facing arc-error parameter is a strict radial bound.

Local saved-fill check used the actual In2.Cu GND polygon and clipped the two EPD_SCLK tracks to a 1.08 mm radius around J301.3. No fill was regenerated and no plane-boundary buffer was added:

| Track UUID | Centerline void in local window | Void outside native polygon with clearance 0.1505 mm | Copper-projection void area outside native polygon |
| --- | --- | --- | --- |
| `4ad69e94-42ea-41c4-8457-875ea6ed8ed1` | 0.947757846241325 mm | 0 | 0.000000035331382 mm² |
| `d2941f3b-7f7c-4256-8670-8cdeb95f539f` | 0.145300000000000 mm | 0 | 0 |

An envelope whose radius is the native polygon's maximum vertex radius plus **2 IU = 0.000002 mm** contains both local residual projections. The 2 IU is explicitly a small numerical comparison allowance; it is not claimed as a global error bound for all zone-fill operations.

## Recommended auditable algorithm

For a genuinely circular, flashed through pad/via on the examined inner layer:

1. Resolve the actual applicable clearance, including local/custom-rule overrides. For this examined zone use 0.15 mm. Add the current `ExtraFillMargin` of 0.0005 mm.
2. Build the native `ERROR_OUTSIDE` knockout with that clearance and the board's `m_MaxError`. For a pad, also account for the native drill/hole knockout if that can dominate the copper-land knockout. Use actual layer geometry and pad shape center, not a footprint bounding box.
3. Prefer the native polygon for the narrowest explanation. If a rotationally symmetric conservative envelope is required for circle-only objects, calculate `R = max(norm(vertex - shape_center))` from that native polygon. This circumscribes the **computed knockout**, without adding another arbitrary 0.005 or 0.01 mm.
4. Keep a separately reported small boundary tolerance, e.g. the existing audit's 0.00002 mm or an explicit 2 IU comparison tolerance. Do not silently turn it into assumed copper.
5. If a Shapely circle is used, remember `Point.buffer(R)` is an inscribed polygon. To ensure its polygon contains radius `R`, with `q` segments per quadrant use `Point.buffer((R + numerical_tolerance) / cos(pi/(4*q)), quad_segs=q)`.
6. Exempt only this own-net through object's local envelope and report its missing-reference length/area separately. Never exempt an entire connected hole, neighbor's antipad, or removed copper web merely because it touches this object. A native envelope is an explanation of local unavoidable void, not proof of return-path quality.

For noncircular pads, do not use a circle centered on the pad with its largest extent: retain the native layer polygon and investigate any residual geometry directly.

## Minimum-thickness processing: what is and is not bounded

The filler subtracts clearance holes, then deflates and reinflates by `min_thickness / 2 - 0.001 mm`: here 0.074 mm. It uses chamfered deflation and rounded reinflation, with optional path simplification, and clips again to clearance holes. Iterative cross-zone knockouts may trigger an additional prune pass. [initial prune and final reinflation](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/pcbnew/zone_filler.cpp#L3051-L3183), [post-knockout prune](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/pcbnew/zone_filler.cpp#L2776-L2823), [Clipper offset tolerance and simplification](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/libs/kimath/src/geometry/shape_poly_set.cpp#L925-L1028).

This supports the existence of very small contour differences after direct knockout construction, but **does not justify a universal sum of several `m_MaxError` values**. Minimum-width pruning can remove a real narrow copper web, a larger geometric change that should remain reportable. Here the 0.0005 mm native extra margin already explains the entire examined centerline residual; the circle-specific native circumradius also contains the tiny corner-projection remainder. No general morphology tolerance or clearance relaxation is needed for that observation.
