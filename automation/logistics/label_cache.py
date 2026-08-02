from threading import RLock

from cachetools import TTLCache

from automation.logistics.label_ocr import (
    download_label_content,
    extract_label_content_fields,
)


LABEL_CACHE_TTL_SECONDS = 24 * 60 * 60
_CONTENT_CACHE = TTLCache(maxsize=2000, ttl=LABEL_CACHE_TTL_SECONDS)
_FIELDS_CACHE = TTLCache(maxsize=2000, ttl=LABEL_CACHE_TTL_SECONDS)
_CACHE_LOCK = RLock()


def cached_label_content(label_url):
    with _CACHE_LOCK:
        content = _CONTENT_CACHE.get(label_url)
    if content is not None:
        return content
    content = download_label_content(label_url)
    with _CACHE_LOCK:
        _CONTENT_CACHE[label_url] = content
    return content


def cached_label_fields(label_url, content):
    with _CACHE_LOCK:
        fields = _FIELDS_CACHE.get(label_url)
    if fields is not None:
        return fields
    fields = extract_label_content_fields(content)
    with _CACHE_LOCK:
        _FIELDS_CACHE[label_url] = fields
    return fields


def clear_label_cache():
    with _CACHE_LOCK:
        _CONTENT_CACHE.clear()
        _FIELDS_CACHE.clear()
