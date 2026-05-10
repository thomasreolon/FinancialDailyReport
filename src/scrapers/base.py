from abc import ABC, abstractmethod

from pydantic import BaseModel


class ScrapingNode(ABC):
    @abstractmethod
    def scrape(self) -> BaseModel | None:
        ...
