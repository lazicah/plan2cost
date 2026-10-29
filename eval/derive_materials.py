"""Material and labour constants from two bills the author supplied for the same 5-bedroom duplex at Asaba: SIMPLIFIED BOQ.pdf (materials and labour: cement bags, tonnes of
sand and granite, rebar lengths, planks, labour rates) and BOQ CUBANA MILLENIUM CITY - UPDATED.pdf (the measured quantities, April 2026). Pairing the two gives material per unit of
measured work. Only numbers leave the PDFs (they stay in reference/, which is not committed). Run:  python -m eval.derive_materials
Writes data/materials_labour.json: unit rates, recipes per BoQ line key, and the evidence behind each ratio."""
import json
import re
import subprocess
from pathlib import Path

SIMPLIFIED = "reference/boq/SIMPLIFIED BOQ.pdf"
MIX_124 = {"cement_bag": 7.0, "sand_t": 0.74, "granite_t": 1.39}  # per m3 of 1:2:4 concrete
OUT = Path("data/materials_labour.json")
SIMPLE_ROW = re.compile(r"^\s*(\d+[a-z]?)\s+(.*?)\s{2,}(\d[\d,]*)\s+(\w[\w²³.]*)\s+([\d,]+\.\d\d)\s+([\d,]+\.\d\d)\s*$")
num = lambda s: float(s.replace(",", ""))  # noqa: E731


def text(pdf: str) -> str:
    return subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout


def simplified_rows(t: str) -> list[dict]:
    rows, section, sub = [], "", ""
    for line in t.split("\n"):
        m = re.match(r"SECTION (\d+): (.*)", line.strip())
        if m:
            section = m.group(2).strip()
            continue
        m = re.match(r"([A-H])\. (.*)", line.strip())
        if m and not re.search(r"\d{3}", line):
            sub = m.group(2).strip()
            continue
        p = SIMPLE_ROW.match(line)
        if p:
            rows.append({"section": section, "sub": sub, "item": p.group(2).strip(), "qty": num(p.group(3)), "unit": p.group(4).lower(), "rate": num(p.group(5)), "amount": num(p.group(6))})
    return rows


