from pathlib import Path

import streamlit as st

from automation.sync.google_sheets import (
    GoogleSheetsClient,
    resolve_service_account_info,
)
from db.inventory.planning.uv_consumption import (
    UV_DAILY_ORDERS_SPREADSHEET_ID,
    UV_GOOGLE_DRIVE_FOLDER_ID,
)


def google_sheets_client():
    credential_file = (
        Path(__file__).resolve().parents[3]
        / ".streamlit"
        / "google-service-account.json"
    )
    info, source = resolve_service_account_info(
        secrets=st.secrets,
        credential_path=credential_file,
    )
    st.session_state["google_sheets_credential_source"] = source
    return GoogleSheetsClient(info)


@st.cache_data(ttl=300, show_spinner=False)
def load_uv_folder_spreadsheets():
    return google_sheets_client().list_spreadsheets_in_folder(
        UV_GOOGLE_DRIVE_FOLDER_ID
    )


def render_uv_spreadsheet_selector(key="uv_google_spreadsheet_id"):
    fallback = {
        "id": UV_DAILY_ORDERS_SPREADSHEET_ID,
        "name": "2026 UV每日订单统计",
        "webViewLink": (
            "https://docs.google.com/spreadsheets/d/"
            f"{UV_DAILY_ORDERS_SPREADSHEET_ID}/edit"
        ),
    }
    try:
        files = load_uv_folder_spreadsheets()
    except Exception as error:
        st.warning(f"暂时无法读取UV数据文件夹，继续使用默认表格：{error}")
        return fallback
    if not files:
        st.warning("UV数据文件夹中没有Google表格，继续使用默认表格。")
        return fallback
    by_id = {item["id"]: item for item in files}
    if fallback["id"] not in by_id:
        files.append(fallback)
        by_id[fallback["id"]] = fallback
    options = [item["id"] for item in files]
    selected = st.selectbox(
        "Google 数据表",
        options,
        index=options.index(UV_DAILY_ORDERS_SPREADSHEET_ID),
        format_func=lambda file_id: by_id[file_id].get("name", file_id),
        key=key,
        help="新表格放进UV部生产文件夹后，会自动出现在这里。",
    )
    return by_id[selected]
