import difflib
import unicodedata


def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


def name_in_text(text, names, fuzzy=0.82):
    """Détecte un nom (ou variante) de façon tolérante (Whisper écorche les
    noms propres) : insensible casse/accents/espaces + correspondance floue."""
    nt = _norm(text)
    if not nt:
        return False
    for name in names:
        nn = _norm(name)
        if not nn:
            continue
        if nn in nt:
            return True
        L = len(nn)
        for i in range(0, max(1, len(nt) - L + 1)):
            if difflib.SequenceMatcher(None, nt[i:i + L], nn).ratio() >= fuzzy:
                return True
    return False


def turns(diarization):
    """Liste triée des tours de parole : (debut, fin, label).
    Accepte soit une liste déjà normalisée, soit une Annotation pyannote."""
    if isinstance(diarization, list):
        return sorted(diarization)
    return sorted((t.start, t.end, lab)
                  for t, _, lab in diarization.itertracks(yield_label=True))


def _text_between(transcript, t0, t1):
    return " ".join(tx for (ts, te, tx) in transcript if te > t0 and ts < t1)


def _plateau_cut_before(t, cuts, precut_window, floor):
    """Le cut de retour plateau : changement de plan juste avant l'instant t
    (avant que quelqu'un ne prenne la parole sur le plateau)."""
    if not cuts:
        return t
    cand = [c for c in cuts if t - precut_window <= c <= t + 0.5]
    if not cand:
        return t
    return max(min(cand, key=lambda x: abs(x - t)), floor)


def _cut_forward(t, cuts, window=15.0):
    if not cuts:
        return t
    cand = [c for c in cuts if t <= c <= t + window]
    return min(cand) if cand else t


def launch_start(all_turns, her_label, block_start, cuts,
                 max_lookback=40.0, launch_gap=10.0, precut_window=5.0):
    """Début = plateau d'annonce le plus proche de sa 1re parole. On borne par
    la parole continue de l'animateur juste avant elle, puis on prend le DERNIER
    changement de plan avant elle dans cette fenêtre : ça capte toute l'annonce
    sans jamais remonter jusqu'à l'ouverture du JT / la météo."""
    cuts = sorted(cuts or [])
    preceding = sorted((s, e, lab) for s, e, lab in all_turns
                       if e <= block_start + 0.01 and lab != her_label)
    speech_start = block_start
    if preceding:
        anchor_label = preceding[-1][2]
        anchor_turns = [t for t in preceding if t[2] == anchor_label]
        speech_start = anchor_turns[-1][0]
        prev = anchor_turns[-1][0]
        for s, e, _ in reversed(anchor_turns):
            if prev - e > launch_gap:
                break
            if block_start - s > max_lookback:
                break
            speech_start = s
            prev = s

    lo = max(speech_start, block_start - max_lookback)
    cand = [c for c in cuts if lo - precut_window <= c <= block_start - 2.0]
    if cand:
        return max(cand)          # plateau d'annonce le plus proche d'elle
    return lo


def reportage_end(all_turns, her_label, block_end, cuts, precut_window=5.0):
    """Fin = retour plateau après le reportage, SANS montrer le présentateur :
    on coupe au cut, juste avant qu'il ne reparle."""
    after = sorted((s, e, lab) for s, e, lab in all_turns
                   if s >= block_end - 0.01 and lab != her_label)
    if not after:
        return _cut_forward(block_end, cuts)
    anchor_next = after[0][0]
    end = _plateau_cut_before(anchor_next, cuts, precut_window, block_end)
    return max(end, block_end)


def chronique_end(all_turns, her_label, block_end, cuts,
                  launch_gap=10.0, precut_window=5.0):
    """Fin = début de l'annonce du sujet suivant. On garde l'échange de clôture
    (le « merci <nom> » du présentateur), on coupe au plateau du sujet d'après."""
    after = sorted((s, e, lab) for s, e, lab in all_turns
                   if s >= block_end - 0.01 and lab != her_label)
    if not after:
        return _cut_forward(block_end, cuts)
    # échange de clôture = tours contigus juste après elle (gap <= launch_gap)
    prev, last, idx = block_end, block_end, 0
    while idx < len(after) and after[idx][0] - prev <= launch_gap:
        prev = after[idx][1]
        last = after[idx][1]
        idx += 1
    if idx < len(after):                       # une vraie coupure -> sujet suivant
        next_launch = after[idx][0]
        return _plateau_cut_before(next_launch, cuts, precut_window, last)
    return _cut_forward(last, cuts)            # pas de sujet suivant identifié


def build_span(mode, all_turns, her_label, block_start, block_end, cuts=None,
               transcript=None, names=None, max_lookback=40.0, launch_gap=10.0,
               precut_window=5.0, end_trim=0.5):
    """Renvoie (start, end, name_validated) selon le mode.
    end_trim : marge retirée en fin pour ne jamais montrer le retour plateau."""
    start = launch_start(all_turns, her_label, block_start, cuts,
                         max_lookback, launch_gap, precut_window)
    if mode == "reportage":
        end = reportage_end(all_turns, her_label, block_end, cuts, precut_window)
    else:  # chronique
        end = chronique_end(all_turns, her_label, block_end, cuts,
                            launch_gap, precut_window)
    # marge de sécurité : couper un poil avant le plan de retour plateau
    end = max(block_end, end - end_trim)
    validated = None
    if transcript and names:
        validated = name_in_text(_text_between(transcript, start, block_start),
                                 names)
    return start, end, validated
