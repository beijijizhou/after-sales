import hashlib
import re
import threading

import requests


COMBINED_WEIGHT_PATTERN = re.compile(
    r"(?P<lb>\d+(?:\.\d+)?)\s*l[b8]\s*"
    r"(?P<oz>\d+(?:\.\d+)?)\s*o[z2]", re.IGNORECASE
)
OZ_WEIGHT_PATTERN = re.compile(
    r"(?P<oz>\d+(?:\.\d+)?)\s*o[z2]\b", re.IGNORECASE
)
LB_WEIGHT_PATTERN = re.compile(
    r"(?P<lb>\d+(?:\.\d+)?)\s*l[b8]\b", re.IGNORECASE
)
CITY_STATE_ZIP_PATTERN = re.compile(
    r"^(?P<city>.+?)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$"
)


def extract_label_fields(label_url, timeout=30):
    return extract_label_content_fields(
        download_label_content(label_url, timeout=timeout)
    )


def download_label_content(label_url, timeout=30):
    response = requests.get(label_url, timeout=timeout)
    response.raise_for_status()
    return response.content


def extract_label_content_fields(content):
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
        image = document[0].render(scale=2.5).to_pil().convert("RGB")
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
        weight_oz = _weight_ounces(line["text"])
        if weight_oz is not None:
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
        "extracted_weight_lb": (
            round(weight_oz / 16, 4) if weight_oz is not None else None
        ),
        "extracted_weight_display": _format_weight(weight_oz),
        "ocr_confidence": round(confidence, 4),
    }


def _weight_ounces(text):
    text = str(text or "")
    combined = COMBINED_WEIGHT_PATTERN.search(text)
    if combined:
        return round(
            float(combined.group("lb")) * 16 + float(combined.group("oz")), 4
        )
    ounces = OZ_WEIGHT_PATTERN.search(text)
    if ounces:
        return round(float(ounces.group("oz")), 4)
    pounds = LB_WEIGHT_PATTERN.search(text)
    if pounds:
        return round(float(pounds.group("lb")) * 16, 4)
    return None


def _format_weight(weight_oz):
    if weight_oz is None:
        return ""
    pounds = int(weight_oz // 16)
    ounces = round(weight_oz - pounds * 16, 2)
    ounce_text = f"{ounces:g}"
    if pounds:
        return f"{pounds} lb {ounce_text} oz"
    return f"{ounce_text} oz"


def _previous_address_line(lines, address_index):
    ignored = ("CREATED ", "RDC ", "USPS", "MAILED FROM")
    for line in reversed(lines[:address_index]):
        text = line["text"].strip().upper()
        if (
            text and not text.startswith(ignored)
            and _weight_ounces(text) is None
        ):
            return line["text"].strip()
    return ""


def _ocr_engine():
    engine = getattr(_OCR_THREAD_LOCAL, "engine", None)
    if engine is None:
        from rapidocr import RapidOCR

        engine = RapidOCR(params={
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Rec.rec_batch_num": 4,
            "Cls.cls_batch_num": 4,
            "Global.use_cls": False,
            "Global.log_level": "warning",
        })
        _OCR_THREAD_LOCAL.engine = engine
    return engine


_OCR_THREAD_LOCAL = threading.local()
