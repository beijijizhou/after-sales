import streamlit as st

from db.supabase_client import supabase

st.title("注册新员工")

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

if st.button("注册"):

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
