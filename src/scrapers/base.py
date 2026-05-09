from abc import ABC, abstractmethod


class ScrapingNode(ABC):
    @abstractmethod
    def scrape(self) -> dict | None:
        ...
