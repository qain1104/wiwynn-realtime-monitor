# 即時資料分析與監控系統

FastAPI + MariaDB + Streamlit 的產線資料監控示範。每秒產生模擬數值，透過 WebSocket 推送；每 10 筆（可設定）使用 ORM 批次寫入資料庫。前端以 Streamlit 多頁導覽呈現即時折線圖、分類柱狀圖、閾值告警、歷史查詢與系統管理。

## 系統架構

```mermaid
flowchart TD
    UI[Streamlit 多頁介面] -->|REST + JWT| API[FastAPI]
    UI -->|WebSocket + JWT| API
    API -->|SQLAlchemy async ORM / asyncmy| DB[(MariaDB 11.7)]
    GEN[每秒模擬器] -->|推送與批次寫入| API
    API -->|Alembic migration| DB
```

## 技術棧

Python 3.12、FastAPI、Pydantic、SQLAlchemy 2 async ORM、asyncmy、Alembic、MariaDB 11.7、Streamlit、pandas、openpyxl、Docker Compose。密碼以 Argon2 雜湊，API 使用 HS256 JWT，有效期八小時。

## 專案結構

```text
backend/app/             FastAPI、JWT、ORM、WebSocket、分析與管理 API
backend/alembic/         MariaDB 資料庫遷移
backend/tests/           API 整合測試（SQLite 隔離資料庫）
frontend/app.py          登入、註冊與多頁導覽入口
frontend/views.py        監控、資料、分析、管理頁面
sample_data/records.csv  可直接匯入的測試資料
docs/architecture.md     系統架構與資料流程
compose.yaml             MariaDB、API、UI 容器編排
```

## Docker 啟動

```bash
cp .env.example .env
# 編輯 .env：設定強密碼和至少 32 字元的 JWT_SECRET
docker compose up --build -d
docker compose logs -f api
```

前端 http://localhost:8501；Swagger API 文件 http://localhost:8000/docs；OpenAPI JSON http://localhost:8000/openapi.json。資料存於 `db_data` named volume。首次啟動執行 Alembic migration，並依環境變數建立管理員。停止：`docker compose down`；保留資料請勿加 `-v`。

## 本機運行

需要 Python 3.12 和 MariaDB 11.7。先複製 `.env.example` 到 `.env`，設定 `DATABASE_URL=mysql+asyncmy://USER:PASSWORD@localhost:3306/monitor`，建立資料庫，再執行：

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
# 另一個終端，在專案根目錄
cd frontend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
API_URL=http://localhost:8000 streamlit run app.py
```

## 測試帳號與權限

管理員帳號從 `.env` 的 `ADMIN_EMAIL` / `ADMIN_PASSWORD` 取得（範例：`admin@example.com` / `change-this-admin-password`，部署前務必修改）。新註冊帳號為 `viewer`；管理員可在系統管理頁將其升為 `user`。Viewer 可查詢；User 可新增、匯入並修改或刪除自己建立的資料；Admin 可以管理所有資料、角色、稽核日誌及資料庫狀態。模擬資料沒有建立者，只有 Admin 可修改或刪除。

## API

| 方法 | 路徑 | 權限 | 說明 |
| --- | --- | --- | --- |
| POST | `/api/auth/register`, `/api/auth/login` | 公開 | 註冊、登入 |
| GET | `/api/auth/me` | 登入 | 個人資料 |
| GET, POST | `/api/records` | 登入、User+ | 清單與新增 |
| GET, PATCH, DELETE | `/api/records/{id}` | 登入、擁有者/Admin | 單筆 CRUD |
| POST | `/api/records/import` | User+ | CSV/JSON 匯入 |
| GET | `/api/analytics/summary`, `/api/analytics/export` | 登入 | 統計與 Excel |
| GET | `/api/admin/users`, `/api/admin/logs`, `/api/admin/health` | Admin | 管理查詢 |
| PATCH | `/api/admin/users/{id}/role` | Admin | 更改角色 |
| WS | `/ws/live?token=JWT` | 登入 | 每秒推送 |

`GET /api/records` 支援 `page`、`size`、`category`、`start`、`end`、`sort=timestamp|value|id`、`order=asc|desc`。時間使用 ISO 8601。匯入欄位是 `title,value,category,timestamp`，範例見 [`sample_data/records.csv`](sample_data/records.csv)。匯入大小最多 2 MB、5000 筆；Excel 最多輸出近期 10000 筆。告警閾值由 `ALERT_THRESHOLD` 設定。

完整架構與資料流說明見 [`docs/architecture.md`](docs/architecture.md)。

## 快速驗證

登入取得 Token，再使用 Bearer header 呼叫 API：

```bash
curl -s http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@example.com","password":"change-this-admin-password"}'
```

進入 Swagger 頁按 Authorize 輸入 Token，可直接試 CRUD、匯入和查詢。資料生成器使用單一 API 程序；多 worker 或多副本部署時需改用獨立 worker 與跨程序訊息佇列，避免重複生成和 WebSocket 訊息分散。日誌查詢顯示資料異動和角色變更的稽核紀錄；容器執行日誌請查看 `docker compose logs api`。

## 自動化測試

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

測試涵蓋健康檢查、註冊登入、Viewer 權限阻擋、Admin CRUD 與統計分析。GitHub Actions 會在每次 push 及 pull request 自動執行測試、語法檢查與 Compose 設定驗證。
