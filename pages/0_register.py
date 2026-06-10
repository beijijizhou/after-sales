import streamlit as st

from db.supabase_client import supabase

st.title("Register")

name = st.text_input("Name")
username = st.text_input("Username")
password = st.text_input("Password", type="password")

if st.button("Register"):
    (
        supabase
        .table("users")
        .insert({
            "name": name,
            "username": username,
            "password": password
        })
        .execute()
    )

    st.success("User created")