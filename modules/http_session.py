# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def make_http_session() -> requests.Session:
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST"]),
        raise_on_status=False
    )

    adapter = HTTPAdapter(
        max_retries=retries,
        pool_connections=10,
        pool_maxsize=10
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

session = make_http_session()