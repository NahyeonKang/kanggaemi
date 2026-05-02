from abc import ABC, abstractmethod
from app.schemas.market_data import MarketDataRequest, MarketDataResponse


class BaseBrokerScraper(ABC):
    @abstractmethod
    def fetch_market_data(self, req: MarketDataRequest) -> MarketDataResponse:
        raise NotImplementedError