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


# --- rediffusions ---------------------------------------------------------
#
# Une matinale repasse le même reportage plusieurs fois dans la journée. Sur
# une source de 2h14, le même sujet sortait en trois exemplaires (diffusé à
# 07:30, 07:48 et 08:30).

FERRYS = ("les ferrys des îles anglo-normandes adaptent leurs rotations "
          "cet été, avec des traversées plus nombreuses au départ de Granville")
PONTS = ("les ponts de la région sont surveillés de près pendant les fortes "
         "chaleurs, le tablier se dilate et les joints se déforment")


def _tx(*items):
    return [(s, e, t) for s, e, t in items]


def test_a_rerun_of_the_same_report_is_dropped():
    tx = _tx((10, 60, FERRYS), (1000, 1050, FERRYS), (2000, 2050, FERRYS))
    kept, reruns = segments.drop_reruns([(10, 60), (1000, 1050), (2000, 2050)], tx)
    assert len(kept) == 1
    assert len(reruns) == 2


def test_two_different_reports_are_both_kept():
    tx = _tx((10, 60, FERRYS), (1000, 1050, PONTS))
    kept, reruns = segments.drop_reruns([(10, 60), (1000, 1050)], tx)
    assert kept == [(10, 60), (1000, 1050)]
    assert reruns == []


def test_the_most_complete_version_is_the_one_kept():
    # Une rediffusion est parfois raccourcie : on garde la version longue.
    court = FERRYS.split(",")[0]
    tx = _tx((10, 30, court), (1000, 1060, FERRYS))
    kept, reruns = segments.drop_reruns([(10, 30), (1000, 1060)], tx)
    assert kept == [(1000, 1060)]
    assert reruns == [(10, 30)]


def test_wording_that_merely_resembles_is_not_a_rerun():
    autre = ("les ferrys de la compagnie ont été immobilisés hier soir "
             "après une avarie technique dans le port de Cherbourg")
    tx = _tx((10, 60, FERRYS), (1000, 1050, autre))
    kept, _ = segments.drop_reruns([(10, 60), (1000, 1050)], tx)
    assert len(kept) == 2


def test_without_a_transcript_nothing_is_dropped():
    # Aucun moyen de comparer : on ne jette rien sur une supposition.
    spans = [(10, 60), (1000, 1050)]
    assert segments.drop_reruns(spans, None) == (spans, [])
    assert segments.drop_reruns(spans, []) == (spans, [])


def test_a_single_passage_is_left_alone():
    assert segments.drop_reruns([(10, 60)], _tx((10, 60, FERRYS))) == ([(10, 60)], [])


def test_a_passage_without_words_is_never_taken_for_a_rerun():
    # Un sujet en son seul (pas de commentaire) ne doit pas être confondu
    # avec un autre sujet muet.
    tx = _tx((10, 60, FERRYS))
    kept, reruns = segments.drop_reruns([(500, 560), (700, 760)], tx)
    assert len(kept) == 2 and reruns == []
