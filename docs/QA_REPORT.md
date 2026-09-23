# 本機驗收紀錄

驗收日期：2026-09-23  
環境：macOS ARM64、Docker Desktop、MariaDB 11.7、FastAPI、Streamlit

## 驗收結果

| 項目 | 結果 | 驗證內容 |
| --- | --- | --- |
| 容器啟動 | 通過 | MariaDB healthy；API 與 UI 可開啟 |
| 健康檢查與 Swagger | 通過 | `/api/health`、`/docs`、`/openapi.json` 可用 |
| 註冊與登入 | 通過 | 新帳號預設為 Viewer；JWT 登入回傳 200 |
| 即時推送 | 通過 | WebSocket 每秒更新，連線顯示 Live |
| 圖表與告警 | 通過 | 折線圖、分類柱狀圖與超過閾值告警正常 |
| 歷史資料 | 通過 | 模擬資料批次寫入並可於資料頁查詢 |
| Viewer 權限 | 通過 | 可查詢與分析；新增資料正確回傳 403 |
| Admin 邊界 | 通過 | Viewer 存取 `/api/admin/users` 正確回傳 403 |
| 統計分析 | 通過 | 筆數、平均、最大、最小、分類與趨勢正常 |
| Excel 匯出 | 通過 | 可準備並下載 `records.xlsx` |
| 自動化測試 | 通過 | GitHub Actions 執行 API 測試、語法與 Compose 驗證 |

## 本輪發現與修正

1. ARM64 缺少 `asyncmy 0.2.10` wheel：升級至具 ARM64 wheel 的版本，移除 GCC toolchain。
2. Alembic 容器無法載入 `app`：runtime 明確設定 `PYTHONPATH=/code`。
3. 即時圖完整 ISO 時間造成標籤擁擠：轉成 datetime，交由圖表自動格式化時間軸。
4. 統計頁每次載入都建立 Excel：改為使用者點擊後才產生。
5. Swagger 缺少結構：加入 API 版本、說明、功能分組和常見權限回應。
6. 缺少 Token 時的狀態碼不明確：統一回傳 401 與 `WWW-Authenticate: Bearer`。

## 驗收限制

- 本輪以 Viewer 執行本機黑箱測試；Admin 密碼由部署者自訂，因此 Admin 成功操作由自動化測試覆蓋。
- 本機驗收建立 `qa.local.20260923@example.com` Viewer 帳號。系統目前沒有刪除使用者功能，可由 Admin 將其保留為展示帳號。
- 單程序 WebSocket 與記憶體批次緩衝符合測驗範圍；水平擴展時應改用訊息佇列與跨程序廣播。
