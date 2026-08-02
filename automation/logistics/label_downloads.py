from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile


def build_label_archive(documents, downloader, max_workers=4):
    unique = []
    seen_urls = set()
    for document in documents:
        url = str(document.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        unique.append({**document, "url": url})
        seen_urls.add(url)
    downloaded, errors = {}, []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(downloader, document["url"]): document
            for document in unique
        }
        for future in as_completed(futures):
            document = futures[future]
            try:
                downloaded[document["url"]] = future.result()
            except Exception as error:
                errors.append({
                    "url": document["url"],
                    "error": str(error),
                })
    archive = BytesIO()
    used_names = set()
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for index, document in enumerate(unique, start=1):
            content = downloaded.get(document["url"])
            if content is None:
                continue
            name = _archive_name(document, content, index)
            name = _unique_name(name, used_names)
            output.writestr(name, content)
            used_names.add(name)
    return archive.getvalue(), errors, len(downloaded)


def _archive_name(document, content, index):
    parts = [
        document.get("platform"),
        document.get("order_id"),
        document.get("tracking_number"),
    ]
    stem = "_".join(_safe_name(part) for part in parts if str(part or "").strip())
    if not stem:
        stem = f"label_{index}"
    return f"{stem}{_document_extension(document.get('url'), content)}"


def _safe_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned.strip("._")[:100]


def _document_extension(url, content):
    suffix = Path(urlparse(str(url or "")).path).suffix.lower()
    if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
        return suffix
    if bytes(content).startswith(b"%PDF"):
        return ".pdf"
    if bytes(content).startswith(b"\x89PNG"):
        return ".png"
    if bytes(content).startswith(b"\xff\xd8"):
        return ".jpg"
    return ".bin"


def _unique_name(name, used_names):
    if name not in used_names:
        return name
    path = Path(name)
    counter = 2
    while True:
        candidate = f"{path.stem}_{counter}{path.suffix}"
        if candidate not in used_names:
            return candidate
        counter += 1
