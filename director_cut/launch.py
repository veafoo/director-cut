import difflib
import unicodedata


# Tournures par lesquelles un présentateur lance un sujet. Volontairement
# courtes et sans accent : la comparaison se fait sur du texte aplati.
# Rester serré : une tournure trop vague accroche une phrase de météo ou de
# titre et fait démarrer le passage bien avant le lancement.
LAUNCH_CUES = (
    "reportage", "vous allez le voir", "regardez", "on y va", "c est parti",
    "sur place", "explications", "on vous emmene", "le sujet de",
)

# Un changement de plan n'est retenu pour caler le début que s'il colle à la
# phrase de lancement. Au-delà, il tombe dans la phrase précédente et on
# repart en plein milieu d'un mot.
SNAP = 1.0


def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


def _flat(s):
    """Minuscules, sans accent, ponctuation en espaces — mots préservés."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " "
                            for c in s.lower()).split())


def is_launch(text, names=()):
    """Cette phrase lance-t-elle un sujet ?

    Le nom de la personne est le signal le plus sûr (« le reportage de … »),
    d'où l'intérêt de names.txt. À défaut, on s'appuie sur les tournures."""
    if names and name_in_text(text, names):
        return True
    flat = _flat(text)
    return any(cue in flat for cue in LAUNCH_CUES)


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


def launch_sentence(transcript, block_start, max_lookback=40.0, names=(),
                    launch_gap=10.0):
    """Début de la phrase de lancement, ou None s'il n'y en a pas.

    Le repère est la phrase, pas le changement de plan : sur un plateau la
    caméra change au milieu des phrases, et s'y caler fait démarrer en plein mot.

    Un lancement doit **coller** au reportage : sa phrase se termine dans les
    `launch_gap` secondes qui précèdent la première parole. Sans cette
    condition, le « Reportage à suivre » du sommaire, prononcé trente secondes
    et une météo plus tôt, est pris pour le lancement.

    Parmi les phrases qui restent, on garde la PLUS ANCIENNE qui lance : un
    lancement tient parfois en deux phrases, autant les avoir toutes."""
    if not transcript:
        return None
    floor = block_start - max_lookback
    for start, end, text in sorted(transcript):
        if end <= floor or start >= block_start:
            continue
        if end > block_start + 0.01:      # phrase déjà à cheval sur sa parole
            continue
        if block_start - end > launch_gap:
            continue
        if is_launch(text, names):
            return start
    return None


def launch_start(all_turns, her_label, block_start, cuts,
                 max_lookback=40.0, launch_gap=10.0, precut_window=5.0,
                 transcript=None, names=()):
    """Début du passage.

    Deux cas, et c'est la distinction qui compte :
    - le présentateur lance le sujet -> on démarre au début de cette phrase ;
    - il enchaîne sans lancer (le sujet suit la météo ou un titre) -> on démarre
      sur le plan où elle apparaît, sans remonter dans le sujet d'avant.

    L'ancienne version prenait le dernier changement de plan dans une fenêtre
    large. Sur un présentateur qui parle sans interruption depuis 50 s, ça
    tombait n'importe où : en pleine météo, ou au milieu d'une phrase."""
    cuts = sorted(cuts or [])
    anchor = launch_sentence(transcript, block_start, max_lookback, names,
                             launch_gap)
    if anchor is not None:
        # caler sur un changement de plan seulement s'il colle à la phrase
        near = [c for c in cuts if anchor - SNAP <= c <= anchor + 0.2]
        return max(near) if near else anchor

    # Pas de lancement : on prend le dernier plan avant elle, ce qui donne une
    # petite amorce sans mordre sur le sujet précédent.
    limit = block_start - 0.5
    floor = block_start - max_lookback
    prev = [c for c in cuts if floor <= c <= limit]
    return max(prev) if prev else max(floor, limit)


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
