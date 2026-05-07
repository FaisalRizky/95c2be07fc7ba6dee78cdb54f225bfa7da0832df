from typing import Optional

try:
    from elasticsearch import Elasticsearch, helpers
except ImportError:
    Elasticsearch = None
    helpers = None

from config.app import config

# ============================================================================
# 🔍 ELASTICSEARCH CLIENT & CONFIGURATION
# ============================================================================
# INTERVIEW CONCEPT: Elasticsearch Client Connection
# - Handles connection pooling, retries, and timeouts.
# ============================================================================
es_client = Elasticsearch(
    config.ES_HOST,
    request_timeout=0.5,    # Ultra-fast detection for local networks
    max_retries=0,
    retry_on_timeout=False
) if Elasticsearch else None
INDEX_NAME = config.ES_INDEX

# ============================================================================
# 🏗️ INDEX SETUP WITH CUSTOM ANALYZERS
# ============================================================================
def setup_elasticsearch():
    if not es_client or not es_client.ping():
        print("[es-config] Skipping setup: Elasticsearch not reachable.")
        return

    try:
        if es_client.indices.exists(index=INDEX_NAME):
            # For this interview demo, we'll recreate to ensure latest analyzers are applied
            es_client.indices.delete(index=INDEX_NAME)

        print(f"[es-config] Creating index {INDEX_NAME} with custom analyzers...")

        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "filter": {
                    "construction_synonyms": {
                        "type": "synonym",
                        "synonyms": [
                            "renovation, refurbishment, remodel",
                            "highway, motorway, freeway, expressway",
                            "residential, housing, dwelling",
                            "commercial, office, business"
                        ]
                    },
                    "autocomplete_filter": {
                        "type": "edge_ngram",
                        "min_gram": 2,
                        "max_gram": 15
                    }
                },
                "analyzer": {
                    "construction_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "construction_synonyms"]
                    },
                    "autocomplete_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "autocomplete_filter"]
                    }
                }
            }
        }

        mappings = {
            "properties": {
                "project_id": {"type": "keyword"},
                "project_name": {
                    "type": "text",
                    "analyzer": "construction_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword"},
                        "autocomplete": {
                            "type": "text",
                            "analyzer": "autocomplete_analyzer",
                            "search_analyzer": "standard"
                        }
                    }
                },
                "description": {
                    "type": "text",
                    "analyzer": "construction_analyzer"
                },
                "area": {"type": "keyword"},
                "company": {"type": "keyword"},
                "project_value": {"type": "integer"},
                "project_start": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss||strict_date_optional_time||epoch_millis",
                }
            }
        }

        es_client.indices.create(index=INDEX_NAME, settings=settings, mappings=mappings)
        print(f"[es-config] Index {INDEX_NAME} configured successfully.")

    except Exception as e:
        print(f"[es-config] Setup error: {e}")

# ============================================================================
# 🔍 ADVANCED SEARCH — Bool Query (Faceted / Filtered)
# ============================================================================
def advanced_search(
    area: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    company: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc"
):
    if not es_client:
        return None, 0

    try:
        must = []
        filters = []

        if keyword:
            must.append({
                "multi_match": {
                    "query": keyword,
                    "fields": ["project_name^3", "project_name.autocomplete", "description"],
                    "fuzziness": "AUTO",
                    "operator": "or"
                }
            })
        else:
            must.append({"match_all": {}})

        if area:
            filters.append({"term": {"area": area}})

        if company:
            filters.append({"term": {"company": company}})

        sort_mapping = {
            "project_id": "project_id",
            "project_name": "project_name.keyword",
            "project_value": "project_value",
            "project_start": "project_start",
            "project_end": "project_end",
            "company": "company",
            "area": "area",
        }

        sort_logic = []
        if sort_by in sort_mapping:
            sort_logic.append({sort_mapping[sort_by]: {"order": sort_order}})

        # Always add a tie-breaker for deterministic pagination
        sort_logic.append({"project_id": {"order": "asc"}})

        res = es_client.search(
            index=INDEX_NAME,
            query={"bool": {"must": must, "filter": filters}},
            from_=(page - 1) * per_page,
            size=per_page,
            _source=False,
            sort=sort_logic
        )

        ids = [hit["_id"] for hit in res["hits"]["hits"]]
        total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) else res["hits"]["total"]

        return ids, total
    except Exception as e:
        print(f"[es-search] Error: {e}")
        return None, 0

# ============================================================================
# 📊 AGGREGATIONS — Analytics (Interview Pattern)
# ============================================================================
def get_search_stats():
    if not es_client:
        return {}
    try:
        res = es_client.search(
            index=INDEX_NAME,
            size=0,
            aggs={
                "by_area": {"terms": {"field": "area", "size": 10}},
                "avg_value": {"avg": {"field": "project_value"}}
            }
        )
        return res.get("aggregations", {})
    except Exception:
        return {}

# ============================================================================
# 📝 BULK INDEXING — Universal Infrastructure Logic
# ============================================================================
def bulk_index_data(data_generator, id_field: str = "id"):
    """
    Universal logic to transform dictionary data into ES actions.
    - id_field: The key in the dictionary to use as the ES document _id.
    """
    if not es_client:
        return 0

    def generate_actions():
        for item in data_generator:
            yield {
                "_index": INDEX_NAME,
                "_id": item.get(id_field),
                "_source": item
            }

    success_count, _ = helpers.bulk(es_client, generate_actions())
    return success_count
