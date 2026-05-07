import time

from config.app import config


def wait_for_elasticsearch(es_client, max_retries=2, delay=1):
    """
    Technical utility to wait for the Elasticsearch service to be reachable.
    Does not know anything about projects or services.
    """
    if not es_client:
        return False

    print(f"[es-utils] Waiting for Elasticsearch at {config.ES_HOST}...")
    for i in range(max_retries):
        try:
            if es_client.ping():
                print("[es-utils] Elasticsearch is reachable!")
                return True
        except Exception:
            pass
        print(f"[es-utils] ... ({i+1}/{max_retries})")
        time.sleep(delay)

    return False
