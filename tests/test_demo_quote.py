from eval.make_demo_quote import plant


def items():
    mk = lambda k, q, r, unit="m2": {"key": k, "description": f"Work {k}", "unit": unit, "qty": q, "rate": r}
    return {i["key"]: i for i in (mk("ext_blockwork_230_m2", 100, 1000), mk("int_blockwork_230_m2", 50, 900), mk("ground_slab_m3", 10, 150000, "m3"), mk("floor_finish_m2", 80, 6000), mk("roof_covering_m2", 120, 16000))}


def test_the_planted_errors_are_the_ones_the_audit_should_find():
    lines, planted = plant(items())
    by = {l["description"]: l for l in lines}
    assert by["Work ext_blockwork_230_m2"]["rate"] == 1250  # 25% over
    assert by["Work ground_slab_m3"]["qty"] == 12.0  # 20% over
    assert by["Work floor_finish_m2"]["amount"] != by["Work floor_finish_m2"]["qty"] * by["Work floor_finish_m2"]["rate"]
    assert sum("blockwork internal partitions" in l["description"] for l in lines) == 1 and sum(1 for l in lines if l["description"] == "Work int_blockwork_230_m2") == 1  # charged twice
    assert not any("roof_covering" in l["description"] for l in lines) and len(planted) == 5
