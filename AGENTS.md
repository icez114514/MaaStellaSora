# Fork Development Rules

## Repository Boundaries

- 本儲存庫是 MaaStellaSora 的個人 Fork，必須明確區分個人 Fork 與上游專案。
- `origin` 應指向個人 Fork。
- `upstream` 應指向 `https://github.com/MaaStellaSora/MaaStellaSora.git`。
- 未經使用者明確指示，不得 Push、建立或送出 Pull Request。
- 未經使用者明確指示，不得建立 Issue、Discussion、Release 或 Tag。
- 未經使用者明確指示，不得自動 Commit、Merge、Rebase 或同步 upstream。
- 功能開發必須使用獨立功能分支，不直接修改預設分支。
- 不得修改或覆蓋不屬於目前任務的現有變更。
- 保留原專案的 License、版權及來源標示。
- 不得假設個人 Fork 中的功能需要貢獻回上游。

## Task Scope

- 只閱讀和修改目前任務直接需要的檔案。
- 實作前先確認工作樹狀態、目前分支及相關既有變更。
- 跳過 `.git`、`.venv`、`node_modules`、`dist`、日誌、產出檔案及快取目錄，除非目前任務確實需要。
- 不得為了理解單一功能而掃描整個專案。
- 不得覆蓋、還原或整理使用者未要求處理的變更。
- 除非使用者明確要求，不得貼出完整原始碼。

## MaaFramework Scope

- 實作任何功能前，先閱讀與該功能直接相關的 MaaStellaSora Pipeline、資源、agent 模組與設定。
- 優先依照 MaaFramework 公開 API、官方文件及 MaaStellaSora 現有慣例實作。
- 新增 Pipeline 功能時，先檢查相關任務定義、圖片資源、OCR、ROI、流程參數與錯誤處理。
- 新增自訂辨識或操作時，只閱讀相關 agent 模組及對應 MaaFramework API。
- 只有遇到未文件化行為、底層錯誤，或確認必須修改框架時，才局部閱讀 MaaFramework 對應模組。
- 不得為了理解單一功能而掃描或通讀整個 MaaFramework。
- 除非使用者明確要求，不得直接修改 MaaFramework 上游、已安裝套件、二進位檔或快取內容。
- 若判斷問題可能來自 MaaFramework，先提供證據、受影響模組及最小閱讀範圍，再繼續調查。
- 若確實需要修改 MaaFramework，必須將其視為獨立變更，先取得使用者明確同意。

## Feature Development Workflow

開始實作功能前：

1. 明確描述功能目標與成功條件。
2. 找出與功能直接相關的 Pipeline、資源、agent 模組及設定。
3. 說明預計修改範圍。
4. 建立獨立功能分支。
5. 優先沿用現有專案結構與模式。
6. 加入與變更風險相符的測試或驗證方式。
7. 完成後回報修改內容、驗證結果與已知限制。
8. 未經使用者明確指示，不得 Push、Commit 或建立 Pull Request。

## Command Output Safety

- 任何可能產生未知或大量輸出的指令都必須限制輸出。
- 預設只檢查前 6000 bytes。
- 如果需要完整輸出，先寫入暫存檔，再讀取與問題直接相關的範圍。
- 不要將依賴清單、完整日誌或整個目錄樹直接輸出到對話。
