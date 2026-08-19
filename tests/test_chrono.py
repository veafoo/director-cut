"""Chronométrage du run : format des durées et comptage par étape.

L'horloge est injectée : un test qui dort est un test qu'on finit par
désactiver.
"""
import pytest
from rich.console import Console

from director_cut import chrono, ui


@pytest.mark.parametrize("secondes,attendu", [
    (0, "00:00:00"),
    (1, "00:00:01"),
    (59, "00:00:59"),
    (60, "00:01:00"),
    (3600, "01:00:00"),
    (3661, "01:01:01"),
    (59.6, "00:01:00"),          # arrondi, pas troncature
    (-5, "00:00:00"),            # une durée négative n'existe pas
])
def test_durations_are_written_hh_mm_ss(secondes, attendu):
    assert chrono.hms(secondes) == attendu


def test_hours_do_not_wrap_at_a_day():
    """Un run de 26 h s'écrit 26:00:00, pas 02:00:00."""
    assert chrono.hms(26 * 3600) == "26:00:00"


def _horloge():
    t = [0.0]
    return t, (lambda: t[0])


def test_each_step_is_counted_separately():
    t, h = _horloge()
    c = chrono.Chrono(horloge=h)
    c.mark("Téléchargement"); t[0] += 128
    c.mark("Diarisation"); t[0] += 1260
    c.stop()
    assert c.items() == [("Téléchargement", 128.0), ("Diarisation", 1260.0)]


def test_a_step_met_twice_adds_up():
    t, h = _horloge()
    c = chrono.Chrono(horloge=h)
    c.mark("Transcription"); t[0] += 10
    c.mark("Découpe"); t[0] += 5
    c.mark("Transcription"); t[0] += 3
    c.stop()
    assert dict(c.items())["Transcription"] == 13.0


def test_the_total_is_the_wait_not_the_sum_of_steps():
    """Ce qui se passe entre deux étapes fait quand même attendre."""
    t, h = _horloge()
    c = chrono.Chrono(horloge=h)
    t[0] += 7                     # avant la première étape
    c.mark("Diarisation"); t[0] += 10
    c.stop()
    t[0] += 4                     # après la dernière
    assert dict(c.items())["Diarisation"] == 10.0
    assert c.total == 21.0


def test_stopping_twice_does_not_count_twice():
    t, h = _horloge()
    c = chrono.Chrono(horloge=h)
    c.mark("Diarisation"); t[0] += 10
    c.stop(); t[0] += 100
    c.stop()
    assert dict(c.items())["Diarisation"] == 10.0


def test_a_step_that_fails_is_still_counted():
    """C'est souvent l'étape qui a planté qu'on cherche à comprendre."""
    t, h = _horloge()
    c = chrono.Chrono(horloge=h)
    with pytest.raises(ValueError):
        with c.step("Diarisation"):
            t[0] += 12
            raise ValueError("pyannote a lâché")
    assert dict(c.items())["Diarisation"] == 12.0


def _rendu(fn, *args):
    console = Console(width=70, force_terminal=False, no_color=True)
    with console.capture() as cap:
        fn(console, *args)
    return cap.get()


def test_the_breakdown_shows_each_step_and_its_share():
    t, h = _horloge()
    c = chrono.Chrono(horloge=h)
    c.mark("Téléchargement"); t[0] += 60
    c.mark("Diarisation"); t[0] += 240
    c.stop()
    sortie = _rendu(ui.timings, c)
    assert "Téléchargement" in sortie and "00:01:00" in sortie
    assert "Diarisation" in sortie and "00:04:00" in sortie
    assert "80 %" in sortie          # la part dit où chercher
    assert "00:05:00" in sortie      # total


def test_the_breakdown_survives_a_run_with_no_step():
    c = chrono.Chrono(horloge=lambda: 0.0)
    assert "00:00:00" in _rendu(ui.timings, c)


def test_the_recap_lists_each_video_and_the_grand_total():
    sortie = _rendu(ui.timings_recap,
                    [("bonjour-la-normandie", 1650.0), ("jt-19h (échec)", 940.0)])
    assert "bonjour-la-normandie" in sortie and "00:27:30" in sortie
    assert "jt-19h (échec)" in sortie and "00:15:40" in sortie
    assert "00:43:10" in sortie