def derive() -> dict:
    S = simplified_rows(text(SIMPLIFIED))

    def s(pat, unit=None, sub=None, ex=None, nsub=None):  # simplified quantity
        return sum(r["qty"] for r in S if re.search(pat, r["item"], re.I) and (unit is None or r["unit"].startswith(unit)) and (sub is None or re.search(sub, r["sub"], re.I))
                   and not (ex and re.search(ex, r["item"], re.I)) and not (nsub and re.search(nsub, r["sub"], re.I)))

    def rate(pat, unit=None):  # the unit rate the simplified bill uses (the most common one)
        rs = [r["rate"] for r in S if re.search(pat, r["item"], re.I) and (unit is None or r["unit"].startswith(unit)) and r["qty"]]
        return max(set(rs), key=rs.count) if rs else None

    # concrete: cement bags against the measured cubic metres of the same elements (the Cubana bill's quantities, read off its pages), and the sand and granite that go with each bag
    parts = {"foundation footing": (r"^FOUNDATION FOOTING", 24), "column bases": (r"^COLUMN BASES", 53), "ground floor slab": (r"^GROUND FLOOR SLAB", 29), "floor beams": (r"^FLOOR BEAMS", 71),
             "floor slabs": (r"^FLOOR SLAB \(", 96), "staircase": (r"^STAIRCASE", 13), "roof beams and slab": (r"^ROOF BEAMS & ROOF SLAB", 19), "columns": (r"^COLUMNS", 28)}
    skip = r"Mortar|Blockwork|Parapet|Wire|Labour|Rebar|Formwork|Nail|Plank|Timber"
    el = {k: (s(r"^Cement", "bag", sub, ex=skip), s(r"^(Stone Dust|Sharp Sand|Sand)", "ton", sub), s(r"^Granite", "ton", sub), m3) for k, (sub, m3) in parts.items()}
    cement_per_m3 = {k: round(b / m3, 2) for k, (b, _, _, m3) in el.items()}
    bags, m3s = sum(v[0] for v in el.values()), sum(v[3] for v in el.values())
    sand_per_bag, granite_per_bag = sum(v[1] for v in el.values()) / bags, sum(v[2] for v in el.values()) / bags
    typical = round(bags / m3s, 2)
    # steel, wire, formwork
    bending_kg, lengths = s(r"Iron Bending", "kg"), s(r"^Rebar", "len")
    form_m2 = s(r"Carpenter", "m")
    planks = s(r'1"\s*[x×X]\s*12', "len", nsub="EARTHWORK SUPPORT")
    blocks, block_m2 = s(r"Sandcrete Blocks", "no"), 144 + 616 + 584 + 60
    mortar_cement, mortar_sand = s(r"Cement.*(Mortar|Blockwork)", "bag"), s(r"Stone Dust / Sand|Sand for Blockwork", "ton", sub="BLOCKWORK|PARAPET|COLUMNS & BLOCKWORK")
    plaster_m2 = s(r"Wall Plastering", "m")
    evidence = {"mix_124_used": MIX_124, "bill_sand_t_per_m3": round(typical * sand_per_bag, 2), "bill_granite_t_per_m3": round(typical * granite_per_bag, 2), "cement_bags_per_m3_by_element": cement_per_m3, "cement_bags_per_m3_all": typical, "sand_t_per_bag": round(sand_per_bag, 3), "granite_t_per_bag": round(granite_per_bag, 3),
                "kg_steel_per_12m_length": round(bending_kg / lengths, 2), "binding_wire_rolls_per_t_steel": round(s(r"Binding Wire", "roll") / bending_kg * 1000, 2),
                "planks_per_m2_formwork": round(planks / form_m2, 3), "blocks_per_m2_wall": round(blocks / block_m2, 2), "plaster_m2": plaster_m2}
    r = {
        # 1:2:4 per the nigeriabuildingcost concrete mix calculator (5% waste, dry-volume factor 1.54): the author chose it over the bill's own sand and granite, which are well above a mix
        "concrete": {"cement_bag": MIX_124["cement_bag"], "sand_t": MIX_124["sand_t"], "granite_t": MIX_124["granite_t"]},
        "blinding_per_m3": {"cement_bag": round(s(r"^Cement", "bag", r"^BLINDING") / 21, 3), "sand_t": round(s(r"Sand|Stone Dust", "ton", r"^BLINDING") / 21, 3)},  # 21 m3 of grade 15 blinding in the Cubana bill
        "steel_per_t": {"rebar_length": round(1000 / (bending_kg / lengths), 1), "binding_wire_roll": evidence["binding_wire_rolls_per_t_steel"]},
        "formwork_per_m2": {"plank_1x12": round(planks / form_m2, 2), "nails_bag": round(s(r"^Nail", "bag", nsub="EARTHWORK SUPPORT") / form_m2, 4)},
        "block_per_m2": {"block_225": round(blocks / block_m2, 2), "cement_bag": round(mortar_cement / block_m2, 3), "sand_t": round(mortar_sand / block_m2, 4)},
        "plaster_per_m2": {"cement_bag": round(s(r"Cement – Plastering", "bag") / plaster_m2, 4), "sand_t": round(s(r"Sand – Plastering", "ton") / plaster_m2, 4)},
        "paint_per_m2": {"paint_drum_20l": round(s(r"Emulsion", "drum") / 2400, 4), "white_cement_bag": round(s(r"Screeding Cement", "bag") / 2400, 5)},
        "floor_tiling_per_m2": {"floor_tile_m2": 1.0, "cement_bag": round((s(r"Cement – Tile Fixing", "bag") + s(r"Cement – Floor Screed", "bag")) / s(r"Labour – Tiling \(Floor\)", "m"), 3),
                                "sand_t": round(s(r"Stone Dust – Screed", "ton") / s(r"Labour – Tiling \(Floor\)", "m"), 4)},
        "skirting_per_m": {"skirting_tile": round(s(r"Skirting Tiles", "no") / 1002, 2)},
        "ceiling_per_m2": {"pop_cement_bag": round(s(r"P\.O\.P Cement", "bag") / 571, 3), "ceiling_hanger_length": round(s(r"Hangers", "len") / 571, 3),
                           "binding_wire_roll": round(s(r"Binding Wire \(Ceiling\)", "roll") / 571, 4), "sponge_kg": round(s(r"Sponge", "kg") / 571, 3)},
        "roof_cover_per_m2": {"roof_sheet_m2": 1.0, "roof_felt_m2": round(s(r"Roof Felt", "m") / 215, 3), "roof_nail": round(s(r"Galvanised Roof Nails", "no") / 215, 2)},
        "roof_timber_per_m": {"hardwood_length": round(s(r"Hardwood (Wallplate|Tie|Rafter|Kingpost|Purlins)", "len") / s(r"Carcassing", "m"), 4)},
        "earthwork_support_per_m2": {"plank_1x12": round(s(r"plank", "len", "EARTHWORK SUPPORT") / 548, 3), "strut_4x4": round(s(r"4\" x 4", "len") / 548, 3),
                                     "brace_2x2": round(s(r"2\" x 2", "len") / 548, 3), "nails_bag": round(s(r"Nail", "bag", "EARTHWORK SUPPORT") / 548, 4)},
    }
    materials = {"cement_bag": ("Cement, 50 kg bag", "bag", rate(r"^Cement", "bag")), "sand_t": ("Sharp sand / stone dust", "tonne", rate(r"Sharp Sand|Stone Dust", "ton")),
                 "granite_t": ("Granite", "tonne", rate(r"^Granite", "ton")), "binding_wire_roll": ("Binding wire, 25 kg roll", "roll", rate(r"Binding Wire", "roll")),
                 "plank_1x12": ("Plank 1\" x 12\" x 3.6 m", "length", rate(r"1\"\s*[x×X]\s*12", "len")), "strut_4x4": ("Timber 4\" x 4\" x 3.6 m", "length", rate(r"4\" x 4", "len")),
                 "brace_2x2": ("Timber 2\" x 2\" x 3.6 m", "length", rate(r"2\" x 2", "len")), "nails_bag": ("Nails, various sizes", "bag", rate(r"^Nail", "bag")),
                 "block_225": ("225 mm sandcrete block", "no", rate(r"Sandcrete Blocks", "no")), "roof_sheet_m2": ("Long-span roofing sheet, 0.55 mm", "m2", rate(r"Roof Covering", "m")),
                 "roof_felt_m2": ("Roof felt, 2 layers", "m2", rate(r"Roof Felt", "m")), "roof_nail": ("Galvanised roof nail", "no", rate(r"Galvanised Roof Nails", "no")),
                 "hardwood_length": ("Hardwood timber, 3.6 m length", "length", 2500), "floor_tile_m2": ("Floor tile 450 x 450 porcelain", "m2", rate(r"Floor Tiles", "m")),
                 "skirting_tile": ("Skirting tile", "no", rate(r"Skirting Tiles", "no")), "pop_cement_bag": ("P.O.P. cement, bag", "bag", rate(r"P\.O\.P Cement", "bag")),
                 "ceiling_hanger_length": ("Hardwood hanger 50 x 50, length", "length", rate(r"Hangers", "len")), "sponge_kg": ("Sponge (ceiling)", "kg", rate(r"Sponge", "kg")),
                 "paint_drum_20l": ("Emulsion or texture paint, 20 litre drum", "drum", rate(r"Emulsion", "drum")), "white_cement_bag": ("White cement for paint base", "bag", rate(r"Screeding Cement", "bag")),
                 "rebar_length": ("Reinforcement bar, 12 m length (mixed sizes)", "length", round(sum(x["amount"] for x in S if x["item"].startswith("Rebar") and x["unit"].startswith("len")) / lengths))}
    labour = {"casting_per_bag": ("Casting concrete, per bag of cement", "bag", rate(r"Labour.*Casting", "bag")), "iron_bending_per_kg": ("Iron bending", "kg", rate(r"Iron Bending", "kg")),
              "block_laying_foundation_per_block": ("Block laying in the foundation", "no", rate(r"Labour – Blockwork", "blk")), "carpenter_per_m2": ("Carpenter, formwork", "m2", rate(r"Carpenter", "m")), "block_laying_per_block": ("Block laying", "no", rate(r"Labour – Blockwork", "no")),
              "plaster_per_m2": ("Plastering", "m2", rate(r"Wall Plastering", "m")), "floor_tiling_per_m2": ("Floor tiling", "m2", rate(r"Labour – Tiling \(Floor\)", "m")),
              "ceiling_per_m2": ("Ceiling work", "m2", rate(r"Labour – Ceiling", "m")), "painting_per_m2": ("Painting", "m2", rate(r"Labour – Painting", "m")),
              "screeding_for_paint_per_m2": ("Screeding for paint", "m2", rate(r"Wall Screeding for Paint", "m")), "carcassing_per_m": ("Roof carcassing", "m", rate(r"Carcassing", "m")),
              "roof_covering_per_m2": ("Fixing roof covering", "m2", rate(r"Labour – Roof Covering", "m")), "earthwork_support_per_m2": ("Fixing earthwork support", "m2", rate(r"Labour for fixing Earthwork", "m"))}
    return {"_note": "Material and labour per unit of measured work, from the author's SIMPLIFIED BOQ and Cubana bills for one 5-bedroom duplex at Asaba (April 2026). One building, so most ratios are that contractor's practice, not a range. "
                     "Concrete is the exception: it uses the 1:2:4 mix quantities of the nigeriabuildingcost concrete calculator (7 bags of cement, 0.74 t of sand, 1.39 t of granite per m3, 5% waste), because the bill's sand (1.76 t per m3, about 1 m3 of "
                     "sand plus 10% waste at 1.6 t/m3) and granite (1.61 t) are well above a mix; the bill's own figures are kept under evidence. Sand bulk density 1.6 t/m3 is confirmed by that site's sand calculator. "
                     "Casting labour is the bill's 2,500 a bag (17,500 a m3 at 7 bags); the calculator's placing labour is 22,000 a m3.",
            "sources": {"simplified": "SIMPLIFIED BOQ.pdf (materials and labour, 5 bedroom duplex, Asaba)", "cubana": "BOQ CUBANA MILLENIUM CITY - UPDATED.pdf (measured BoQ, April 2026)"},
            "materials": {k: {"name": n, "unit": u, "rate": v} for k, (n, u, v) in materials.items()}, "labour": {k: {"name": n, "unit": u, "rate": v} for k, (n, u, v) in labour.items()},
            "ratios": r, "evidence": evidence}


def main() -> None:
    d = derive()
    OUT.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    print("cement bags per m3:", d["evidence"]["cement_bags_per_m3_by_element"], "all:", d["evidence"]["cement_bags_per_m3_all"])
    print("ratios:", json.dumps(d["ratios"])[:700])
    print("missing rates:", [k for k, v in {**d["materials"], **d["labour"]}.items() if v["rate"] is None])


if __name__ == "__main__":
    main()
