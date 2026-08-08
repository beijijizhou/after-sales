import pypdfium2 as pdfium
import streamlit as st


def render_pdf_pages(pdf_bytes, scale=1.6):
    """Render PDF bytes into detached page images for a stable Streamlit preview."""
    document = pdfium.PdfDocument(pdf_bytes)
    images = []
    try:
        for page_index in range(len(document)):
            page = document[page_index]
            bitmap = page.render(scale=scale)
            try:
                images.append(bitmap.to_pil().copy())
            finally:
                bitmap.close()
                page.close()
    finally:
        document.close()
    return images


def render_invoice_pdf_preview(pdf_bytes):
    """Show every invoice page without relying on a third-party web component."""
    try:
        pages = render_pdf_pages(pdf_bytes)
    except Exception:
        st.error("Invoice 预览加载失败；仍可下载预览 PDF 后核对。")
        return
    if not pages:
        st.warning("Invoice 预览为空，请重新生成。")
        return
    with st.container(border=True):
        for page_number, page_image in enumerate(pages, start=1):
            if len(pages) > 1:
                st.caption(f"第 {page_number} / {len(pages)} 页")
            st.image(page_image, width="stretch")
