from datetime import datetime, timedelta, timezone

from src.api.youtube import download_yt_transcript, list_channel_videos
from src.scrapers.base import ScrapingNode

CHANNEL_URL = "https://www.youtube.com/@fxevolutionvideo"


class YTFxEvolutionScraper(ScrapingNode):
    def __init__(self, hours: int = 24):
        self.hours = hours

    def scrape(self) -> dict | None:
        videos = list_channel_videos(CHANNEL_URL, max_videos=5)
        if not videos:
            return None

        latest = videos[0]
        published_at = latest.get("published_at")
        if published_at is None:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.hours)
        if published_at < cutoff:
            return None

        transcript = download_yt_transcript(latest["video_id"])
        return {"url": latest["url"], "transcript": transcript}
