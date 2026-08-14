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
