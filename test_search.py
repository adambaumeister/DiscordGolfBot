import datetime

import pytest
import os


@pytest.fixture()
def search_fixture():
    from dotenv import load_dotenv
    load_dotenv()

    if not os.getenv("GOOGLE_SEARCH_KEY"):
        pytest.skip("This is an integration test and will not work without creds - skipping.")

    from search import Search
    return Search()


def test_search_first_image(search_fixture):
    image = search_fixture.get_first_image("The Open")
    assert image.link


def test_cache():
    from search import CachedImageSearch, ImageSearchCache, ImageSearchResponse

    cache = ImageSearchCache()
    dummy_response = CachedImageSearch(
        response=ImageSearchResponse(
            items=[]
        )
    )

    old_dummy_response = CachedImageSearch(
        response=ImageSearchResponse(
            items=[]
        ),
        ts=datetime.datetime.now() - datetime.timedelta(days=20)
    )

    cache.add_to_cache("test search query", dummy_response)
    # Should work, and return a cache item
    assert cache.get_from_cache("test search query")

    # Should fail - item too old and needs to be refreshed.
    cache.add_to_cache("test query 2", old_dummy_response)
    assert not cache.get_from_cache("test query 2")
