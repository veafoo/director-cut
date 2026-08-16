"""Bornes des passages : la logique la plus sensible du projet.

Le début d'un passage est le **tour de parole** qui précède le sien : le
présentateur qui lance le sujet. Ce repère est structurel, il ne dépend
d'aucune tournure ni d'aucune langue. La fin est le **changement de plan** qui
ramène le plateau — un retour plateau se voit avant de s'entendre.

Scénario de référence (plateau -> elle -> plateau) :

    0-5     PRES   ouverture du journal (autre sujet)
    20-30   PRES   lancement du sujet
    30-90   HER    son passage
    95-100  PRES   retour plateau
    130-140 PRES   lancement du sujet suivant

Changements de plan à 5, 19.5, 29.8, 94.2, 128.0.
"""
import pytest

from director_cut import launch, segments

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


# --- launch_start : le tour de parole d'avant ------------------------------

def test_the_start_is_the_beginning_of_the_preceding_turn():
    # Le présentateur lance de 20 à 30 : on démarre à 20, moins l'amorce.
    start = launch.launch_start(TURNS, HER, 30.0, CUTS)
    assert 20.0 - launch.LEAD_IN <= start <= 20.0


def test_the_start_does_not_go_back_to_an_earlier_turn():
    # Le tour 0-5 appartient au sujet précédent.
    assert launch.launch_start(TURNS, HER, 30.0, CUTS) > 5.0


def test_a_crumb_of_diarization_is_not_taken_for_the_launch():
    turns = TURNS + [(29.9, 30.0, "SPEAKER_09")]
    assert launch.launch_start(turns, HER, 30.0, CUTS) <= 20.0


def test_a_turn_longer_than_the_lookback_is_capped():
    # Un présentateur qui enchaîne les sujets : on ne remonte pas dans le
    # sujet d'avant.
    turns = [(40.0, 89.0, PRES), (90.0, 150.0, HER)]
    start = launch.launch_start(turns, HER, 90.0, [], max_lookback=10.0)
    assert start >= 80.0 - launch.LEAD_IN


def test_the_cap_never_lands_in_the_middle_of_a_sentence():
    turns = [(40.0, 89.0, PRES), (90.0, 150.0, HER)]
    text = [(78.0, 82.5, "une phrase à cheval sur le plafond"),
            (82.7, 89.0, "la phrase suivante, elle, est entière")]
    start = launch.launch_start(turns, HER, 90.0, [], max_lookback=10.0,
                                transcript=text)
    assert start >= 82.7 - launch.LEAD_IN


def test_without_anyone_speaking_before_her_we_start_on_her_shot():
    turns = [(30.0, 90.0, HER)]
    assert launch.launch_start(turns, HER, 30.0, [19.5, 29.8]) == 29.8


def test_without_anyone_and_without_cuts():
    turns = [(30.0, 90.0, HER)]
    assert launch.launch_start(turns, HER, 30.0, []) == 29.5


# --- amorce ---------------------------------------------------------------

def test_a_lead_in_protects_the_first_syllable():
    # Les horodatages sont approximatifs : démarrer pile dessus rogne le mot.
    assert launch.launch_start(TURNS, HER, 30.0, CUTS) < 20.0


def test_the_lead_in_never_swallows_the_previous_sentence():
    text = [(10.0, 19.9, "la phrase d'avant, qui ne nous regarde pas"),
            (20.0, 30.0, "et maintenant le lancement du sujet")]
    start = launch.launch_start(TURNS, HER, 30.0, CUTS, transcript=text)
    assert start >= 19.9 - launch.MARGIN


# --- reportage_end --------------------------------------------------------

def test_reportage_end_stops_on_the_shot_that_brings_the_studio_back():
    assert launch.reportage_end(TURNS, HER, 90.0, CUTS) == 94.2


def test_reportage_end_never_cuts_into_her_last_word():
    assert launch.reportage_end(TURNS, HER, 94.5, CUTS) >= 90.0


def test_reportage_end_without_anyone_after_uses_the_next_cut():
    turns = [(30.0, 90.0, HER)]
    assert launch.reportage_end(turns, HER, 90.0, [94.2]) == 94.2


def test_reportage_end_with_no_cut_at_all_keeps_the_block_end():
    turns = [(30.0, 90.0, HER)]
    assert launch.reportage_end(turns, HER, 90.0, []) == 90.0


def test_last_word_ignores_a_crumb():
    turns = [(30.0, 90.0, HER), (95.1, 95.2, HER)]
    assert launch.last_word(turns, HER, 95.2) == 90.0


# --- chronique_end --------------------------------------------------------

def test_chronique_end_keeps_the_closing_exchange_and_stops_at_the_next_topic():
    assert launch.chronique_end(TURNS, HER, 90.0, CUTS) == 128.0


def test_chronique_end_without_a_next_topic_uses_the_forward_cut():
    turns = [(30.0, 90.0, HER), (95.0, 100.0, PRES)]
    assert launch.chronique_end(turns, HER, 90.0, [105.0]) == 105.0


def test_chronique_end_without_anyone_after():
    turns = [(30.0, 90.0, HER)]
    assert launch.chronique_end(turns, HER, 90.0, [94.2]) == 94.2


# --- build_span -----------------------------------------------------------

