import json
from pathlib import Path

from plan2cost.takeoff.besmm_bill import get, path

import pytest


@pytest.mark.skipif(not path(), reason="the BESMM4 master bill is not in this checkout (it is the NIQS's text, kept in reference/)")
def test_every_code_in_the_map_is_a_real_besmm_item_with_the_unit_we_bill():
    codes = json.loads(Path("data/besmm_codes.json").read_text())["codes"]
    for key, code in codes.items():
        item = get(code)
        assert item, f"{key}: {code} is not in the master bill"
        assert key.rsplit("_", 1)[1] == item["unit"].lower().replace("m3", "m3"), f"{key}: billed in a different unit from {code} ({item['unit']})"
