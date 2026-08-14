"""Gabarits de vignettes 9:16 : quel logo, posé où.

Un gabarit = un PNG déposé dans `brands/` + une position. La position est
exprimée en fractions de l'image de sortie (et pas en pixels) pour rester
valable quelle que soit la définition.

Les valeurs par défaut sont relevées au pixel près sur des vignettes réellement
publiées par les chaînes concernées : marge gauche, marge haute, et hauteur du
logo. Une chaîne absente de `PLACEMENTS` prend `DEFAULT_PLACEMENT`, et un
fichier `brands/<nom>.json` écrase le tout si on veut caler autre chose.
"""
import json
import os
from dataclasses import dataclass

# Format des vignettes réseaux sociaux (Instagram / TikTok / Reels).
OUT_W, OUT_H = 1080, 1920

# Relevé sur les vignettes publiées. left/top = coin haut-gauche du logo,
# height = hauteur du logo ; le tout en fraction de l'image de sortie.
#
# strip_top / strip_bottom : bandes de la source à jeter AVANT le recadrage,
# en fraction de la hauteur source. Sert à sortir l'habillage antenne du cadre
# (logo de chaîne, horloge, météo en haut ; bandeau titre et bandeau déroulant
# en bas). À 0, la vignette prend toute la hauteur de l'image : plus net, mais
# le bandeau du direct s'y retrouve coupé en deux.
PLACEMENTS = {
    "bfmtv":         {"left": 0.0759, "top": 0.1969, "height": 0.1156},
    "bfm_normandie": {"left": 0.0759, "top": 0.1969, "height": 0.1151},
    "tf1":           {"left": 0.0713, "top": 0.2646, "height": 0.0703},
}

# Chaîne inconnue : on reprend le placement BFM, le plus courant des trois.
DEFAULT_PLACEMENT = {"left": 0.0759, "top": 0.1969, "height": 0.1151}

# Habillage antenne relevé sur le flux BFM Normandie 1280x720 : 100 px en haut
# (logo + horloge + météo), 175 px en bas (titre + bandeau déroulant).
STRIPS = {
    "bfm_normandie": {"strip_top": 0.139, "strip_bottom": 0.243},
    "bfmtv":         {"strip_top": 0.139, "strip_bottom": 0.243},
}

# Emprise exacte de chaque élément d'habillage, en fractions de la frame source
# (gauche, haut, droite, bas). Sert de masque à l'effacement IA, qui reconstruit
# le décor derrière — d'où des boîtes serrées plutôt que des bandes entières.
#
# Une boîte qui touche un bord de l'image doit aller JUSQU'AU bord : un liseré
# de graphisme oublié et le modèle recopie sa couleur sur toute la zone.
#
# Un élément qui n'est pas toujours à l'antenne (le synthé qui nomme un
# interviewé, par exemple) porte une `color` : il n'est effacé que si cette
# couleur couvre au moins `cover` de la boîte. Sans ça, on effacerait de la
# vraie image chaque fois que le synthé est absent.
#
# Relevé sur BFM Normandie. Pour une autre chaîne, poser les valeurs dans
# brands/<nom>.json sous la clé "furniture".
FURNITURE = {
    "bfm_normandie": [
        {"box": (0.0,    0.0,   0.2266, 0.1417)},  # logo chaîne + horloge
        {"box": (0.8047, 0.0,   1.0,    0.1528)},  # météo
        {"box": (0.043,  0.750, 0.8398, 0.8639)},  # bandeau titre
        {"box": (0.0,    0.840, 1.0,    1.0)},     # bandeau déroulant
        # synthé d'interview (nom, âge, commune) : intermittent
        {"box": (0.651, 0.211, 0.906, 0.511),
         "color": (49, 49, 109), "cover": 0.10},
    ],
}

BRANDS_DIR = "brands"


@dataclass(frozen=True)
class Furniture:
    """Un élément d'habillage. box = (gauche, haut, droite, bas) en fractions
    de la frame source. color/cover : voir FURNITURE."""
    box: tuple
    color: tuple = None
    cover: float = 0.10

    @classmethod
    def parse(cls, item):
        if isinstance(item, dict):
            return cls(box=tuple(item["box"]),
                       color=tuple(item["color"]) if item.get("color") else None,
                       cover=float(item.get("cover", 0.10)))
        return cls(box=tuple(item))


@dataclass(frozen=True)
class Brand:
    name: str
    logo: str
    left: float
    top: float
    height: float
    strip_top: float = 0.0
    strip_bottom: float = 0.0
    furniture: tuple = ()

    def box(self, w=OUT_W, h=OUT_H):
        """(x, y, hauteur) en pixels pour une sortie w x h."""
        return round(self.left * w), round(self.top * h), round(self.height * h)


def _dir(workdir):
    return os.path.join(workdir or ".", BRANDS_DIR)


def available(workdir="."):
    """Noms des gabarits utilisables = les PNG présents dans brands/."""
    d = _dir(workdir)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-4] for f in os.listdir(d) if f.lower().endswith(".png"))


def load(name, workdir=".", strip=False):
    """Charge un gabarit par son nom. Lève ValueError si le logo manque.

    strip=True active le retrait de l'habillage antenne (voir STRIPS)."""
    logo = os.path.join(_dir(workdir), f"{name}.png")
    if not os.path.exists(logo):
        found = available(workdir)
        raise ValueError(
            f"Pas de logo pour '{name}'. Dépose brands/{name}.png"
            + (f" (disponibles : {', '.join(found)})" if found else
               " (le dossier brands/ est vide)"))

    place = dict(PLACEMENTS.get(name, DEFAULT_PLACEMENT))
    if strip:
        place.update(STRIPS.get(name, {}))
    override = os.path.join(_dir(workdir), f"{name}.json")
    if os.path.exists(override):
        with open(override, encoding="utf-8") as f:
            place.update(json.load(f))
    furniture = place.get("furniture", FURNITURE.get(name, ()))
    return Brand(name=name, logo=logo, left=place["left"], top=place["top"],
                 height=place["height"],
                 strip_top=place.get("strip_top", 0.0),
                 strip_bottom=place.get("strip_bottom", 0.0),
                 furniture=tuple(Furniture.parse(f) for f in furniture))


def auto(name, workdir=".", strip=False):
    """Gabarit à appliquer sans que la personne ait à le nommer.

    Nom explicite -> ce gabarit. Sinon, s'il n'y a qu'un seul logo dans
    brands/, c'est forcément celui-là. Plusieurs logos et aucun choix -> aucun
    logo (on ne devine pas la chaîne à sa place)."""
    if name:
        return load(name, workdir, strip)
    found = available(workdir)
    if len(found) == 1:
        return load(found[0], workdir, strip)
    return None
