"""Bornes des passages : c'est la logique la plus sensible du projet.

Scénario de référence utilisé partout ci-dessous (plateau -> elle -> plateau) :

    0-5    PRES   ouverture du journal (autre sujet)
    20-30  PRES   annonce du sujet (le "lancement")
    30-90  HER    son passage
    95-100 PRES   retour plateau
    130-140 PRES  annonce du sujet suivant

Changements de plan à 5, 19.5, 29.8, 94.2, 128.0.
"""
import pytest

from director_cut import launch

HER = "SPEAKER_01"
PRES = "SPEAKER_00"

TURNS = [
    (0.0, 5.0, PRES),
    (20.0, 30.0, PRES),
    (30.0, 90.0, HER),
    (95.0, 100.0, PRES),
    (130.0, 140.0, PRES),
]
CUTS = [5.0, 19.5, 29.8, 94.2, 128.0]


# --- name_in_text ---------------------------------------------------------

def test_name_in_text_exact():
    assert launch.name_in_text("et on retrouve Marie Dupont", ["Marie Dupont"])


def test_name_in_text_ignores_case_accents_and_spacing():
    assert launch.name_in_text("bonjour MÉLANIE  DUPONT", ["melanie dupont"])


def test_name_in_text_tolerates_whisper_typos():
    # Whisper écorche les noms propres : une lettre fausse ne doit pas casser.
    assert launch.name_in_text("le reportage de Marie Dupond", ["Marie Dupont"])


def test_name_in_text_rejects_another_name():
    assert not launch.name_in_text("le reportage de Paul Martin", ["Marie Dupont"])


def test_name_in_text_empty_inputs():
    assert not launch.name_in_text("", ["Marie Dupont"])
    assert not launch.name_in_text("Marie Dupont", [])
    assert not launch.name_in_text("Marie Dupont", [""])


# --- turns ----------------------------------------------------------------

def test_turns_accepts_a_normalized_list():
    assert launch.turns([(2.0, 3.0, "B"), (0.0, 1.0, "A")]) == [
        (0.0, 1.0, "A"), (2.0, 3.0, "B")]


def test_turns_accepts_a_pyannote_annotation():
    class Seg:
        def __init__(self, s, e):
            self.start, self.end = s, e

    class Annotation:
        def itertracks(self, yield_label=True):
            yield Seg(2.0, 3.0), None, "B"
            yield Seg(0.0, 1.0), None, "A"

    assert launch.turns(Annotation()) == [(0.0, 1.0, "A"), (2.0, 3.0, "B")]


# --- launch_start ---------------------------------------------------------

def test_launch_start_snaps_to_the_plateau_cut_of_the_announcement():
    # Le lancement commence à 20 ; le cut plateau juste avant est à 19.5.
    assert launch.launch_start(TURNS, HER, 30.0, CUTS) == 19.5


def test_launch_start_does_not_go_back_to_the_opening_of_the_show():
    # Le cut à 5.0 (ouverture) ne doit jamais être retenu.
    assert launch.launch_start(TURNS, HER, 30.0, CUTS) > 5.0


def test_launch_start_respects_max_lookback():
    # Avec un lookback ridicule, on ne remonte pas jusqu'à l'annonce.
    start = launch.launch_start(TURNS, HER, 30.0, CUTS, max_lookback=2.0)
    assert start >= 28.0


def test_launch_start_breaks_on_a_long_pause_in_the_announcement():
    # Le présentateur parle à 0-5 puis 20-30 : avec launch_gap=2, les deux
    # prises ne forment pas un seul lancement, on ne remonte pas à 0.
    turns = [(0.0, 5.0, PRES), (20.0, 30.0, PRES), (30.0, 90.0, HER)]
    assert launch.launch_start(turns, HER, 30.0, CUTS, launch_gap=2.0) == 19.5


def test_launch_start_without_cuts_falls_back_on_the_speech_start():
    turns = [(20.0, 30.0, PRES), (30.0, 90.0, HER)]
    assert launch.launch_start(turns, HER, 30.0, []) == 20.0


