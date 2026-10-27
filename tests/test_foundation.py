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
