"""Libération des modèles : ce qui a fini de servir doit quitter la mémoire.

Trois modèles chargés en même temps (diarisation, empreinte, transcription)
suffisent à faire tuer le processus par le système sur une machine juste.
"""
from director_cut import embeddings


def test_liberer_l_empreinte_vide_le_cache():
    embeddings._inference = object()
    embeddings.unload()
    assert embeddings._inference is None


def test_liberer_sans_rien_de_charge_ne_fait_rien():
    embeddings._inference = None
    embeddings.unload()
    assert embeddings._inference is None


def test_rendre_la_memoire_ne_leve_jamais():
    embeddings.free_memory()
