"""Plan -> BoQ: BESMM4-style items from a take-off, with every assumed input flagged and no invented prices."""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from plan2cost.tools.substructure import (blinding_foundations_m3, disposal_and_backfill, formwork_foundation_sides_m2, levelling_compaction_m2,
                                          topsoil_strip_m2, void_filling_m3)
from plan2cost.tools.walls import Opening, blockwork_area_m2
from plan2cost.tools.foundation import PadBase, StripSection, ground_bed_takeoff, pad_concrete_m3, pad_rebar_kg, whole_units


@dataclass
class Assumption:
    name: str
    value: float
    basis: str
    source: str  # "drawing" or "assumed"


@dataclass
class BoqItem:
    key: str  # take-off / rate key, e.g. trench_excavation_strip_m3
    description: str
    unit: str
    qty: float
    rate: float | None = None
    amount: float | None = None


def load_defaults(path: str = "data/defaults.json") -> dict:
    return json.loads(Path(path).read_text())["foundation_strip"]


def strip_inputs(drawn: dict | None = None, defaults: dict | None = None) -> tuple[StripSection, list[Assumption], float]:
    """Merge what the drawing states with defaults. Returns the section, the assumption log and the concrete grade."""
    drawn, defaults = drawn or {}, defaults or load_defaults()
    log, vals = [], {}
    for name, d in defaults.items():
        if name == "width_mm" and name not in drawn:
            block = drawn.get("block_mm", defaults["block_mm"]["value"])
            vals[name] = 3 * block  # trench width by convention; a width printed on the drawing wins
            log.append(Assumption(name, vals[name], d["basis"], "assumed"))
        elif name in drawn:
            vals[name] = drawn[name]
            log.append(Assumption(name, drawn[name], "stated on the drawing", "drawing"))
        else:
            vals[name] = d["value"]
            log.append(Assumption(name, d["value"], d["basis"], "assumed"))
    grade = vals.pop("concrete_grade")
    return StripSection(**vals), log, grade


def foundation_boq(t: dict, s: StripSection, grade: float) -> list[BoqItem]:
    depth = f"maximum depth not exceeding 2.00m; commencing surface {int(s.topsoil_m * 1000)}mm below existing ground level"
    block = f"{s.block_mm}mm thick; 225 x 450 nominal blocks; laid stretcher bond; cement mortar (1:6); filled solid with weak concrete"
    rows = [
        ("trench_excavation_strip_m3", f"Trench excavation, width exceeding 0.30m; {depth}", "m3"),
        ("pit_excavation_column_bases_m3", f"Pits excavation for column bases; {depth}", "m3"),
        ("working_space_m3", "Working space allowance to excavation; including additional support, disposal and backfilling with selected excavated material", "m3"),
        ("earthwork_support_m2", "Earthwork support; maximum depth not exceeding 2.00m; distance between opposing faces not exceeding 2.00m", "m2"),
        ("strip_footing_concrete_m3", f"Plain in situ concrete, grade {grade:g}; foundations", "m3"),
        (f"fdn_blockwork_{s.block_mm}_m2", f"Blockwork walls in foundation; {block}", "m2"),
    ]
    return [BoqItem(k, d, u, t[k]) for k, d, u in rows if k in t]


def foundation_extras(pads: list[PadBase], grade: float, slab_area_m2: float | None = None,
                      fill_area_m2: float | None = None) -> list[BoqItem]:
    """Pad concrete and reinforcement from the structural drawing; ground bed items once the footprint is known."""
    items = [BoqItem("column_base_concrete_m3", f"Reinforced in situ concrete, grade {grade:g}; horizontal work in column bases (pad foundations)",
                     "m3", pad_concrete_m3(pads))]
    for d, kg in sorted(pad_rebar_kg(pads).items()):
        items.append(BoqItem(f"rebar_y{d}_foundations_t", f"High yield steel bar reinforcement; {d}mm diameter; straight and bent; in column bases",
                             "t", round(kg / 1000, 3)))
    if slab_area_m2:
        t = ground_bed_takeoff(slab_area_m2, fill_area_m2)
        items += [
            BoqItem("blinding_on_hardcore_m3", "Plain in situ concrete (1:3:6); horizontal work not exceeding 300mm thick; in blinding 50mm thick; poured on hardcore", "m3", t["blinding_on_hardcore_m3"]),
            BoqItem("hardcore_m3", "Imported granite hardcore filling; beds 150mm deep under ground floor bed; level; compacted in layers", "m3", t["hardcore_m3"]),
            BoqItem("laterite_m3", "Laterite filling; beds 150mm deep; level; compacted in layers", "m3", t["laterite_m3"]),
            BoqItem("dpm_polythene_m2", "Damp proof membrane; polythene sheeting; over 500mm wide; horizontal; under ground floor bed (laps included)", "m2", t["dpm_polythene_m2"]),
            BoqItem("brc_mesh_part1_m2", "Steel fabric reinforcement; BRC mesh; minimum laps 150mm; in ground floor bed", "m2", t["brc_mesh_part1_m2"]),
            BoqItem("ground_slab_m3", f"Reinforced in situ concrete, grade {grade:g}; horizontal work not exceeding 300mm thick; in ground floor bed 150mm thick; poured on hardcore", "m3", t["ground_slab_m3"]),
        ]
    return items


