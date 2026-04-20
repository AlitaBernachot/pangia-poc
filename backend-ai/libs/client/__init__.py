# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""DB client package — one module per backend data store."""

from libs.client.chroma_client import (
    add_documents,
    get_chroma_client,
    similarity_search,
)
from libs.client.graphdb_client import (
    ensure_repository,
    run_sparql_construct,
    run_sparql_select,
)
from libs.client.neo4j_client import (
    close_driver,
    get_driver,
    run_query,
    run_readonly_query,
)
from libs.client.postgis_client import (
    close_pool,
    get_pool,
    run_spatial_query,
    run_write_query,
)
from libs.client.redis_client import (
    close_redis,
    get_redis,
    load_session,
    save_session,
)

__all__ = [
    # chroma
    "get_chroma_client",
    "similarity_search",
    "add_documents",
    # graphdb
    "ensure_repository",
    "run_sparql_select",
    "run_sparql_construct",
    # neo4j
    "get_driver",
    "close_driver",
    "run_query",
    "run_readonly_query",
    # postgis
    "get_pool",
    "close_pool",
    "run_spatial_query",
    "run_write_query",
    # redis
    "get_redis",
    "close_redis",
    "load_session",
    "save_session",
]
