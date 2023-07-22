import datetime
import os
import logging
import requests
from typing import List, Optional
from pydantic import BaseModel, HttpUrl

LOGGER = logging.getLogger()

BASE_URL = "https://www.googleapis.com/customsearch/v1"


class Image(BaseModel):
    height: int
    width: int
    contextLink: HttpUrl
    thumbnailLink: HttpUrl
    thumbnailHeight: int
    thumbnailWidth: int


class ImageItem(BaseModel):
    kind: str
    title: str
    link: HttpUrl
    image: Optional[Image]


class ImageSearchResponse(BaseModel):
    items: List[ImageItem]


class CachedImageSearch(BaseModel):
    ts: datetime.datetime = datetime.datetime.now()
    response: ImageSearchResponse


class ImageSearchCache:
    CACHE_AGE_DAYS = 10

    def __init__(self):
        self.cache: dict[str, CachedImageSearch] = {}

    def add_to_cache(self, key, cached_image_search: CachedImageSearch):
        self.cache[key] = cached_image_search

    def get_from_cache(self, key):
        """Returns the item from teh cache, assuming it's not older than the max cache age."""
        result = self.cache.get(key)
        if not result:
            return

        current_ts = datetime.datetime.now()
        if result.ts < current_ts - datetime.timedelta(days=self.CACHE_AGE_DAYS):
            return

        return result


class Search:
    """Simple wrapper around the google 'custom search' API.
    Supports caching based on search queries so we only use it a minimal amount."""

    def __init__(self):
        self.search_engine_id = os.getenv("GOOGLE_SEARCH_ID")
        self.search_engine_key = os.getenv("GOOGLE_SEARCH_KEY")

        self.params = {"cx": self.search_engine_id, "key": self.search_engine_key}

        self.image_search_cache = ImageSearchCache()

    def get_first_image(self, search_str: str):
        cached_result = self.image_search_cache.get_from_cache(search_str)
        if cached_result:
            return cached_result.response.items[0]

        extra_params = {
            "q": search_str,
            "searchType": "image"
        }
        r = requests.get(
            url=BASE_URL,
            params={**self.params, **extra_params}
        ).json()
        search_response = ImageSearchResponse.model_validate(r)
        self.image_search_cache.add_to_cache(search_str, CachedImageSearch(response=search_response))
        return search_response.items[0]
