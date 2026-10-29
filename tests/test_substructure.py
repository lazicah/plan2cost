from plan2cost.takeoff.foundation import PadBase
from plan2cost.takeoff.substructure import (FoundationColumn, blinding_foundations_m3, columns_in_foundation, disposal_and_backfill,
                                          formwork_foundation_sides_m, levelling_compaction_m2, topsoil_strip_m2, void_filling_m3)

# The author's plan2 sheet: base thicknesses 0.25, 0.25, 0.25, 0.4 (type 4) and 0.45 (type 5) as he used them.
PADS = [PadBase("1", 1.2, 1.2, 4, 0.25), PadBase("2", 1.4, 1.4, 5, 0.25), PadBase("3", 1.5, 1.5, 5, 0.25), PadBase("4", 1.6, 1.6, 4, 0.4),
        PadBase("5", 1.7, 1.7, 1, 0.45)]


def test_topsoil_levelling_and_blinding_reproduce_the_sheet():
    assert topsoil_strip_m2(19.1, 10.5, factor=0.95) == 226  # the author's manual reduction on that sheet, not a rule
    assert topsoil_strip_m2(19.1, 10.5) == 238
    assert levelling_compaction_m2(70, 0.69, PADS) == 89
    assert blinding_foundations_m3(70, 0.69, PADS) == 7


def test_columns_disposal_and_backfill():
    one = columns_in_foundation([FoundationColumn(0.225, 0.45, 4)])
    assert one["column_concrete_m3"] == 0.61 and one["formwork_column_sides_m2"] == 8
    out = disposal_and_backfill(excavation_m3=106, blockwork_girth_m=105, blockwork_height_m=0.85, block_mm=225, blinding_m3=7, footing_m3=11, bases_m3=12, columns_m3=2.61)
    assert out == {"disposal_off_site_m3": 53, "backfill_around_foundations_m3": 53}


def test_void_filling_factor():
    assert void_filling_m3(89) == 10.26


def test_void_filling_scales_with_block_thickness():
    assert void_filling_m3(89, 225) == 10.26
    assert void_filling_m3(100, 150) == 7.69
    assert void_filling_m3(100, 100) == 5.12


def test_base_formwork_in_metres_is_the_perimeter_of_the_bases():
    assert formwork_foundation_sides_m(PADS) == 110  # 4x4.8 + 5x5.6 + 5x6.0 + 4x6.4 + 6.8 = 109.6
