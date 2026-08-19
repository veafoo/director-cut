import torch


def _to_turns(output):
    """Normalise la sortie pyannote (toutes versions) en une liste triée de
    (debut, fin, label). pyannote 3.x renvoie une Annotation avec .itertracks ;
    pyannote 4.x / community-1 renvoie un objet avec .speaker_diarization."""
    ann = output
    if not hasattr(ann, "itertracks") and hasattr(output, "speaker_diarization"):
        ann = output.speaker_diarization

    turns = []
    if hasattr(ann, "itertracks"):
        for turn, _, label in ann.itertracks(yield_label=True):
            turns.append((float(turn.start), float(turn.end), str(label)))
    else:
        # nouvelle API : itère en (turn, speaker)
        for item in ann:
            turn, label = item[0], item[-1]
            turns.append((float(turn.start), float(turn.end), str(label)))
    return sorted(turns)


_pipeline = None


def unload():
    """Libère le pipeline de diarisation.

    Il a fini son travail dès que la diarisation est faite. Le garder en
    mémoire pendant que la transcription charge le sien fait culminer la RAM au
    pire moment : sur une machine juste, le système tue le processus sans un
    mot d'explication. Sur un lot, il sera rechargé pour la vidéo suivante —
    quelques secondes, contre un run qui n'arrive pas au bout."""
    global _pipeline
    if _pipeline is None:
        return
    _pipeline = None
    from .embeddings import free_memory
    free_memory()


def load_pipeline(hf_token):
    """Charge le pipeline de diarisation, une fois pour toutes.

    Le chargement prend plusieurs secondes et le modèle ne dépend pas de la
    vidéo : sur un lot, le recharger à chaque fois est du temps perdu."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    from pyannote.audio import Pipeline

    if not hf_token:
        raise RuntimeError(
            "Token Hugging Face manquant (fichier .hf_token ou variable HF_TOKEN)."
        )

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", token=hf_token)
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=hf_token)

    if pipeline is None:
        raise RuntimeError(
            "Pipeline vide : vérifie l'acceptation des conditions des modèles "
            "pyannote (speaker-diarization-3.1, segmentation-3.0, "
            "speaker-diarization-community-1) et la validité du token."
        )

    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        pipeline.to(torch.device("mps"))

    _pipeline = pipeline
    return pipeline


def diarize(wav_path, hf_token, num_speakers=None, show_progress=True):
    """Renvoie une liste de tours de parole : [(debut, fin, label), ...]."""
    pipeline = load_pipeline(hf_token)

    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers

    output = None
    if show_progress:
        try:
            from pyannote.audio.pipelines.utils.hook import ProgressHook
            with ProgressHook() as hook:
                output = pipeline(wav_path, hook=hook, **kwargs)
        except Exception:
            output = None
    if output is None:
        output = pipeline(wav_path, **kwargs)

    return _to_turns(output)
