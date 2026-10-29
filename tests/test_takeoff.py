from plan2cost.takeoff.units import to_10mm


def test_dimensions_round_half_up_to_the_nearest_10mm():
    assert to_10mm(0.675) == 0.68
    assert to_10mm(0.674) == 0.67
