def scene_cuts(video_path, threshold=27.0):
    """Renvoie la liste des instants (s) de changement de plan."""
    try:
        from scenedetect import ContentDetector, detect
        scenes = detect(video_path, ContentDetector(threshold=threshold))
    except Exception:
        return []
    cuts = []
    for start, end in scenes:
        cuts.append(start.get_seconds())
        cuts.append(end.get_seconds())
    return sorted(set(cuts))
