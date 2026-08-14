from director_cut import segments


def test_merge_segments_joins_small_gaps():
    segs = [(0.0, 10.0), (12.0, 20.0), (60.0, 70.0)]
    assert segments.merge_segments(segs, 5.0) == [(0.0, 20.0), (60.0, 70.0)]


def test_merge_segments_keeps_large_gaps_apart():
    segs = [(0.0, 10.0), (12.0, 20.0)]
    assert segments.merge_segments(segs, 1.0) == [(0.0, 10.0), (12.0, 20.0)]


def test_merge_segments_boundary_gap_is_inclusive():
    # Trou exactement égal à merge-gap : on regroupe (c'est le réglage
    # --merge-gap que la personne ajuste quand un sujet part en morceaux).
    assert segments.merge_segments([(0.0, 10.0), (15.0, 20.0)], 5.0) == [(0.0, 20.0)]
    assert segments.merge_segments([(0.0, 10.0), (15.01, 20.0)], 5.0) == [
        (0.0, 10.0), (15.01, 20.0)]


def test_merge_segments_handles_unsorted_and_nested():
    segs = [(30.0, 35.0), (0.0, 40.0)]
    assert segments.merge_segments(segs, 0.0) == [(0.0, 40.0)]


def test_merge_segments_empty():
    assert segments.merge_segments([], 10.0) == []


def test_pad_segments_never_goes_negative():
    assert segments.pad_segments([(1.0, 5.0)], 3.0) == [(0.0, 8.0)]


def test_pad_segments_clamps_on_duration():
    assert segments.pad_segments([(1.0, 5.0)], 3.0, duration=6.0) == [(0.0, 6.0)]


def test_snap_to_scenes_uses_nearest_cut_within_tolerance():
    cuts = [0.5, 10.4, 100.0]
    assert segments.snap_to_scenes([(0.0, 10.0)], cuts, tol=1.0) == [(0.5, 10.4)]


def test_snap_to_scenes_leaves_bounds_alone_when_no_cut_is_close():
    assert segments.snap_to_scenes([(0.0, 10.0)], [50.0], tol=1.0) == [(0.0, 10.0)]


def test_snap_to_scenes_without_cuts_is_identity():
    segs = [(0.0, 10.0)]
    assert segments.snap_to_scenes(segs, []) is segs


def test_drop_short_filters_on_duration():
    segs = [(0.0, 2.0), (10.0, 20.0)]
    assert segments.drop_short(segs, 3.0) == [(10.0, 20.0)]


def test_drop_short_keeps_exact_min_len():
    assert segments.drop_short([(0.0, 3.0)], 3.0) == [(0.0, 3.0)]
