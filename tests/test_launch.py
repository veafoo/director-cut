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


def test_launch_start_without_cuts_starts_just_before_her():
    turns = [(20.0, 30.0, PRES), (30.0, 90.0, HER)]
    assert launch.launch_start(turns, HER, 30.0, []) == 29.5


def test_launch_start_without_any_preceding_speaker():
    # Elle ouvre le sujet : pas de lancement à récupérer.
    turns = [(30.0, 90.0, HER)]
    assert launch.launch_start(turns, HER, 30.0, []) == 29.5


# --- reportage_end --------------------------------------------------------

def test_reportage_end_cuts_before_the_presenter_is_back():
    # Il reparle à 95 ; le cut plateau à 94.2 doit être retenu.
    assert launch.reportage_end(TURNS, HER, 90.0, CUTS) == 94.2


def test_reportage_end_never_cuts_into_her_last_word():
    assert launch.reportage_end(TURNS, HER, 94.5, CUTS) >= 90.0


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


# --- régressions relevées sur un vrai JT ----------------------------------
#
# Éléments repris tels quels d'un journal de 18h : tours de parole, plans et
# transcription. Les deux passages échouaient chacun d'une façon différente,
# et les deux fins montraient le retour plateau.

P1_TURNS = [
    (38.3, 87.5, PRES),        # titres + météo, d'une seule traite
    (89.4, 188.7, HER),        # son sujet
    (190.3, 190.4, HER),       # parasite de diarisation, déjà sur le plateau
    (190.4, 223.1, PRES),
]
P1_CUTS = [62.2, 66.1, 67.7, 87.8, 88.5, 89.4, 189.2, 196.8]
P1_TEXT = [
    (48.5, 51.1, "et des restrictions ont même été instaurées aux Andelis."),
    (51.3, 53.1, "Reportage à suivre."),          # lancement… du sommaire
    (66.7, 68.9, "On jette un petit coup d'œil à vos prévisions météo"),
    (84.4, 87.6, "et une maximale de 22 degrés au havre et à l'ençon."),
]
P1_PLATEAU = 189.2

P2_TURNS = [(260.3, 288.1, PRES), (289.3, 390.5, HER), (392.7, 420.4, PRES)]
P2_CUTS = [276.8, 282.1, 287.5, 291.6, 380.6, 387.1, 391.5, 397.3]
P2_TEXT = [
    (279.9, 282.2, "D'autres ouvrages sont surveillés de près"),
    (282.4, 284.6, "comme le pont de Tancarville, en Seine-Maritime."),
    (284.8, 288.0, "Vous allez le voir avec ce reportage de Lou-Hupelle."),
]
P2_PLATEAU = 391.5


def _span(turns, cuts, text, bs, be, names=()):
    return launch.build_span("reportage", turns, HER, bs, be, cuts=cuts,
                             transcript=text, names=names, max_lookback=40.0,
                             end_trim=0.5)


def test_a_subject_without_launch_does_not_start_in_the_weather():
    # Le présentateur enchaîne titres, météo puis sujet sans reprendre son
    # souffle. Se caler sur un changement de plan ramenait la météo.
    start, _, _ = _span(P1_TURNS, P1_CUTS, P1_TEXT, 89.4, 190.4)
    assert start > 87.6                      # après la dernière phrase météo
    assert start < 89.4                      # mais avant sa première parole


def test_the_summary_launch_is_not_taken_for_the_real_one():
    # « Reportage à suivre » est prononcé 36 s plus tôt, avant la météo.
    assert launch.launch_sentence(P1_TEXT, 89.4, max_lookback=40.0) is None


def test_a_launch_is_taken_from_the_start_of_its_sentence():
    # Se caler sur le plan (282.1) coupait au milieu de la phrase précédente.
    start, _, _ = _span(P2_TURNS, P2_CUTS, P2_TEXT, 289.3, 390.5)
    assert start == 284.8
    assert start > 284.6                     # pas dans « le pont de Tancarville »


def test_the_journalist_name_also_marks_the_launch():
    assert launch.launch_sentence(P2_TEXT, 289.3, names=["Lou Hupel"]) == 284.8


@pytest.mark.parametrize("turns,cuts,text,bs,be,plateau", [
    (P1_TURNS, P1_CUTS, P1_TEXT, 89.4, 190.4, P1_PLATEAU),
    (P2_TURNS, P2_CUTS, P2_TEXT, 289.3, 390.5, P2_PLATEAU),
])
def test_the_cut_never_reaches_the_studio(turns, cuts, text, bs, be, plateau):
    _, end, _ = _span(turns, cuts, text, bs, be)
    assert end < plateau


def test_a_stray_diarization_fragment_does_not_drag_the_cut_onto_the_studio():
    # Le fragment de 0.1 s à 190.3 est déjà sur le plateau ; s'en servir comme
    # plancher de fin ramenait 1.2 s de plateau dans le passage.
    assert launch.last_word(P1_TURNS, HER, 190.4) == 188.7
    _, end, _ = _span(P1_TURNS, P1_CUTS, P1_TEXT, 89.4, 190.4)
    assert 188.7 <= end < P1_PLATEAU


def test_the_cut_keeps_her_last_word():
    for turns, cuts, text, bs, be, last in (
            (P1_TURNS, P1_CUTS, P1_TEXT, 89.4, 190.4, 188.7),
            (P2_TURNS, P2_CUTS, P2_TEXT, 289.3, 390.5, 390.5)):
        _, end, _ = _span(turns, cuts, text, bs, be)
        assert end >= last
