import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Tests marked `network` download from the Hub; they run only with EXTRACT_INDEX_NETWORK=1."""
    if os.environ.get("EXTRACT_INDEX_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="needs EXTRACT_INDEX_NETWORK=1")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