def test_build_span_applies_the_end_trim():
    _, e, _ = launch.build_span("reportage", TURNS, HER, 30.0, 90.0, cuts=CUTS,
                                end_trim=0.5)
    assert e == pytest.approx(93.7)


def test_build_span_end_trim_never_eats_into_her_speech():
    _, e, _ = launch.build_span("reportage", TURNS, HER, 30.0, 90.0, cuts=CUTS,
                                end_trim=999.0)
    assert e == 90.0


def test_build_span_validates_the_name_heard_in_the_launch():
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
# Tours de parole, plans et transcription repris d'un journal de 18h. Chaque
# passage échouait d'une façon différente, et pour des raisons différentes.

P1_TURNS = [
    (38.3, 87.5, PRES),        # titres puis météo, d'une seule traite
    (89.4, 90.4, HER),         # parasites : le générique de l'émission
    (90.6, 91.0, HER),
    (91.3, 91.3, HER),
    (92.5, 92.9, HER),
    (97.2, 126.5, PRES),       # le lancement de SON sujet
    (126.8, 188.7, HER),       # sa vraie prise de parole
    (190.3, 190.4, HER),       # parasite : le plateau est déjà revenu
    (190.4, 223.1, PRES),
]
P1_CUTS = [62.2, 66.1, 67.7, 87.8, 88.5, 89.4, 90.4, 126.6, 189.2, 196.8]
P1_PLATEAU = 189.2

P2_TURNS = [(224.3, 258.6, PRES), (260.3, 288.1, PRES),
            (289.3, 390.5, HER), (392.7, 420.4, PRES)]
P2_CUTS = [276.8, 282.1, 287.5, 291.6, 380.6, 387.1, 391.5, 397.3]
P2_TEXT = [(254.2, 256.6, "et la qualité de l'air sera également mauvaise"),
           (256.8, 258.4, "selon Atmo-Normandie."),
           (260.3, 262.4, "Les vagues de chaleur, à répétition,"),
           (262.6, 266.8, "mettent à l'épreuve certaines de nos infrastructures.")]
P2_PLATEAU = 391.5


def _blocks(turns, min_turn=1.5, gap=60.0):
    her = segments.drop_short(sorted((s, e) for s, e, l in turns if l == HER),
                              min_turn)
    return segments.merge_segments(her, gap)


def test_diarization_crumbs_are_dropped_before_grouping():
    # Sans filtre, quatre miettes du générique ramènent le bloc 37 s trop tôt.
    brut = sorted((s, e) for s, e, l in P1_TURNS if l == HER)
    assert segments.merge_segments(brut, 60.0)[0][0] == 89.4
    assert _blocks(P1_TURNS)[0][0] == 126.8


def test_the_passage_starts_on_the_launch_not_on_the_opening_credits():
    bs, be = _blocks(P1_TURNS)[0]
    start, _, _ = launch.build_span("reportage", P1_TURNS, HER, bs, be,
                                    cuts=P1_CUTS, max_lookback=40.0)
    assert 96.0 <= start <= 97.3      # le tour du présentateur qui la lance
    assert start > 92.9               # plus jamais sur le générique
    assert start > 87.5               # ni sur la météo


def test_the_second_passage_is_not_truncated():
    bs, be = _blocks(P2_TURNS)[0]
    start, _, _ = launch.build_span("reportage", P2_TURNS, HER, bs, be,
                                    cuts=P2_CUTS, transcript=P2_TEXT,
                                    max_lookback=40.0)
    assert 259.5 <= start <= 260.3          # au début du tour, avec l'amorce
    assert start >= 258.4 - launch.MARGIN   # sans mordre la phrase d'avant


@pytest.mark.parametrize("turns,cuts,plateau", [
    (P1_TURNS, P1_CUTS, P1_PLATEAU),
    (P2_TURNS, P2_CUTS, P2_PLATEAU),
])
def test_the_cut_never_reaches_the_studio(turns, cuts, plateau):
    bs, be = _blocks(turns)[0]
    _, end, _ = launch.build_span("reportage", turns, HER, bs, be, cuts=cuts,
                                  end_trim=0.5)
    assert end < plateau


def test_a_stray_fragment_does_not_drag_the_cut_onto_the_studio():
    # Le fragment de 0.1 s à 190.3 est déjà sur le plateau.
    assert launch.last_word(P1_TURNS, HER, 190.4) == 188.7


def test_the_cut_keeps_her_last_word():
    for turns, cuts, last in ((P1_TURNS, P1_CUTS, 188.7),
                              (P2_TURNS, P2_CUTS, 390.5)):
        bs, be = _blocks(turns)[0]
        _, end, _ = launch.build_span("reportage", turns, HER, bs, be,
                                      cuts=cuts, end_trim=0.5)
        assert end >= last


def test_the_rule_holds_without_any_transcript():
    # Le repère est le tour de parole : le texte n'est pas nécessaire.
    for turns, cuts in ((P1_TURNS, P1_CUTS), (P2_TURNS, P2_CUTS)):
        bs, be = _blocks(turns)[0]
        avec = launch.build_span("reportage", turns, HER, bs, be, cuts=cuts,
                                 transcript=P2_TEXT)[0]
        sans = launch.build_span("reportage", turns, HER, bs, be, cuts=cuts)[0]
        assert abs(avec - sans) <= launch.MARGIN + 0.01
