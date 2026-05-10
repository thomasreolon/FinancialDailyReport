from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from src.api.youtube import download_yt_transcript, list_channel_videos
from src.scrapers.base import ScrapingNode

from src.utils.global_logger import log, log_error

CHANNEL_URL = "https://www.youtube.com/{channel}"


class YTResult(BaseModel):
    url: str
    transcript: str


class YTScraper(ScrapingNode):
    def __init__(self, hours: int = 24, channel: str = "@fxevolutionvideo"):
        self.hours = hours
        self.channel = channel

    def scrape(self) -> YTResult | None:
        videos = list_channel_videos(CHANNEL_URL.format(channel=self.channel), max_videos=5)
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
        return YTResult(url=latest["url"], transcript=transcript)
