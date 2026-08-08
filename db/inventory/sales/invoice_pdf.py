from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def build_sales_invoice_pdf(invoice, company, customer, lines):
    buffer = BytesIO()
    font_name = _invoice_font()
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "InvoiceNormal", parent=styles["Normal"], fontName=font_name,
        fontSize=9, leading=12,
    )
    title = ParagraphStyle(
        "InvoiceTitle", parent=normal, fontSize=24, leading=28,
        textColor=colors.HexColor("#17365D"), alignment=TA_RIGHT,
    )
    right = ParagraphStyle(
        "InvoiceRight", parent=normal, alignment=TA_RIGHT,
    )
    document = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=0.55 * inch,
        leftMargin=0.55 * inch, topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=f"Invoice {invoice['invoice_number']}",
        author=str(company.get("company_name") or ""),
    )
    company_lines = [
        f"<b>{_safe(company.get('company_name'))}</b>",
        _safe(company.get("address_line1")),
        _city_line(company),
        _safe(company.get("email")),
        _safe(company.get("phone")),
    ]
    header = Table([
        [Paragraph("<br/>".join(filter(None, company_lines)), normal),
         Paragraph(_invoice_title(invoice.get("status")), title)],
        ["", Paragraph(
            f"Invoice #: <b>{_safe(invoice.get('invoice_number'))}</b><br/>"
            f"Date: {_safe(invoice.get('invoice_date'))}", right
        )],
    ], colWidths=[4.2 * inch, 2.7 * inch])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    customer_lines = [
        f"<b>{_safe(customer.get('display_name'))}</b>",
        _safe(customer.get("contact_name")),
        _safe(customer.get("address_line1")),
        _city_line(customer),
        _safe(customer.get("email")),
        _safe(customer.get("phone")),
    ]
    story = [
        header,
        Spacer(1, 0.22 * inch),
        Paragraph("BILL TO", ParagraphStyle(
            "BillTo", parent=normal, fontSize=8,
            textColor=colors.HexColor("#64748B"),
        )),
        Paragraph("<br/>".join(filter(None, customer_lines)), normal),
        Spacer(1, 0.25 * inch),
    ]

    table_rows = [["Description", "Qty", "Unit Price", "Amount"]]
    for row in lines.to_dict("records"):
        description = " / ".join(filter(None, (
            str(row.get(key) or "").strip() for key in [
                "品牌", "材质", "颜色", "尺码",
            ]
        )))
        table_rows.append([
            description,
            f"{int(row['数量']):,}",
            f"${float(row['单价']):,.2f}",
            f"${float(row['金额']):,.2f}",
        ])
    subtotal = sum(float(value) for value in lines["金额"])
    table_rows.append(["", "", "Subtotal", f"${subtotal:,.2f}"])
    detail = Table(
        table_rows,
        colWidths=[4.45 * inch, 0.65 * inch, 0.9 * inch, 0.9 * inch],
        repeatRows=1,
    )
    detail.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -2), 0.35, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEABOVE", (2, -1), (-1, -1), 1, colors.HexColor("#17365D")),
        ("FONTNAME", (2, -1), (-1, -1), font_name),
    ]))
    story.extend([detail, Spacer(1, 0.2 * inch)])
    if invoice.get("note"):
        story.append(Paragraph(f"Note: {_safe(invoice['note'])}", normal))
    document.build(story)
    return buffer.getvalue()


def _invoice_font():
    name = "STSong-Light"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def _invoice_title(status):
    if status == "void":
        return "INVOICE - VOID"
    if status == "draft":
        return "INVOICE - DRAFT"
    return "INVOICE"


def _safe(value):
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;"
    )


def _city_line(values):
    city = str(values.get("city") or "").strip()
    state = str(values.get("state") or "").strip()
    postal = str(values.get("postal_code") or "").strip()
    return " ".join(filter(None, [f"{city}," if city and state else city, state, postal]))
