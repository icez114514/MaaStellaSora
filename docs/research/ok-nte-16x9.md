# ok-nte 自動調整遊戲為 16:9 的實作

## 結論

ok-nte 並未修改遊戲設定檔，也沒有持續攔截或「鎖死」遊戲解析度。它把支援比例與候選尺寸交給 `ok-script`；連接遊戲視窗後，框架檢查實際擷取畫面的比例與最低尺寸。若不合規且「Auto Resize Game Window」啟用，框架以 Win32 API 改變遊戲視窗的**外框尺寸**並置中，再更新擷取尺寸。

因此這是「啟動／連接時自動校正視窗」，不是持續監控後禁止使用者再次拉動視窗。若最大候選尺寸加上標題列後超出桌面工作區，程式會依清單順序改選可容納的較小 16:9 尺寸；實際結果仍取決於 Windows 視窗邊框、標題列與 DPI 尺寸。

## ok-nte 的設定與呼叫順序

1. [`src/config.py`](https://github.com/BnanZ0/ok-nte/blob/fb1d502026acd66b4dabfba3b85bd6250c672305/src/config.py#L128-L135) 宣告：
   - `ratio: "16:9"`
   - `min_size: (1920, 1080)`
   - `resize_to: [(3840, 2160), (2560, 1440), (1920, 1080)]`
2. [`main.py`](https://github.com/BnanZ0/ok-nte/blob/fb1d502026acd66b4dabfba3b85bd6250c672305/main.py#L1-L10) 建立 `ok.OK(config)` 並呼叫 `start()`，把上述設定交給框架。
3. [`src/tasks/LauncherTask.py`](https://github.com/BnanZ0/ok-nte/blob/fb1d502026acd66b4dabfba3b85bd6250c672305/src/tasks/LauncherTask.py#L299-L304) 在遊戲擷取連線完成後呼叫 `og.app.start_controller.check_resolution()`。
4. ok-nte 固定使用 [`ok-script==2.0.1`](https://github.com/BnanZ0/ok-nte/blob/fb1d502026acd66b4dabfba3b85bd6250c672305/requirements.txt#L63)。

## ok-script 2.0.1 的實際縮放流程

1. [`TaskExecutor.check_frame_and_resolution()`](https://github.com/ok-oldking/ok-script/blob/ec92492d00c45d206c7ed6b1ddc1845633661732/ok/task/TaskExecutor.py#L210-L243) 取得 capture 的 `width`、`height`，以 `width / height` 比較 16:9；允許誤差為目標比例的 1%，並檢查 1920×1080 最低尺寸。
2. [`StartController.check_resolution()`](https://github.com/ok-oldking/ok-script/blob/ec92492d00c45d206c7ed6b1ddc1845633661732/ok/core/start_controller.py#L246-L280) 僅在檢查失敗、是 Windows capture、存在 `resize_to` 且 Auto Resize 已啟用時，呼叫 `capture_method.hwnd_window.try_resize_to(resize_to)`。
3. [`HwndWindow.try_resize_to()`](https://github.com/ok-oldking/ok-script/blob/ec92492d00c45d206c7ed6b1ddc1845633661732/ok/device/capture_methods/hwnd_window.py#L134-L168)：
   - 先確認 Auto Resize 選項；其預設值為 `True`（[`GlobalConfig.py`](https://github.com/ok-oldking/ok-script/blob/ec92492d00c45d206c7ed6b1ddc1845633661732/ok/util/GlobalConfig.py#L48-L57)）。
   - 用 `GetSystemMetrics` 取得主螢幕大小。
   - 取得目前 window/client bounds，算出邊框寬度與標題列高度。
   - 依 `resize_to` 順序選第一個「client 尺寸加視窗裝飾後仍放得進主螢幕」的解析度。
   - 將 client 目標尺寸加回邊框與標題列尺寸，交給 `resize_window()`，最後重新讀取尺寸確認成功。
4. [`show_title_bar()` 與 `resize_window()`](https://github.com/ok-oldking/ok-script/blob/ec92492d00c45d206c7ed6b1ddc1845633661732/ok/util/window.py#L190-L247) 完成 Win32 操作：
   - `GetWindowLong`／`SetWindowLong` 加入 `WS_CAPTION`、移除 `WS_POPUP`，再以 `SetWindowPos(..., SWP_FRAMECHANGED, ...)` 套用視窗樣式。
   - 第一次 `SetWindowPos` 設定外框寬高；第二次根據 `GetWindowRect` 與主螢幕尺寸把視窗置中。
   - 最多輪詢 5 秒，確認外框尺寸與位置已生效。

## Windows API 意義

- Microsoft 說明 [`SetWindowPos`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos) 可變更頂層視窗的大小與位置；這正是實際調整遊戲視窗的 API。
- [`GetWindowRect`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect) 回傳視窗外框的螢幕座標，框架用它驗證尺寸並計算置中位置。
- [`SetWindowLongW`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongw) 文件指出，修改 frame style 後應呼叫帶 `SWP_FRAMECHANGED` 的 `SetWindowPos`；框架即採此流程。
- [`GetSystemMetrics`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getsystemmetrics) 用於取得主螢幕尺寸，以決定哪個候選 16:9 尺寸放得下。

## 對 MaaStellaSora 的啟示

可借用的是「先量測 client 與 outer window 差值，再以目標 client 解析度換算外框尺寸」的方式，而非直接把外框設成 1920×1080。若未來移植，需另外考量：是否允許改成有標題列的 windowed 模式、多螢幕選擇、DPI virtualization、遊戲是否接受外部 resize，以及不要影響既有 16:9 使用者。
