import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def list_channel_videos(channel_url: str, max_videos: int = 5) -> list[dict]:
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", str(max_videos),
        "--print", "%(.{id,title,upload_date,webpage_url})j",
        channel_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        videos = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            entry = json.loads(line)
            upload_date = entry.get("upload_date")  # "YYYYMMDD"
            published_at = None
            if upload_date:
                published_at = datetime(
                    int(upload_date[:4]),
                    int(upload_date[4:6]),
                    int(upload_date[6:8]),
                    tzinfo=timezone.utc,
                )
            videos.append({
                "video_id": entry.get("id"),
                "url": entry.get("webpage_url"),
                "title": entry.get("title"),
                "published_at": published_at,
            })
        return videos
    except Exception:
        return []


def download_yt_transcript(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        segments = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(s["text"] for s in segments)
    except Exception:
        pass

    # fallback: yt-dlp subtitle download
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-format", "vtt",
            "--skip-download",
            "--output", str(Path(tmpdir) / "%(id)s.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if result.returncode != 0 or not vtt_files:
            raise RuntimeError(f"Failed to download transcript for video {video_id}")
        return _parse_vtt(vtt_files[0].read_text())


def _parse_vtt(vtt: str) -> str:
    lines = []
    for line in vtt.splitlines():
        # skip header, cue timestamps, and empty lines
        if not line or line.startswith("WEBVTT") or "-->" in line or line.startswith("NOTE"):
            continue
        # strip inline tags like <00:00:00.000> and <c>
        import re
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean:
            lines.append(clean)
    # deduplicate consecutive identical lines (auto-captions repeat)
    deduped = [lines[i] for i in range(len(lines)) if i == 0 or lines[i] != lines[i - 1]]
    return " ".join(deduped)
