from plan2cost.facts.foundation_section import check_section

PAGE = "675mm. x 225mm. MASS CONCRETE STRIP FOUNDATION BASE 50mm. THICK SANDCRETE BLINDING 150 775 225 50 1200 SECTION A - A"


def test_layers_that_add_up_are_accepted_and_values_must_be_printed():
    data = {"footing_width_mm": 675, "footing_thickness_mm": 225, "blinding_mm": 50, "slab_mm": 150, "fill_depth_mm": 775,
            "overall_depth_mm": 1200, "hardcore_mm": 150}
    out = check_section(data, PAGE)
    assert out["layers_close"] is True and out["values"]["overall_depth_mm"] == 1200
    assert "hardcore_mm" not in out["values"] and any("not split" in q for q in out["questions"])  # 150 is printed (the slab) but is not a hardcore depth
    assert check_section({**data, "overall_depth_mm": 1300}, PAGE)["layers_close"] in (None, False)
