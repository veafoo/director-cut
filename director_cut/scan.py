"""Repérer sa voix au gros grain, pour ne diariser que ce qui la concerne.

Une matinale de deux heures diarisée en entier coûte une demi-heure de calcul
pour trois minutes de reportage : pyannote calcule une empreinte pour chaque
tour de parole de chaque personne présente, alors qu'une seule nous intéresse.

Mesuré sur la machine de développement : la diarisation complète coûte 16,7 s
par minute d'audio, le balayage ci-dessous 1,48 s — **onze fois moins**. On
balaye donc d'abord, puis on diarise seulement autour de ce qu'on a trouvé.

Le filet, parce qu'un passage raté est pire qu'un run lent :

- on balaye avec un seuil **abaissé** (RECUL_SEUIL) : mieux vaut garder une
  zone pour rien que d'en manquer une ;
- chaque zone est élargie (MARGE) pour contenir l'annonce du présentateur
  avant elle et le retour plateau après ;
- si le balayage ne trouve rien, ou retient plus de PART_MAX de la source, on
  revient à la diarisation complète — dans un cas parce qu'on ne peut pas
  conclure, dans l'autre parce qu'il n'y a plus rien à économiser.
"""
import os

import numpy as np
import soundfile as sf

from . import audio, embeddings, segments

FENETRE = 4.0        # durée d'un coup de sonde
PAS = 8.0            # une sonde toutes les 8 s : une prise de parole de 10 s
                     # en croise toujours au moins une
MARGE = 30.0         # de quoi contenir l'annonce et le retour plateau
RECUL_SEUIL = 0.15   # on balaye plus large que le seuil d'identification
PART_MAX = 0.6       # au-delà, autant tout diariser d'un coup


def voice_regions(wav_path, reference, threshold, window=FENETRE, step=PAS,
                  margin=MARGE, on_progress=None):
    """Les zones où sa voix apparaît, au gros grain.

    Rien n'est décidé ici : ces zones servent uniquement à savoir où lancer la
    vraie diarisation. Elles sont donc volontairement trop larges."""
    info = sf.info(wav_path)
    duree, sr = info.duration, info.samplerate
    seuil = threshold - RECUL_SEUIL
    trouves = []
    debut = 0.0
    while debut + window <= duree:
        bloc, _ = sf.read(wav_path, start=int(debut * sr),
                          frames=int(window * sr), dtype="float32")
        if bloc.ndim > 1:
            bloc = bloc.mean(axis=1)
        if embeddings.cosine(embeddings.embed_array(bloc, sr), reference) >= seuil:
            trouves.append((debut, debut + window))
        debut += step
        if on_progress:
            on_progress(min(debut, duree), duree)
    if not trouves:
        return []
    larges = [(max(0.0, s - margin), min(e + margin, duree)) for s, e in trouves]
    return segments.merge_segments(larges, 0.0)


def couverture(regions, duree):
    """Quelle part de la source les zones retenues représentent."""
    if not duree:
        return 1.0
    return sum(e - s for s, e in regions) / duree


def vaut_le_coup(regions, duree):
    """Faut-il diariser par zones, ou tout reprendre depuis le début ?

    Aucune zone : le balayage n'a rien vu, on ne peut pas en conclure qu'elle
    est absente — c'est à la diarisation de le dire. Trop de zones : il n'y a
    plus rien à économiser, et découper coûterait plus que ça ne rapporte."""
    return bool(regions) and couverture(regions, duree) <= PART_MAX


def _empreinte_locuteur(wav_path, tours, sr, max_sec=20.0):
    """Empreinte d'un locuteur à partir de ses plus longs tours dans la zone."""
    pris, morceaux = 0.0, []
    for deb, fin in sorted(tours, key=lambda t: t[1] - t[0], reverse=True):
        bloc, _ = sf.read(wav_path, start=int(deb * sr),
                          frames=int((fin - deb) * sr), dtype="float32")
        if bloc.ndim > 1:
            bloc = bloc.mean(axis=1)
        morceaux.append(bloc)
        pris += fin - deb
        if pris >= max_sec:
            break
    if not morceaux:
        return None
    return embeddings.embed_array(np.concatenate(morceaux), sr)


def _rattacher(vecteur, connus, seuil=0.5):
    """Rendre à ce locuteur l'identité qu'il avait dans une autre zone.

    Chaque zone est diarisée séparément : son « SPEAKER_00 » n'a aucun rapport
    avec celui de la zone d'à côté. Or la découpe a besoin d'identités valables
    sur toute la source — c'est comme ça qu'elle reconnaît le présentateur, à
    sa présence d'un bout à l'autre du journal."""
    if vecteur is None:
        return None
    meilleur, score = None, seuil
    for nom, vec in connus.items():
        s = embeddings.cosine(vecteur, vec)
        if s >= score:
            meilleur, score = nom, s
    if meilleur is None:
        meilleur = f"SPEAKER_{len(connus):02d}"
        connus[meilleur] = vecteur
    return meilleur


def diarize_regions(wav_path, regions, diariser, workdir):
    """Diarise chaque zone, puis recolle les identités entre les zones.

    `diariser` prend un chemin de wav et rend [(debut, fin, label), ...] —
    injecté pour que cette fonction reste testable sans modèle."""
    sr = sf.info(wav_path).samplerate
    connus, tours = {}, []
    for i, (deb, fin) in enumerate(regions):
        morceau = audio.extract_wav_span(
            wav_path, deb, fin, os.path.join(workdir, f"_zone_{i:02d}.wav"))
        try:
            locaux = diariser(morceau)
            par_label = {}
            for s, e, label in locaux:
                par_label.setdefault(label, []).append((s, e))
            identites = {}
            for label, ses_tours in par_label.items():
                identites[label] = _rattacher(
                    _empreinte_locuteur(morceau, ses_tours, sr), connus)
            for s, e, label in locaux:
                if identites.get(label):
                    tours.append((deb + s, deb + e, identites[label]))
        finally:
            if os.path.exists(morceau):
                os.remove(morceau)
    return sorted(tours)


def duree_audio(wav_path):
    return sf.info(wav_path).duration
