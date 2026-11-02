from plan2cost.takeoff import coefficients as c


def test_the_table_is_consistent():
    assert c.problems() == []


def test_a_coefficient_is_a_range_with_its_sources():
    lo, typ, hi = c.spread("steel_slab_suspended_kg_per_m3")
    assert lo < typ < hi and c.value("blocks_per_m2_450x225") == 10
    assert all(c.load()["sources"][s]["name"] for s in c.entry("mix_124_cement_bags_per_m3")["sources"])


def test_the_authors_slab_steel_rule_agrees_with_the_published_per_volume_range():
    """12.5 kg Y12 per m2 plus 25% top bars and 12.5% distribution is about 17 kg/m2; a 175mm slab at 80 to 120 kg/m3 is 14 to 21."""
    per_m2 = c.value("steel_suspended_slab_bottom_y12_kg_per_m2") * (1 + c.value("steel_top_bars_share_of_bottom") + c.value("steel_distribution_share_of_bottom"))
    lo, _, hi = c.spread("steel_slab_suspended_kg_per_m3")
    thick = c.value("suspended_slab_concrete_m3_per_m2")
    assert lo * thick <= per_m2 <= hi * thick


def test_prices_are_labelled_as_sanity_checks_not_rates():
    assert all("sanity" in e["note"] or "never a rate" in e["note"] for e in c.group("benchmark"))


def test_a_broken_table_is_reported():
    bad = {"sources": {"a": {}}, "entries": [{"id": "x", "group": "g", "unit": "kg", "low": 5, "typical": 2, "high": 9, "sources": ["zz"], "confidence": "meh", "note": ""}]}
    assert len(c.problems(bad)) == 3


def test_ratios_derived_from_the_authors_plans_keep_their_per_plan_values():
    derived = [e for e in c.load()["entries"] if "authorboq" in e["sources"]]
    assert len(derived) >= 15
    for e in derived:
        assert e["n_plans"] == len(e["per_plan"]) and min(e["per_plan"].values()) == e["low"] and max(e["per_plan"].values()) == e["high"]
