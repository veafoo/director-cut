def merge_segments(segs, max_gap):
    """Fusionne les segments séparés par un trou <= max_gap secondes."""
    if not segs:
        return []
    segs = sorted(segs)
    out = [list(segs[0])]
    for s, e in segs[1:]:
        if s - out[-1][1] <= max_gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [tuple(x) for x in out]


def pad_segments(segs, pad, duration=None):
    """Ajoute une marge de respiration avant/après chaque segment."""
    out = []
    for s, e in segs:
        s2 = max(0.0, s - pad)
        e2 = e + pad
        if duration is not None:
            e2 = min(duration, e2)
        out.append((s2, e2))
    return out


def snap_to_scenes(segs, cuts, tol=2.0):
    """Cale chaque borne sur le changement de plan le plus proche (< tol s)."""
    if not cuts:
        return segs
    cuts = sorted(cuts)

    def nearest(t):
        c = min(cuts, key=lambda x: abs(x - t))
        return c if abs(c - t) <= tol else t

    return [(nearest(s), nearest(e)) for s, e in segs]


def drop_short(segs, min_len):
    return [(s, e) for s, e in segs if (e - s) >= min_len]


def _words(transcript, start, end):
    """Mots prononcés dans [start, end], normalisés pour la comparaison."""
    import unicodedata
    text = " ".join(tx for ts, te, tx in transcript if te > start and ts < end)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else " " for c in text.lower()).split()


def drop_reruns(spans, transcript, threshold=0.75):
    """Écarte les rediffusions d'un même sujet.

    Une matinale repasse le même reportage plusieurs fois dans la journée : la
    voix est là à chaque diffusion, et on sortait le sujet en trois exemplaires.
    Deux passages qui disent la même chose sont la même chose — le commentaire
    est écrit une fois, il est identique à chaque rediffusion.

    On garde la version la plus longue de chaque groupe : une rediffusion est
    parfois raccourcie, autant conserver la plus complète.
    """
    import difflib
    if not transcript or len(spans) < 2:
        return list(spans), []

    scripts = [(sp, _words(transcript, *sp)) for sp in spans]
    kept, reruns = [], []
    for span, words in scripts:
        twin = None
        for i, (kspan, kwords) in enumerate(kept):
            if not words or not kwords:
                continue
            # Inclusion, pas ressemblance : une rediffusion est parfois
            # raccourcie, et le texte court est alors contenu dans le long.
            # Une similarité symétrique la ferait passer pour un autre sujet.
            m = difflib.SequenceMatcher(None, kwords, words, autojunk=False)
            common = sum(b.size for b in m.get_matching_blocks())
            if common / min(len(kwords), len(words)) >= threshold:
                twin = i
                break
        if twin is None:
            kept.append((span, words))
        elif span[1] - span[0] > kept[twin][0][1] - kept[twin][0][0]:
            reruns.append(kept[twin][0])       # la gardée était plus courte
            kept[twin] = (span, words)
        else:
            reruns.append(span)
    return [sp for sp, _ in kept], sorted(reruns)
