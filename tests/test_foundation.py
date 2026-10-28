from plan2cost.tools.foundation import GridLine, PadBase, StripSection, foundation_takeoff, whole_units

# Totals from the author's plan2 survey: full runs 104.835m, pad/overlap deductions 35.145m (trench 69.69m).
LINES = [GridLine("all", runs=[(104.835, 1)], deductions=[(35.145, 1)])]
PADS = [PadBase("1", 1.2, 1.2, 4), PadBase("2", 1.4, 1.4, 5), PadBase("3", 1.5, 1.5, 5),
        PadBase("4", 1.6, 1.6, 4), PadBase("5", 1.7, 1.7, 1)]


def section(width_mm):
    return StripSection(width_mm=width_mm, footing_thickness_m=0.225, trench_depth_m=1.35)


def test_reproduces_authors_sheet_with_its_690mm_width():
    out = foundation_takeoff(LINES, PADS, section(690))
    assert out["strip_trench_girth_230_m"] == 70 and out["fdn_blockwork_girth_230_m"] == 105
    assert out["trench_excavation_strip_m3"] == 58
    assert out["pit_excavation_column_bases_m3"] == 48
    assert out["working_space_m3"] == 180
    assert out["earthwork_support_m2"] == 299.52
    assert out["strip_footing_concrete_m3"] == 11
    assert out["fdn_blockwork_230_m2"] == 89


def test_drawn_675mm_rounds_to_0_68_and_changes_trench_volume():
    s = section(675)
    assert s.width_m == 0.68
    assert foundation_takeoff(LINES, PADS, s)["trench_excavation_strip_m3"] == 57  # 70 x 0.68 x 1.2 = 57.12


def test_whole_units_minimum_one():
    assert whole_units(0.2) == 1 and whole_units(2.5) == 3


def test_ground_bed_matches_author_workbook():
    from plan2cost.tools.foundation import ground_bed_takeoff

    t = ground_bed_takeoff(200.55, fill_area_m2=184)
    assert (t["ground_slab_m3"], t["brc_mesh_part1_m2"], t["dpm_polythene_m2"]) == (30, 200, 200)
    assert (t["hardcore_m3"], t["laterite_m3"], t["blinding_on_hardcore_m3"]) == (28, 28, 10)


def test_pad_concrete_and_rebar_from_drawing():
    from plan2cost.tools.foundation import PadBase, pad_concrete_m3, pad_rebar_kg

    pads = [PadBase("1", 1.2, 1.2, 4, 0.25, ("06-Y1202@200c/c B", "06-Y1202@200c/c B"))]
    assert pad_concrete_m3(pads) == 1  # 1.44 m3
    kg = pad_rebar_kg(pads)
    assert list(kg) == [12] and round(kg[12], 1) == round(2 * 6 * (1.1 + 0.3) * 0.888889 * 4, 1)
