import os
import subprocess


def _fmt(t):
    return f"{t:.3f}"


def cut_segments(video_path, segments, out_dir, prefix="passage",
                 concat=True, reencode=False, on_progress=None):
    """Découpe chaque segment, et concatène si demandé.

    reencode=False : coupe rapide par copie de flux (cale sur keyframe, donc
    bornes au plan près). reencode=True : coupe à l'image près (plus lent)."""
    os.makedirs(out_dir, exist_ok=True)
    clips = []
    for i, (s, e) in enumerate(segments, 1):
        out = os.path.join(out_dir, f"{prefix}_{i:02d}.mp4")
        if reencode:
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-ss", _fmt(s), "-to", _fmt(e),
                "-c:v", "libx264", "-c:a", "aac", out,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-ss", _fmt(s), "-i", video_path,
                "-t", _fmt(e - s),
                "-c", "copy", out,
            ]
        subprocess.run(cmd, check=True, capture_output=True)
        clips.append(out)
        if on_progress:
            on_progress(i, len(segments))

    if concat and len(clips) > 1:
        listfile = os.path.join(out_dir, "concat.txt")
        with open(listfile, "w") as f:
            for c in clips:
                f.write(f"file '{os.path.abspath(c)}'\n")
        final = os.path.join(out_dir, f"{prefix}_complet.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", listfile, "-c", "copy", final],
            check=True, capture_output=True,
        )
        clips.append(final)
    return clips


def cut_one(video_path, start, end, out_path, reencode=True):
    """Découpe UN passage vers out_path. reencode=True -> coupe à l'image près."""
    if reencode:
        cmd = ["ffmpeg", "-y", "-i", video_path,
               "-ss", _fmt(start), "-to", _fmt(end),
               "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", out_path]
    else:
        cmd = ["ffmpeg", "-y", "-ss", _fmt(start), "-i", video_path,
               "-t", _fmt(end - start), "-c", "copy", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
