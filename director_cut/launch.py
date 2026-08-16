import difflib
import unicodedata


# Amorce avant le début du lancement. Les horodatages sont approximatifs :
# démarrer pile dessus rogne la première syllabe. On ne mord jamais plus que
# MARGIN sur la phrase d'avant, dont la fin est de toute façon du silence.
LEAD_IN = 0.4
MARGIN = 0.15

# Sous cette durée, une prise de parole est un parasite de diarisation, pas un
# tour de parole.
MIN_TURN = 1.5


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


def _lead_in(anchor, transcript):
    """Recule un peu avant `anchor`, sans mordre la phrase précédente."""
    begin = anchor - LEAD_IN
    if transcript:
        before = [e for _, e, _ in transcript if e <= anchor + 0.01]
        if before:
            begin = max(begin, max(before) - MARGIN)
    return min(begin, anchor)


def _sentence_at_or_after(transcript, t):
    """Début de la première phrase qui commence à `t` ou après."""
    if not transcript:
        return None
    starts = sorted(st for st, _, _ in transcript if st >= t - 0.01)
    return starts[0] if starts else None


def launch_start(all_turns, her_label, block_start, cuts,
                 max_lookback=40.0, launch_gap=10.0, precut_window=5.0,
                 transcript=None, names=(), min_turn=MIN_TURN):
    """Début du passage = la prise de parole qui précède la sienne.

    Le lancement, c'est le présentateur qui parle juste avant elle. On démarre
    donc au début de SA prise de parole. Ce repère est structurel : il ne
    dépend d'aucune tournure, d'aucune chaîne, d'aucune langue.

    Deux versions précédentes s'y sont cassé les dents. Prendre le dernier
    changement de plan dans une large fenêtre tombait en pleine météo, parce
    qu'un présentateur enchaîne les sujets sans reprendre son souffle. Chercher
    des tournures de lancement dans le texte (« reportage de », « sur place »)
    marchait sur un JT et sur un seul : c'est du vocabulaire de rédaction figé
    dans le code.

    Ce qui délimite vraiment le lancement, c'est le tour de parole. Un
    générique, un reportage précédent ou un silence le coupent naturellement.
    """
    floor = block_start - max_lookback
    before = [(s, e) for s, e, lab in all_turns
              if lab != her_label and e <= block_start + 0.01
              and e - s >= min_turn]
    if not before:
        # Personne ne parle avant elle : on démarre sur le plan où elle
        # apparaît, sans remonter dans ce qui précède.
        # Le dernier plan avant sa parole EST la première image de son sujet
        # (fin du générique, ouverture du reportage) : on démarre dessus.
        prev = [c for c in sorted(cuts or []) if floor <= c <= block_start]
        return max(prev) if prev else max(floor, block_start - 0.5)

    anchor = max(before, key=lambda t: t[1])[0]
    if anchor < floor:
        # Tour trop long pour être pris en entier (il couvre les sujets d'avant).
        # On coupe au plafond, mais jamais en plein milieu d'une phrase.
        anchor = _sentence_at_or_after(transcript, floor) or floor
        if anchor >= block_start:
            anchor = floor
    return _lead_in(anchor, transcript)


def last_word(all_turns, her_label, block_end, min_turn=0.5):
    """Fin de sa dernière VRAIE prise de parole.

    La diarisation lui attribue parfois un fragment de quelques centièmes de
    seconde une fois le plateau revenu. Pris pour sa dernière parole, ce
    fragment fait déborder la coupe sur le plateau."""
    ends = [e for s, e, lab in all_turns
            if lab == her_label and e <= block_end + 0.01 and e - s >= min_turn]
    return max(ends) if ends else block_end


def reportage_end(all_turns, her_label, block_end, cuts, precut_window=5.0,
                  forward=15.0):
    """Fin = dernière image du reportage.

    Le retour plateau est un changement de plan, pas une prise de parole : le
    présentateur réapparaît une bonne seconde avant de parler. Viser « juste
    avant qu'il ne parle » montrait donc le plateau à tous les coups. On vise
    le plan qui ramène le plateau, et on s'arrête dessus."""
    end_of_speech = last_word(all_turns, her_label, block_end)
    ahead = [c for c in sorted(cuts or [])
             if end_of_speech - 0.05 <= c <= end_of_speech + forward]
    if ahead:
        return ahead[0]
    return max(end_of_speech, block_end)


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
                         max_lookback, launch_gap, precut_window,
                         transcript=transcript, names=names)
    if mode == "reportage":
        end = reportage_end(all_turns, her_label, block_end, cuts, precut_window)
    else:  # chronique
        end = chronique_end(all_turns, her_label, block_end, cuts,
                            launch_gap, precut_window)
    # Marge de sécurité : s'arrêter un poil avant le plan de retour plateau,
    # mais jamais avant sa dernière parole. On se cale sur la dernière parole
    # RÉELLE : la borne du bloc inclut parfois un fragment parasite déjà sur
    # le plateau, et s'en servir de plancher ramenait le plateau dans la coupe.
    end = max(last_word(all_turns, her_label, block_end), end - end_trim)
    validated = None
    if transcript and names:
        validated = name_in_text(_text_between(transcript, start, block_start),
                                 names)
    return start, end, validated
