"""Retouche IA : masque d'habillage, détection d'un élément intermittent,
enchaînement des étapes. Les deux modèles ne sont pas chargés ici — on vérifie
la logique autour, les poids se valident sur un rendu réel."""
import numpy as np
import pytest

from director_cut import enhance
from director_cut.brands import Furniture

SHAPE = (720, 1280, 3)
NAVY = (49, 49, 109)


def _frame(color=(200, 200, 200)):
    f = np.zeros(SHAPE, np.uint8)
    f[:, :] = color
    return f


def _fill(frame, box, color):
    h, w = frame.shape[:2]
    l, t, r, b = box
    frame[int(t * h):int(b * h), int(l * w):int(r * w)] = color
    return frame


# --- masque ---------------------------------------------------------------

def test_a_box_becomes_a_masked_rectangle():
    item = Furniture(box=(0.0, 0.0, 0.5, 0.25))
    m = enhance.furniture_mask(SHAPE, [item], grow=0)
    assert m[:180, :640].all()
    assert not m[181:, 641:].any()


def test_boxes_are_grown_a_little():
    # Un liseré de graphisme oublié et le modèle recopie sa couleur partout.
    tight = enhance.furniture_mask(SHAPE, [Furniture(box=(0.2, 0.2, 0.3, 0.3))],
                                   grow=0)
    grown = enhance.furniture_mask(SHAPE, [Furniture(box=(0.2, 0.2, 0.3, 0.3))],
                                   grow=6)
    assert grown.sum() > tight.sum()


def test_growing_never_leaves_the_image():
    m = enhance.furniture_mask(SHAPE, [Furniture(box=(0.0, 0.0, 1.0, 1.0))],
                               grow=50)
    assert m.shape == SHAPE[:2]
    assert m.all()


def test_several_elements_are_combined():
    items = [Furniture(box=(0.0, 0.0, 0.2, 0.1)),
             Furniture(box=(0.0, 0.9, 1.0, 1.0))]
    m = enhance.furniture_mask(SHAPE, items, grow=0)
    assert m[0, 0] and m[-1, -1]
    assert not m[360, 640]


def test_no_element_means_no_mask():
    assert not enhance.furniture_mask(SHAPE, [], grow=0).any()


# --- élément intermittent -------------------------------------------------

def test_a_permanent_element_is_always_erased():
    assert enhance.is_present(None, Furniture(box=(0, 0, 1, 1))) is True


def test_an_intermittent_element_is_erased_when_its_colour_is_there():
    box = (0.651, 0.211, 0.906, 0.511)
    item = Furniture(box=box, color=NAVY, cover=0.10)
    frame = _fill(_frame(), box, NAVY)
    assert enhance.is_present(frame, item)


def test_an_intermittent_element_is_left_alone_when_absent():
    # Le décor naturel n'a pas l'aplat de la charte : on n'efface pas de la
    # vraie image sur une supposition.
    item = Furniture(box=(0.651, 0.211, 0.906, 0.511), color=NAVY, cover=0.10)
    assert not enhance.is_present(_frame((120, 170, 210)), item)


def test_a_touch_of_the_colour_is_not_enough():
    box = (0.6, 0.2, 0.9, 0.5)
    item = Furniture(box=box, color=NAVY, cover=0.50)
    frame = _frame()
    # seulement un cinquième de la boîte à la bonne couleur
    frame[144:187, 768:1152] = NAVY
    assert not enhance.is_present(frame, item)


def test_an_intermittent_element_is_not_erased_without_a_frame_to_check():
    item = Furniture(box=(0, 0, 1, 1), color=NAVY)
    assert enhance.is_present(None, item) is False
    assert not enhance.furniture_mask(SHAPE, [item]).any()


def test_the_mask_only_holds_what_is_on_screen():
    box = (0.651, 0.211, 0.906, 0.511)
    always = Furniture(box=(0.0, 0.9, 1.0, 1.0))
    sometimes = Furniture(box=box, color=NAVY, cover=0.10)
    frame = _frame()                      # synthé absent
    m = enhance.furniture_mask(frame.shape, [always, sometimes], frame=frame)
    assert m[700, 640]                    # le bandeau permanent est masqué
    assert not m[260, 1000]               # le synthé, non


# --- recadrage ------------------------------------------------------------

def test_crop_gives_the_target_ratio():
    out = enhance.crop_9_16(_frame())
    h, w = out.shape[:2]
    assert w / h == pytest.approx(9 / 16, abs=0.01)


