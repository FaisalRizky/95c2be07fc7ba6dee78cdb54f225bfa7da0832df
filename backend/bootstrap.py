from config.db import get_db
from services.project_service import sync_projects_to_elasticsearch


def run_bootstrap():
    """
    Orchestrates the entire application startup sequence.
    - Validates Database health.
    - Synchronizes Elasticsearch data.
    """
    db = get_db()

    # 1. Database Health Check
    if not db.check_health():
        raise RuntimeError("[bootstrap] Cannot connect to database or execute test query.")
    print("[bootstrap] Database OK")

    # 2. Search Synchronization
    try:
        count = sync_projects_to_elasticsearch(db)
        if count > 0:
            print(f"[bootstrap] Elasticsearch synchronization complete: {count} projects.")
    except Exception as e:
        # We catch but don't re-raise search errors so the API can still
        # start in fallback mode if ES is down.
        print(f"[bootstrap] Search synchronization failed: {e}")
