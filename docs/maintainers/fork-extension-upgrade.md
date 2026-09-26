# Fork 擴充與上游更新

本 fork 的擴充以 upstream `7846391` 為初始基準。功能位於 `agent/fork_ext/`、`assets/resource/fork/`，任務定義位於 `assets/resource/fork/tasks.json`。原分支 `feature/ultrawide-5120x2160` 保留作移植對照。同步上游時，先檢查下列接點，再處理行為變更；節點仍存在不代表語意未變。

## 固定入口

| 接點 | 必須維持的關係 |
| --- | --- |
| `assets/interface.json` | agent 指向 `agent/fork_ext/entry.py`；匯入 `resource/fork/tasks.json`；每種語系先載入上游資源，再載入 `fork/base` 與對應語系的 fork 資源。 |
| `agent/fork_ext/entry.py` | 先匯入上游 `agent/main.py` 與 fork 動作／辨識，註冊完成後啟動 agent；視窗比例控制在退出時清理。 |
| `tools/ci/install.py`、`tools/ci/install_mxu.py` | 安裝時保留 `interface.json` 指定的 agent 入口，轉換為安裝包內相對路徑。上游若重寫安裝流程，須重查這兩處。 |

這三處是同步上游時預期需要比對的原有檔案。Fork 的任務、Python 程式、圖片和 pipeline 變更放在專屬路徑。相同名稱的 fork 節點以**完整節點**覆寫；上游增加欄位時，必須重新比較覆寫內容，避免蓋掉新行為。

## 必查節點與行為

| 功能 | 上游接點 | 驗收行為 |
| --- | --- | --- |
| 自動刷 650 入口與準備 | `星塔_入口_agent` → `ascension_preparation` | 仍會載入各語系事件規則，且每次任務重置潛能狀態。 |
| 事件選項 | `星塔_节点_进行对话选择_agent` → `event_recognition` | Fork 辨識先評估後果含 `650` 的規則，其餘規則維持上游順序。 |
| 潛能 | `星塔_节点_选择潜能_agent` → `choose_potential_recognition`；`星塔_节点_选择潜能_点击刷新_agent` | 核心潛能選推薦；一般潛能只取推薦等級 6 的合格項。新普通潛能選後須為 3 級；新稀有潛能選後可為 2 或 3 級；其次升級既有潛能。無合格項時刷新；次數用完或刷新後金幣不足時，選保底卡前進，並標記到首次商店放棄重試。辨識資料缺失、實際刷新失敗或點擊失敗仍停止。上游的 `Data`、`PotentialInteractor`、`RecommendationHandler` 介面變更時重查 Fork 辨識。 |
| 首次商店與重試 | `星塔_节点_进入商店_agent`、`星塔_通用_识别当前金币_agent`、`星塔_循环用节点_agent` | 正常抵達首次商店時，金幣讀取失敗即停止；達 1200 停止；不足才放棄。潛能已標記重試時跳過商店金幣檢查。點左上角返回後，`星塔_自动刷650_放弃_agent` 應以 OCR 命中的「放棄」位置點擊；台服確認視窗只有「放棄」與「暫時離開」，不能等待「確認」節點。放棄後辨識儲存紀錄或返回畫面，再回到循環；循環需清除標記並重置潛能狀態。 |
| 心鏈送禮 | `心链_入口`、`心链_点击邮寄`、`心链_选择礼物`、`心链_赠送礼物`；`InviteAuto` 的 `_scroll_to_next_page`、`_scroll_to_top` | 獨立任務先經 `心链送礼新_选择旅人`，指定旅人找不到即停止；藍色模式由 `心链送礼新_选择十个蓝色礼物` 選滿 10 個才進入贈送。檢查圖片 `gift_blue_good.png`、禮物數量 OCR 與繼承的列表捲動方法。 |
| 邀約結算 | `邀约_点击空白`、`邀约_还是算了`、`邀约_送出礼物`、`邀约_默契提升` | 結算後仍能點掉人物／彈窗並回到邀約介面；上游若已修好同一情境，移除重複覆寫。比較 `fork_invite.json` 的完整節點與各語系 OCR。 |
| 追獵結算 | `猎影合围_追踪目标_战斗结束`、`猎影合围_协助_战斗结束`、`通用_点击空白处继续` | 點擊空白後補點畫面中心，避免好友畫面吃掉點擊；檢查返回主介面的下一節點順序。 |
| 台服辨識 | `fork/tw/pipeline`、上游 `tw/pipeline` | 放棄／確認、邀約及追獵 OCR 保留繁體預期文字；爬塔事件規則仍載入台服版本。舊版 `choose_record.json` 修改與目前上游相同，無需覆寫。 |

## 每次更新步驟

1. 記錄更新前的上游提交與工作區狀態，取得 upstream 最新 `main`，在獨立分支整合。比較上表的入口與節點，包括原節點的動作、辨識、`next`、`attach` 及各語系覆寫。
2. 執行唯讀檢查：`python tools/check_fork_compat.py`。失敗時先調整擴充接點或移除已被上游取代的覆寫，不要只更新檢查條件。
3. 使用已安裝 MaaFramework 的 Python 執行 `tools/check_fork_resources_runtime.py`。Windows 本地可用 `./install/python/python.exe -X utf8 tools/check_fork_resources_runtime.py`；它會依介面設定載入四種資源組合並核對覆寫後的關鍵節點。
4. 用同一 Python 執行 `-X utf8 -m unittest discover -s tests -p 'test_*.py'`，另執行安裝腳本測試 `python -m unittest discover -s tools/ci -p 'test_install_mxu.py'`。檢查一般上游任務及安裝包的 agent 入口；實機檢查台服 650 首次商店、藍禮物選滿 10 個才送出，以及邀約／追獵結算。

檢查腳本只驗證已知接點，無法證明 OCR、遊戲畫面與上游新策略語意完全相容。上游若重構上述流程，先比較新版流程，再更新 Fork 的任務覆寫及本文件。
