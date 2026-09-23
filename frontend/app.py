import streamlit as st

from views import admin_page, api_call, analytics_page, records_page, realtime_page

st.set_page_config(page_title='Real-time Monitor', page_icon='📡', layout='wide')
st.title('即時資料分析與監控系統')

if 'token' not in st.session_state:
    login_tab, register_tab = st.tabs(['登入', '註冊'])
    with login_tab:
        with st.form('login'):
            email = st.text_input('Email')
            password = st.text_input('Password', type='password')
            if st.form_submit_button('登入', use_container_width=True):
                response = api_call('POST', '/api/auth/login', authenticated=False, json={'email': email, 'password': password})
                if response:
                    st.session_state.token = response['access_token']
                    st.session_state.role = response['role']
                    st.rerun()
    with register_tab:
        with st.form('register'):
            new_email = st.text_input('Email', key='register_email')
            new_password = st.text_input('Password（至少 8 字元）', type='password', key='register_password')
            if st.form_submit_button('建立 Viewer 帳號', use_container_width=True):
                if api_call('POST', '/api/auth/register', authenticated=False, json={'email': new_email, 'password': new_password}):
                    st.success('註冊完成，請返回登入。')
    st.stop()

if st.sidebar.button('登出', use_container_width=True):
    socket = st.session_state.get('socket')
    if socket:
        socket.close()
    st.session_state.clear()
    st.rerun()

pages = [
    st.Page(realtime_page, title='即時監控', icon='📈', default=True),
    st.Page(records_page, title='資料紀錄', icon='🗂️'),
    st.Page(analytics_page, title='統計分析', icon='📊'),
]
if st.session_state.role == 'admin':
    pages.append(st.Page(admin_page, title='系統管理', icon='⚙️'))

st.navigation(pages).run()