def test_crop_is_centred():
    frame = _frame()
    frame[:, 630:650] = (255, 0, 0)       # repère au centre
    out = enhance.crop_9_16(frame)
    mid = out[:, out.shape[1] // 2]
    assert (mid[:, 0] == 255).all()


def test_crop_of_an_already_vertical_image_changes_nothing():
    tall = np.zeros((1920, 1080, 3), np.uint8)
    assert enhance.crop_9_16(tall).shape == tall.shape


# --- enchaînement ---------------------------------------------------------

@pytest.fixture
def steps(monkeypatch):
    """Remplace les deux modèles pour suivre l'ordre des opérations."""
    seen = []

    def fake_erase(rgb, mask):
        seen.append(("erase", rgb.shape, float(mask.mean())))
        return rgb

    def fake_upscale(rgb, **kw):
        seen.append(("upscale", rgb.shape))
        return np.repeat(np.repeat(rgb, 4, 0), 4, 1)

    monkeypatch.setattr(enhance, "erase", fake_erase)
    monkeypatch.setattr(enhance, "upscale", fake_upscale)
    return seen


def test_the_frame_is_cleaned_before_being_cropped(steps):
    # Le modèle a besoin de toute l'image autour du bandeau pour reconstruire.
    enhance.prepare(_frame(), boxes=[Furniture(box=(0.0, 0.9, 1.0, 1.0))])
    assert steps[0][0] == "erase"
    assert steps[0][1] == SHAPE           # frame entière, pas le recadrage


def test_the_upscale_comes_after_the_crop(steps):
    enhance.prepare(_frame(), boxes=[Furniture(box=(0.0, 0.9, 1.0, 1.0))])
    kinds = [s[0] for s in steps]
    assert kinds == ["erase", "upscale"]
    # on ne sur-résout pas les deux tiers d'image qui partent au recadrage
    assert steps[1][1][1] < SHAPE[1]


def test_cleaning_can_be_switched_off(steps):
    enhance.prepare(_frame(), boxes=[Furniture(box=(0, 0, 1, 1))], clean=False)
    assert [s[0] for s in steps] == ["upscale"]


def test_upscaling_can_be_switched_off(steps):
    enhance.prepare(_frame(), boxes=[Furniture(box=(0.0, 0.9, 1.0, 1.0))],
                    sharpen=False)
    assert [s[0] for s in steps] == ["erase"]


def test_an_image_already_big_enough_is_not_upscaled(steps):
    big = np.zeros((3840, 2160, 3), np.uint8)
    enhance.prepare(big, clean=False)
    assert steps == []


def test_nothing_to_erase_means_the_model_is_not_called(steps):
    # Synthé absent et rien d'autre : pas la peine de réveiller le GPU.
    item = Furniture(box=(0, 0, 0.5, 0.5), color=NAVY, cover=0.5)
    enhance.prepare(_frame(), boxes=[item], sharpen=False)
    assert steps == []


def test_stripping_removes_the_edge_bands_before_cropping(steps):
    out_plain = enhance.prepare(_frame(), clean=False, sharpen=False)
    out_strip = enhance.prepare(_frame(), clean=False, sharpen=False,
                                strip_top=0.139, strip_bottom=0.243)
    assert out_strip.shape[0] < out_plain.shape[0]
    assert out_strip.shape[1] / out_strip.shape[0] == pytest.approx(9 / 16,
                                                                    abs=0.01)


# --- modèles --------------------------------------------------------------

def test_missing_lists_what_has_to_be_downloaded(monkeypatch):
    monkeypatch.setattr(enhance, "is_ready", lambda n: n == "lama")
    assert enhance.missing(clean=True, sharpen=True) == ["esrgan"]
    assert enhance.missing(clean=True, sharpen=False) == []
    assert enhance.missing(clean=False, sharpen=True) == ["esrgan"]


def test_every_model_has_a_name_and_a_url():
    for name, (filename, url) in enhance.MODELS.items():
        assert filename and url.startswith("https://")
        assert enhance.model_path(name).endswith(filename)


def test_download_does_not_refetch_an_existing_model(monkeypatch, tmp_path):
    monkeypatch.setattr(enhance, "CACHE", str(tmp_path))
    (tmp_path / enhance.MODELS["lama"][0]).write_bytes(b"deja la")
    monkeypatch.setattr(enhance.subprocess, "run",
                        lambda *a, **k: pytest.fail("aucun téléchargement"))
    assert enhance.download("lama").endswith(enhance.MODELS["lama"][0])
