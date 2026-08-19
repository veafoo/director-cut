"""Mesurer le temps de chaque étape, et le rendre lisible.

Sur une source de deux heures, savoir que le run a duré quarante minutes ne
sert à rien ; savoir que trente-cinq sont parties dans la diarisation dit quoi
optimiser. Le détail par étape est donc affiché à la fin de chaque vidéo, et
récapitulé par vidéo quand la commande en traite plusieurs.
"""
import time
from contextlib import contextmanager


def hms(secondes):
    """Une durée en HH:MM:SS.

    Les heures ne débordent pas à 24 : un run de vingt-six heures s'écrit
    26:00:00, pas 02:00:00."""
    secondes = max(0, int(round(secondes)))
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class Chrono:
    """Le temps passé par étape, dans l'ordre où elles se présentent.

    L'horloge est injectable pour que les tests n'aient pas à dormir."""

    def __init__(self, horloge=time.monotonic):
        self._horloge = horloge
        self._debut = horloge()
        self._etapes = {}
        self._en_cours = None

    @contextmanager
    def step(self, nom):
        depart = self._horloge()
        try:
            yield
        finally:
            # Une étape interrompue par une erreur compte quand même : c'est
            # souvent celle qu'on cherche à comprendre.
            self._etapes[nom] = (self._etapes.get(nom, 0.0)
                                 + self._horloge() - depart)

    def mark(self, nom):
        """Ouvre une étape, et ferme celle d'avant.

        Sur une chaîne linéaire comme la nôtre, c'est plus lisible qu'un bloc
        imbriqué par étape : une ligne avant chaque étape, et rien à refermer.
        """
        self._fermer()
        self._en_cours = (nom, self._horloge())

    def _fermer(self):
        if self._en_cours is None:
            return
        nom, depart = self._en_cours
        self._etapes[nom] = (self._etapes.get(nom, 0.0)
                             + self._horloge() - depart)
        self._en_cours = None

    def stop(self):
        """Ferme l'étape en cours. Appelé avant d'afficher le détail."""
        self._fermer()

    def items(self):
        """[(étape, secondes), …] dans l'ordre de première apparition."""
        return list(self._etapes.items())

    @property
    def total(self):
        """Le temps écoulé depuis le début, pas la somme des étapes.

        Ce qui se passe entre deux étapes compte aussi dans l'attente."""
        return self._horloge() - self._debut
