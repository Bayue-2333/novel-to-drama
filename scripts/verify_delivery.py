"""Verify media, captions and hash-bound review records; not a semantic video reviewer."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

REVIEW_KINDS = ("visual", "audio", "sync", "subtitles", "continuity")


def sha256(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def bundle_digest(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def seconds(value):
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[,.](\d{2,3})", value.strip())
    if not match:
        raise ValueError(f"Bad subtitle timestamp: {value}")
    hours, minutes, secs, fraction = match.groups()
    if int(minutes) >= 60 or int(secs) >= 60:
        raise ValueError("Subtitle timestamp minutes/seconds must be below 60")
    return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(fraction) / (10 ** len(fraction))


def plain(text):
    return re.sub(r"\s+", "", re.sub(r"\{[^}]*\}|<[^>]*>", "", text.replace(r"\N", " ").replace(r"\n", " ")))


def read_srt(path):
    content = Path(path).read_text(encoding="utf-8-sig").strip().replace("\r\n", "\n")
    cues = []
    for index, block in enumerate(re.split(r"\n\s*\n", content), 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(index):
            raise ValueError("SRT needs sequential IDs, timing and nonempty text")
        times = re.fullmatch(r"(\d+:\d{2}:\d{2},\d{3}) --> (\d+:\d{2}:\d{2},\d{3})", lines[1].strip())
        if not times:
            raise ValueError("Invalid SRT timing line")
        cues.append((seconds(times[1]), seconds(times[2]), plain("\n".join(lines[2:]))))
    return cues


def read_ass(path):
    cues, fields, in_events = [], None, False
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("["):
            in_events = line.lower() == "[events]"
        elif in_events and line.lower().startswith("format:"):
            fields = [part.strip().lower() for part in line.split(":", 1)[1].split(",")]
        elif in_events and line.lower().startswith("dialogue:"):
            if not fields or fields[-1] != "text":
                raise ValueError("ASS needs Events Format with Text last")
            parts = line.split(":", 1)[1].lstrip().split(",", len(fields) - 1)
            if len(parts) != len(fields):
                raise ValueError("Invalid ASS Dialogue")
            data = dict(zip(fields, parts))
            cues.append((seconds(data["start"]), seconds(data["end"]), plain(data["text"])))
    return cues


def validate_cues(cues, duration):
    if not cues:
        raise ValueError("No subtitle cues")
    previous_end = 0.0
    for start, end, text in cues:
        if start < previous_end - 0.001 or start < 0 or end <= start or end > duration + 0.05 or not text:
            raise ValueError("Subtitle overlap, empty text, invalid order or out-of-range timing")
        previous_end = end


def covers(ranges, duration):
    intervals = []
    for item in ranges:
        if not isinstance(item, list) or len(item) != 2:
            return False
        start, end = item
        if any(type(n) not in (int, float) or not math.isfinite(n) for n in item):
            return False
        if start < 0 or end <= start or end > duration + 0.05:
            return False
        intervals.append((start, end))
    edge = 0.0
    for start, end in sorted(intervals):
        if start > edge + 0.05:
            return False
        edge = max(edge, end)
    return bool(intervals) and edge >= duration - 0.05


def check_reviews(reviews, bundle, duration, root):
    errors = []
    for kind in REVIEW_KINDS:
        review = reviews.get(kind, {})
        if review.get("status") != "pass" or review.get("bundle_sha256") != bundle:
            errors.append(f"{kind}: missing, partial, failed or stale review")
        if not covers(review.get("ranges", []), duration):
            errors.append(f"{kind}: review does not cover the whole final timeline")
        if not all(review.get(k) for k in ("method", "reviewer", "reviewed_at")):
            errors.append(f"{kind}: missing method/reviewer/date")
        evidence = review.get("evidence", [])
        if not evidence or any(not (root / p).is_file() or not (root / p).stat().st_size for p in evidence):
            errors.append(f"{kind}: missing evidence files")
    return errors


def run_command(args, timeout, cwd=None):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, cwd=cwd)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace")[-1800:])
    return result.stdout


def probe(path, ffprobe):
    return json.loads(run_command([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path], 60))


def media_check(path, expected, ffprobe, ffmpeg, decode_timeout):
    info = probe(path, ffprobe)
    videos = [s for s in info["streams"] if s["codec_type"] == "video"]
    audios = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not videos or not audios:
        raise ValueError("Expected video and audio tracks")
    video, audio = videos[0], audios[0]
    duration = float(video.get("duration", info["format"]["duration"]))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid media duration")
    av_duration = float(audio.get("duration", info["format"]["duration"]))
    av_start_gap = abs(float(video.get("start_time", 0)) - float(audio.get("start_time", 0)))
    # Container-track checks are not perceptual lip-sync validation.
    tolerance = expected.get("track_tolerance_seconds", 0.15)
    if abs(duration - av_duration) > tolerance or av_start_gap > tolerance:
        raise ValueError("Audio/video track duration or start mismatch; inspect timestamps")
    for key in ("width", "height"):
        if expected.get(key) is not None and video[key] != expected[key]:
            raise ValueError(f"Unexpected {key}: {video[key]}")
    numerator, denominator = video["avg_frame_rate"].split("/")
    fps = float(numerator) / float(denominator)
    if expected.get("fps") is not None and abs(fps - expected["fps"]) > 0.01:
        raise ValueError(f"Unexpected fps: {fps}")
    if expected.get("audio_sample_rate") is not None and int(audio["sample_rate"]) != expected["audio_sample_rate"]:
        raise ValueError("Unexpected audio sample rate")
    run_command([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", path,
                 "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], decode_timeout)
    return {"duration": duration, "fps": fps, "width": video["width"], "height": video["height"],
            "audio_sample_rate": audio.get("sample_rate"), "full_decode": "pass"}


def verify(manifest, root, ffprobe, ffmpeg, decode_timeout=1800):
    errors, rows = [], []
    episodes = manifest.get("episodes", [])
    required = manifest.get("required_episode_ids", [])
    ids = [episode["id"] for episode in episodes]
    if not required or len(set(required)) != len(required) or len(set(ids)) != len(ids) or set(ids) != set(required):
        errors.append("Missing, duplicate or unexpected episodes relative to required_episode_ids")
    for episode in episodes:
        row = {"id": episode["id"], "errors": []}
        try:
            paths = {key: (root / episode[key]).resolve() for key in ("video", "master", "srt", "ass")}
            if any(not p.is_file() or not p.stat().st_size for p in paths.values()):
                raise ValueError("Missing or empty delivery asset")
            if paths["video"] == paths["master"]:
                raise ValueError("Burned-subtitle video and clean master must be separate files")
            hashes = {key: sha256(path) for key, path in paths.items()}
            row["hashes"] = hashes
            row["bundle_sha256"] = bundle_digest(hashes)
            expected = episode.get("expected", {})
            for key in ("video", "master"):
                row[key] = media_check(paths[key], expected, ffprobe, ffmpeg, decode_timeout)
            duration = row["video"]["duration"]
            if abs(duration - row["master"]["duration"]) > 0.05:
                raise ValueError("Master and subtitled version durations differ")
            srt, ass = read_srt(paths["srt"]), read_ass(paths["ass"])
            validate_cues(srt, duration)
            validate_cues(ass, duration)
            if len(srt) != len(ass) or any(abs(a[0] - b[0]) > 0.03 or abs(a[1] - b[1]) > 0.03 or a[2] != b[2] for a, b in zip(srt, ass)):
                raise ValueError("SRT/ASS text or timings differ")
            row["subtitle_cues"] = len(srt)
            row["errors"].extend(check_reviews(episode.get("reviews", {}), row["bundle_sha256"], duration, root))
            for issue in episode.get("issues", []):
                if issue.get("severity") not in ("blocker", "major", "minor") or issue.get("status") not in ("open", "resolved"):
                    row["errors"].append("Issue has invalid severity/status")
                if issue.get("severity") in ("blocker", "major") and (issue.get("status") != "resolved" or issue.get("verified_on_bundle_sha256") != row["bundle_sha256"]):
                    row["errors"].append(f"Unresolved or stale blocking issue: {issue.get('id')}")
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError, subprocess.TimeoutExpired) as exc:
            row["errors"].append(str(exc))
        errors.extend(f"{episode['id']}: {error}" for error in row["errors"])
        rows.append(row)
    return {"status": "pass" if not errors else "needs_review", "errors": errors, "episodes": rows,
            "scope": "Media/caption integrity plus hash-bound declared review evidence; semantic truth is not automatically verified"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--decode-timeout", type=float, default=1800)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    result = verify(manifest, args.manifest.resolve().parent, args.ffprobe, args.ffmpeg, args.decode_timeout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "errors": result["errors"], "report": str(args.out.resolve())}, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