def test_launch_start_without_any_preceding_speaker():
    # Elle ouvre le sujet : pas de lancement à récupérer.
    turns = [(30.0, 90.0, HER)]
    assert launch.launch_start(turns, HER, 30.0, []) == 30.0


# --- reportage_end --------------------------------------------------------

def test_reportage_end_cuts_before_the_presenter_is_back():
    # Il reparle à 95 ; le cut plateau à 94.2 doit être retenu.
    assert launch.reportage_end(TURNS, HER, 90.0, CUTS) == 94.2


def test_reportage_end_never_returns_before_the_block_end():
    assert launch.reportage_end(TURNS, HER, 94.5, CUTS) >= 94.5


def test_reportage_end_without_anyone_after_uses_the_next_cut():
    turns = [(30.0, 90.0, HER)]
    assert launch.reportage_end(turns, HER, 90.0, [94.2]) == 94.2


def test_reportage_end_with_no_cut_at_all_keeps_the_block_end():
    turns = [(30.0, 90.0, HER)]
    assert launch.reportage_end(turns, HER, 90.0, []) == 90.0


# --- chronique_end --------------------------------------------------------

def test_chronique_end_keeps_the_closing_exchange_and_stops_at_the_next_topic():
    # 95-100 = "merci <nom>" (gardé), 130 = annonce du sujet suivant.
    # Le cut plateau avant 130 est à 128.0.
    assert launch.chronique_end(TURNS, HER, 90.0, CUTS) == 128.0


def test_chronique_end_without_a_next_topic_uses_the_forward_cut():
    turns = [(30.0, 90.0, HER), (95.0, 100.0, PRES)]
    assert launch.chronique_end(turns, HER, 90.0, [105.0]) == 105.0


def test_chronique_end_without_anyone_after():
    turns = [(30.0, 90.0, HER)]
    assert launch.chronique_end(turns, HER, 90.0, [94.2]) == 94.2


# --- build_span -----------------------------------------------------------

def test_build_span_reportage_applies_the_end_trim():
    s, e, _ = launch.build_span("reportage", TURNS, HER, 30.0, 90.0, cuts=CUTS,
                                end_trim=0.5)
    assert (s, e) == (19.5, 93.7)


def test_build_span_end_trim_never_eats_into_her_speech():
    # end_trim énorme : la borne ne doit pas passer sous la fin de son bloc.
    _, e, _ = launch.build_span("reportage", TURNS, HER, 30.0, 90.0, cuts=CUTS,
                                end_trim=999.0)
    assert e == 90.0


def test_build_span_chronique_uses_the_chronique_end():
    s, e, _ = launch.build_span("chronique", TURNS, HER, 30.0, 90.0, cuts=CUTS,
                                end_trim=0.0)
    assert (s, e) == (19.5, 128.0)


def test_build_span_validates_the_name_heard_in_the_announcement():
    transcript = [(20.0, 30.0, "le reportage de Marie Dupont")]
    *_, validated = launch.build_span("reportage", TURNS, HER, 30.0, 90.0,
                                      cuts=CUTS, transcript=transcript,
                                      names=["Marie Dupont"])
    assert validated is True


def test_build_span_reports_a_missing_name():
    transcript = [(20.0, 30.0, "le reportage de Paul Martin")]
    *_, validated = launch.build_span("reportage", TURNS, HER, 30.0, 90.0,
                                      cuts=CUTS, transcript=transcript,
                                      names=["Marie Dupont"])
    assert validated is False


def test_build_span_without_names_does_not_validate_anything():
    *_, validated = launch.build_span("reportage", TURNS, HER, 30.0, 90.0,
                                      cuts=CUTS)
    assert validated is None


@pytest.mark.parametrize("mode", ["reportage", "chronique"])
def test_build_span_always_returns_an_ordered_span(mode):
    s, e, _ = launch.build_span(mode, TURNS, HER, 30.0, 90.0, cuts=CUTS)
    assert s < e
