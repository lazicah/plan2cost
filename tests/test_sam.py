from plan2cost.facts.sam import parse

# One frame of the documented example: two objects on a 320x334 source (Meta Model API docs, "Reading segmentation output").
LINE = ("<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>,"
        "1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>")


def test_masks_decode_to_source_sized_rasters_placed_at_their_boxes():
    segs = parse(LINE)
    assert [s.object_id for s in segs] == [0, 1]
    for s in segs:
        assert s.mask.shape == (334, 320) and s.area_px > 0
        x1, y1, x2, y2 = s.box
        ys, xs = s.mask.nonzero()
        assert xs.min() >= x1 and xs.max() <= x2 + 1 and ys.min() >= y1 and ys.max() <= y2 + 1


def test_zero_matches_is_an_empty_list():
    assert parse("") == []
