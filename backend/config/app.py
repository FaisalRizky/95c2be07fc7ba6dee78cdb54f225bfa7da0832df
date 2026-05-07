import os


class AppConfig:
    """
    Centralized configuration registry for the entire application,
    similar to Laravel's config behavior. All environment variables
    and default values should be defined here.
    """

    # App Settings
    ENV = os.getenv("APP_ENV", "development")
    DEBUG = os.getenv("APP_DEBUG", "true").lower() == "true"

    # Database Settings
    DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()
    SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "")  # default resolved at runtime relative to repo root
    POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/glenigan")

    # Cache Settings
    CACHE_ENGINE = os.getenv("CACHE_ENGINE", "memory").lower()
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

    # Elasticsearch Settings
    ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
    ES_INDEX = os.getenv("ES_INDEX", "glenigan_projects")

# Global config instance to be imported across the app
config = AppConfig()
