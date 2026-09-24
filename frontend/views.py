import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st
import websocket

API = os.getenv('API_URL', 'http://localhost:8000')


def api_call(method, path, authenticated=True, **kwargs):
    headers = {'Authorization': f"Bearer {st.session_state.get('token', '')}"} if authenticated else {}
    try:
        result = requests.request(method, API + path, headers=headers, timeout=15, **kwargs)
        if not result.ok:
            try:
                detail = result.json().get('detail', result.text)
            except ValueError:
                detail = result.text
            st.error(f'{result.status_code}: {detail}')
            return None
        return result if 'export' in path else (result.json() if result.content else {})
    except requests.RequestException as exc:
        st.error(f'API unavailable: {exc}')
        return None


def realtime_page():
    st.header('即時監控')
    st.caption('每秒推送一筆模擬感測資料；圖表顯示最近 60 筆。')
    if 'live' not in st.session_state:
        st.session_state.live = []

    @st.fragment(run_every='1s')
    def monitor():
        if 'socket' not in st.session_state:
            try:
                ws_url = API.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/live?token=' + st.session_state.token
                st.session_state.socket = websocket.create_connection(ws_url, timeout=1)
            except Exception as exc:
                st.warning(f'WebSocket reconnecting: {exc}')
                return
        try:
            st.session_state.socket.settimeout(0.8)
            event = json.loads(st.session_state.socket.recv())
            st.session_state.live = (st.session_state.live + [event])[-60:]
        except Exception:
            st.session_state.pop('socket', None)
        frame = pd.DataFrame(st.session_state.live)
        if frame.empty:
            st.info('等待第一筆即時資料…')
            return
        frame['timestamp'] = pd.to_datetime(frame['timestamp'])
        latest = frame.iloc[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric('最新數值', latest['value'])
        c2.metric('資料分類', latest['category'])
        c3.metric('連線狀態', 'Live')
        if latest['alert']:
            st.error('異常警告：數值超過閾值')
        st.line_chart(frame.set_index('timestamp')['value'], x_label='時間', y_label='數值')
        st.bar_chart(frame.groupby('category')['value'].mean())

    monitor()


def records_page():
    st.header('資料紀錄')
    category = st.text_input('篩選分類')
    page_number = st.number_input('頁碼', min_value=1, value=1)
    records = api_call('GET', '/api/records', params={'page': page_number, 'size': 50, 'category': category or None})
    if records is not None:
        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
    if st.session_state.role not in ('admin', 'user'):
        st.info('Viewer 可查詢資料；新增、匯入與修改需要 User 或 Admin 權限。')
        return
    with st.form('create'):
        title = st.text_input('標題')
        value = st.number_input('數值')
        new_category = st.text_input('分類')
        if st.form_submit_button('新增'):
            if api_call('POST', '/api/records', json={'title': title, 'value': value, 'category': new_category}):
                st.rerun()
    upload = st.file_uploader('匯入 CSV 或 JSON', type=['csv', 'json'])
    if upload and st.button('匯入'):
        if api_call('POST', '/api/records/import', files={'file': (upload.name, upload.getvalue())}):
            st.rerun()
    with st.expander('修改或刪除紀錄'):
        target = st.number_input('紀錄 ID', min_value=1)
        updated_value = st.number_input('新數值', key='updated_value')
        left, right = st.columns(2)
        if left.button('更新數值'):
            if api_call('PATCH', f'/api/records/{target}', json={'value': updated_value}):
                st.rerun()
        if right.button('刪除'):
            if api_call('DELETE', f'/api/records/{target}') is not None:
                st.rerun()


def analytics_page():
    st.header('統計分析')
    days = st.slider('最近幾天', 1, 365, 7)
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    stats = api_call('GET', '/api/analytics/summary', params={'start': start})
    if stats:
        a, b, c, d = st.columns(4)
        a.metric('筆數', stats['count'])
        b.metric('平均', round(stats['average'] or 0, 2))
        c.metric('最大', stats['max'] if stats['max'] is not None else '-')
        d.metric('最小', stats['min'] if stats['min'] is not None else '-')
        if stats['categories']:
            st.bar_chart(pd.DataFrame(stats['categories']).set_index('category')['count'])
    records = api_call('GET', '/api/records', params={'start': start, 'size': 500, 'order': 'asc'})
    if records:
        history = pd.DataFrame(records)
        history['timestamp'] = pd.to_datetime(history['timestamp'])
        st.line_chart(history.set_index('timestamp')['value'], x_label='時間', y_label='數值')
    if st.button('準備 Excel 下載'):
        response = api_call('GET', '/api/analytics/export', params={'start': start})
        if response:
            st.session_state.export_bytes = response.content
            st.session_state.export_days = days
    if st.session_state.get('export_days') == days and st.session_state.get('export_bytes'):
        st.download_button('下載 records.xlsx', st.session_state.export_bytes, 'records.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def admin_page():
    st.header('系統管理')
    health = api_call('GET', '/api/admin/health')
    if health:
        a, b, c = st.columns(3)
        a.metric('資料庫', health['database'])
        b.metric('歷史資料筆數', health['record_count'])
        c.metric('WebSocket 連線', health['websocket_clients'])
    users = api_call('GET', '/api/admin/users')
    if users is not None:
        st.subheader('使用者與權限')
        st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
    with st.form('role'):
        target = st.number_input('使用者 ID', min_value=1)
        new_role = st.selectbox('角色', ['viewer', 'user', 'admin'])
        if st.form_submit_button('更新角色'):
            if api_call('PATCH', f'/api/admin/users/{target}/role', json={'role': new_role}):
                st.rerun()
    logs = api_call('GET', '/api/admin/logs')
    if logs is not None:
        st.subheader('系統稽核日誌')
        st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
