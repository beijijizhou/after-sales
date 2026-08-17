import streamlit as st

from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from db.access import create_employee, load_production_departments
from utils.auth import has_permission, require_page_access

require_page_access("register")

st.title("注册新员工")
can_register = has_permission("can_register")
if not can_register:
    st.info("当前账号只能查看，不能新增或修改员工资料")

name = st.text_input("人名")

job_title = st.selectbox(
    "岗位",
    [
        "质检",
        "烫印",
    ]
)

production_departments = st.multiselect(
    "生产部门（可多选）",
    load_production_departments(supabase),
    default=["DTF"],
)

is_qa = job_title == "质检"

username = st.text_input(
    "登陆账号的用户名",
    disabled=not is_qa
)

password = st.text_input(
    "密码",
    type="password",
    disabled=not is_qa
)

if st.button("注册", disabled=not can_register):

    try:
        create_employee(
            supabase,
            name,
            job_title,
            production_departments,
            username=username if is_qa else "",
            password=password if is_qa else "",
        )
    except Exception as error:
        st.error(f"用户创建失败：{error}")
    else:
        st.success("用户创建成功")