def superstructure_boq(ext_girth: dict[str, float], int_girth: dict[str, float], heights: dict[str, float],
                       openings: list[Opening], block_mm: int = 230) -> list[BoqItem]:
    """External and internal walls are measured separately: openings are deducted from the wall they are in, because the
    facade material and the finishes differ between the two faces."""
    ext = blockwork_area_m2(ext_girth, heights, [o for o in openings if o.external])
    internal = blockwork_area_m2(int_girth, heights, [o for o in openings if not o.external])
    block = f"{block_mm}mm thick hollow sandcrete blockwork; cement mortar (1:6); stretcher bond"
    items = [
        BoqItem("ext_blockwork_230_m2", f"{block}; external walls", "m2", ext),
        BoqItem("int_blockwork_230_m2", f"{block}; internal walls and partitions", "m2", internal),
        BoqItem("external_wall_render_m2", "Cement-sand rendering to external walls; over 600mm wide; to blockwork", "m2", ext),
        BoqItem("external_wall_paint_m2", "Weatherproof paint, 2 coats, on rendered walls; general surfaces over 300mm girth", "m2", ext),
    ]
    for o in openings:
        where = "external" if o.external else "internal"
        items.append(BoqItem(f"opening_{o.label.lower()}_nr", f"{o.label} {o.kind} {int(o.width_m * 1000)} x {int(o.height_m * 1000)}mm; {where}; as schedule", "nr", o.count))
    return items


def substructure_extras(t: dict, s: StripSection, pads: list[PadBase], trench_girth_m: float, building_length_m: float, building_width_m: float,
                        extras: dict) -> list[BoqItem]:
    """Items that follow from the strip, pits and bases: topsoil, surface treatment, levelling, blinding, formwork, disposal and backfill, void
    filling and foundation wall finishes. `t` is the foundation take-off, `extras` the quantities already computed (footing, bases, blinding)."""
    width = s.width_m
    top = topsoil_strip_m2(building_length_m, building_width_m, s.working_space_m)
    blind = blinding_foundations_m3(trench_girth_m, width, pads)
    exc = t["trench_excavation_strip_m3"] + t["pit_excavation_column_bases_m3"]
    db = disposal_and_backfill(exc, t[f"fdn_blockwork_girth_{s.block_mm}_m"], s.blockwork_height_m, s.block_mm, blind,
                               t["strip_footing_concrete_m3"], extras.get("column_base_concrete_m3", 0), extras.get("column_concrete_m3", 0))
    fdn_block = t[f"fdn_blockwork_{s.block_mm}_m2"]
    rows = [
        ("topsoil_strip_m2", "Remove topsoil; average depth 150mm", "m2", top),
        ("topsoil_disposal_m3", "Topsoil excavated as above; off site; transported away and deposited in spoil heaps", "m3", whole_units(top * s.topsoil_m)),
        ("excavated_surface_treatment_m2", "Anti-termite treatment applied to excavated surfaces", "m2", int(math.ceil(t["earthwork_support_m2"]))),
        ("levelling_compaction_m2", "Level and compact the bottom of excavations", "m2", levelling_compaction_m2(trench_girth_m, width, pads)),
        ("blinding_foundations_m3", "Plain in situ concrete (1:3:6); blinding 50mm thick under strip footings and 100mm under column bases; poured against earth", "m3", blind),
        ("formwork_foundation_sides_m2", "Formwork to sides of column bases; plain vertical; height 250-500mm", "m2", formwork_foundation_sides_m2(pads)),
        ("disposal_off_site_m3", "Excavated material; off site; transported away from excavation and deposited in spoil heaps", "m3", db["disposal_off_site_m3"]),
        ("backfill_around_foundations_m3", "Filling to excavations; selected excavated material; compacted around foundations", "m3", db["backfill_around_foundations_m3"]),
        ("concrete_filling_blockwork_voids_m3", "Plain in situ concrete, grade 15; mass concrete filling the voids in sandcrete blockwork", "m3", void_filling_m3(fdn_block, s.block_mm)),
        ("fdn_wall_render_m2", "Cement-sand (1:3) rendering to external face of foundation walls; 15mm thick", "m2", fdn_block),
    ]
    return [BoqItem(k, d, u, q) for k, d, u, q in rows]


def price_boq(items: list[BoqItem], rates: dict) -> dict:
    """Price with user-supplied rates. A missing or zero rate leaves the line unpriced; it is never guessed."""
    unpriced = []
    for i in items:
        r = rates["rates"].get(i.key)
        if r:
            i.rate, i.amount = r, round(i.qty * r, 2)
        else:
            unpriced.append(i.key)
    return {"currency": rates["currency"], "total": round(sum(i.amount or 0 for i in items), 2), "unpriced": unpriced}
