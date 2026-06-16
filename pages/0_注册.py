import streamlit as st

from db.supabase_client import supabase

st.title("注册新质检人员")

name = st.text_input("人名")
username = st.text_input("登陆账号的用户名")
password = st.text_input("密码", type="password")

if st.button("Register"):
    (
        supabase
        .table("users")
        .insert({
            "name": name,
            "user_name": username,
            "password": password,
            "employee_id": name + password +"_id",
        })
        .execute()
    )

    st.success("User created")