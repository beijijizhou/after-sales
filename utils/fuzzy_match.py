from utils.exact_match import search as exact_search
from utils.barcode_patterns import build_fuzzy_search_preview


def build_search_preview(barcodes):
    return build_fuzzy_search_preview(barcodes)


def search(supabase, barcodes):
    return exact_search(supabase, barcodes, fuzzy=True)
