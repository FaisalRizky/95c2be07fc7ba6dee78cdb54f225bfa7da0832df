import time
from typing import Optional, Protocol

try:
    from elasticsearch import Elasticsearch, exceptions
except ImportError:
    Elasticsearch = None
    exceptions = None

from config.app import config
from config.elasticsearch import advanced_search, es_client


class SearchEngine(Protocol):
    def search_projects(
        self,
        area: Optional[str],
        keyword: Optional[str],
        page: int,
        per_page: int,
        company: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
    ) -> tuple[Optional[list[str]], int]:
        """
        Returns a list of project_ids matching the search criteria.
        Returns None if this engine cannot handle the request (fallback trigger).
        """
        ...


class SqliteSearchEngine:
    """Fallback search engine that simply returns None to let the main SQL query handle everything."""

    def search_projects(
        self,
        area: Optional[str],
        keyword: Optional[str],
        page: int,
        per_page: int,
        company: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
    ) -> tuple[Optional[list[str]], int]:
        return None, 0


class ElasticSearchEngine:
    def __init__(self, host: str, index_name: str):
        self.client = es_client
        self.index_name = index_name

    def is_active(self) -> bool:
        if self.client is None:
            return False
        try:
            return self.client.ping()
        except Exception:
            return False

    def search_projects(
        self, area, keyword, page, per_page, company=None, sort_by=None, sort_order="asc"
    ) -> tuple[Optional[list[str]], int]:
        return advanced_search(area, keyword, page, per_page, company=company, sort_by=sort_by, sort_order=sort_order)


class SearchProvider:
    _engine: Optional[SearchEngine] = None
    _last_check_time: float = 0
    _check_interval: int = 30  # Re-check ES liveness at most once every 30 seconds

    @classmethod
    def get_engine(cls) -> SearchEngine:
        current_time = time.time()

        # Within the interval: return whatever engine was last confirmed good.
        # This applies whether ES is up OR down — avoids 500ms ping overhead on
        # every request when ES has gone down after startup.
        if cls._engine is not None and current_time - cls._last_check_time < cls._check_interval:
            return cls._engine

        # Outside the interval: re-check liveness and update the cached engine.
        cls._last_check_time = current_time
        es_engine = ElasticSearchEngine(config.ES_HOST, config.ES_INDEX)

        if es_engine.is_active():
            if not isinstance(cls._engine, ElasticSearchEngine):
                print("[search] Elasticsearch detected! Switching to ES engine.")
            cls._engine = es_engine
            return cls._engine

        # ES is not reachable — fall back (or stay) on SQLite.
        if isinstance(cls._engine, ElasticSearchEngine):
            print("[search] Elasticsearch went down. Falling back to SQLite.")
        cls._engine = SqliteSearchEngine()
        return cls._engine
