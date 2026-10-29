from plan2cost.takeoff.checklist import building_type, coverage, how_to_get, statement

LIST = {"trades": [
    {"id": "substructure", "items": [
        {"id": "SUB-01", "description": "Excavation", "unit": "m3", "measured_from": "plan+section", "applies_to": ["duplex"], "required": True},
        {"id": "SUB-05", "description": "Blocks", "unit": "nr", "measured_from": "plan+section", "applies_to": ["duplex"], "required": True},
        {"id": "SUB-10", "description": "Cement", "unit": "bags", "measured_from": "derived", "applies_to": ["duplex"], "required": True},
        {"id": "SUB-18", "description": "Anti-termite", "unit": "m2", "measured_from": "plan", "applies_to": ["duplex"], "required": False}]},
    {"id": "electrical", "items": [
        {"id": "ELE-02", "description": "Sockets", "unit": "nr", "measured_from": "electrical layout|plan", "applies_to": ["duplex"], "required": True},
        {"id": "ELE-01", "description": "Wiring", "unit": "m", "measured_from": "electrical layout|allowance", "applies_to": ["duplex", "bungalow"], "required": True}]}]}
MAP = {"SUB-01": {"status": "covered", "keys": ["trench_excavation_strip_m3"]}, "SUB-05": {"status": "partial", "keys": ["fdn_blockwork_230_m2"], "missing": "block count"}}


def test_coverage_counts_what_the_boq_has_and_names_what_it_lacks():
    c = coverage(["trench_excavation_strip_m3", "fdn_blockwork_230_m2"], 2, LIST, MAP)
    assert (c["required"], c["covered"], c["partial"], c["not_built"]) == (5, 1, 1, 3)  # optional items are not counted
    assert c["trades"]["electrical"] == {"covered": 0, "partial": 0, "not_built": 2, "required": 2}
    assert {r["id"]: r["status"] for r in c["items"]}["SUB-05"] == "partial" and next(r for r in c["items"] if r["id"] == "SUB-05")["missing"] == "block count"
    s = statement(c)
    assert "1 of 5" in s and "electrical" in s and "substructure" in s


def test_the_building_type_decides_which_items_apply_and_the_source_of_a_quantity_is_stated():
    assert building_type(1) == "bungalow" and building_type(2) == "duplex"
    c = coverage([], 1, LIST, MAP)
    assert c["required"] == 1  # only the wiring item applies to a bungalow
    assert how_to_get(LIST["trades"][0]["items"][2]).startswith("derive")
    assert "ask the user" in how_to_get(LIST["trades"][1]["items"][1]) and how_to_get(LIST["trades"][0]["items"][0]) == "read from the plan+section"