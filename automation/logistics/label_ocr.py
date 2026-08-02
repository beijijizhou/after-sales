import hashlib
import re
from functools import lru_cache

import requests


WEIGHT_PATTERN = re.compile(
    r"(?P<lb>\d+)\s*l[b8]\s*(?P<oz>\d+)\s*o[z2]", re.IGNORECASE
)
CITY_STATE_ZIP_PATTERN = re.compile(
    r"^(?P<city>.+?)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$"
)


def extract_label_fields(label_url, timeout=30):
    response = requests.get(label_url, timeout=timeout)
    response.raise_for_status()
    content = response.content
    lines = ocr_pdf_lines(content)
    parsed = parse_usps_label_lines(lines)
    return {
        **parsed,
        "label_content_hash": hashlib.sha256(content).hexdigest(),
    }


def ocr_pdf_lines(content):
    import numpy as np
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(content)
    try:
        if len(document) < 1:
            raise ValueError("面单PDF没有页面")
        image = document[0].render(scale=3).to_pil().convert("RGB")
    finally:
        document.close()
    result = _ocr_engine()(np.asarray(image))
    if not result or not result.txts:
        raise ValueError("OCR没有识别到面单文字")
    lines = []
    for box, text, score in zip(result.boxes, result.txts, result.scores):
        lines.append({
            "text": str(text).strip(),
            "score": float(score),
            "x": float(np.min(box[:, 0])),
            "y": float(np.min(box[:, 1])),
        })
    return sorted(lines, key=lambda item: (item["y"], item["x"]))


def parse_usps_label_lines(lines):
    weight_oz = None
    for line in lines:
        match = WEIGHT_PATTERN.search(line["text"])
        if match:
            weight_oz = int(match.group("lb")) * 16 + int(match.group("oz"))
            break

    address_index = None
    address_match = None
    for index, line in enumerate(lines):
        match = CITY_STATE_ZIP_PATTERN.match(line["text"].upper())
        if match:
            address_index, address_match = index, match
            break

    if address_index is None:
        raise ValueError("OCR未识别到寄件城市、州和邮编")
    street = _previous_address_line(lines, address_index)
    if not street:
        raise ValueError("OCR未识别到寄件街道")
    confidence = min(
        lines[address_index]["score"],
        next(line["score"] for line in reversed(lines[:address_index])
             if line["text"] == street),
    )
    return {
        "extracted_street": street,
        "extracted_city": address_match.group("city"),
        "extracted_state": address_match.group("state"),
        "extracted_postal_code": address_match.group("zip"),
        "extracted_weight_oz": weight_oz,
        "ocr_confidence": round(confidence, 4),
    }


def _previous_address_line(lines, address_index):
    ignored = ("CREATED ", "RDC ", "USPS", "MAILED FROM")
    for line in reversed(lines[:address_index]):
        text = line["text"].strip().upper()
        if text and not text.startswith(ignored) and not WEIGHT_PATTERN.search(text):
            return line["text"].strip()
    return ""


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr import RapidOCR

    return RapidOCR()
