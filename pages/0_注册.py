import streamlit as st

from db.supabase_client import supabase
from utils.auth import has_permission, require_page_access

require_page_access("register")

st.title("注册新员工")
can_register = has_permission("can_register")
if not can_register:
    st.info("当前账号只能查看，不能新增或修改员工资料")

name = st.text_input("人名")

department = st.selectbox(
    "部门",
    [
        "质检",
        "烫印",
    ]
)

is_qa = department == "质检"

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

    data = {
        "name": name,
        "department": department,
        "employee_id": name + "_id",
    }

    if is_qa:
        data["user_name"] = username
        data["password"] = password
    if department == "烫印":
        data["password"] = "N/A"

    (
        supabase
        .table("users")
        .insert(data)
        .execute()
    )

    st.success("用户创建成功")
