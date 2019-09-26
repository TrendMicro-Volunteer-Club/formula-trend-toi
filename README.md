# 趨勢科技 - Formula Trend
Formula Trend相關範例程式碼、文件、模擬器，以及實體車韌體。

## 開發環境準備
1. 安裝[Python 3.7](https://www.python.org/downloads/)，請記錄安裝路徑
2. 將Python路徑新增至系統變數
    - Windows：
        1. 開啟 [控制台] > [系統及安全性] > [系統]
        2. 點選 [進階系統設定]
        3. 在 [進階] 標籤中，點選 [環境變數]
        4. 在 [系統變數] 區塊中，找到 **Path**
        5. 新增`python.exe`的執行檔案路徑
            > 預設路徑通常為 `C:\Program Files\Python 3.7` 或 `C:\Python37`
3. 以系統管理員身份打開命令提示字元
4. 輸入以下指令，安裝相依套件，確保無錯誤訊息：
    ```
    pip install jupyter matplotlib opencv-python pillow eventlet flask-socketio
    ```
5. 透過[Git](https://git-scm.com/)下載此git repository所有內容


## 快速開始

> **注意**  
> 實體車和模擬器的程式呼叫介面並不相同，區分如下：
> - 模擬器AI：`sample_bot/follow_red_line/sample_bot_py3.py`
> - 實體車AI：`trendcar/trendcar/brains/pilot.py`
> 請根據其所運作的平台 (模擬器、實體車) 選取適當的介面進行開發

### 模擬器
1. 下載 [模擬器] 並解壓縮
2. 開啟解壓縮的 `Windows_auto`資料夾
3. 滑鼠雙擊 `StartGame_local.bat`開啟模擬器
4. 開啟命令提示字元
5. 切換至本git repository的根目錄，並進入`sample_bot/follow_red_line`
6. 執行以下指令，就會透過預設的樣板程式進行模擬器賽車控制：
    ```
    python sample_bot_py3.py
    ```

### 實體車
1. 透過SSH連線至車輛
    > - 連線方式可選擇Wi-fi或USB UART連接線  
    > - 詳細資料可參考 [Wiki](https://github.com/TrendMicro-Volunteer-Club/formula-trend-toi/wiki/開發環境架設)
2. 將欲測試的 `trendcar/trendcar/brains/pilot.py` 傳送並覆蓋至的 `/opt/trendcar/trendcar/brains/pilot.py`
3. 執行`trendcar-config`
4. 進入[TrendCar Options] > [Control Daemon] > [Reload Daemon]重新啟動車輛的AI控制程式
5. 將實體車置放於賽道，辨識go號誌之後開始測試車輛
    > - 若無go號誌，也可開啟`tredncar-console`之後執行按Tab強制車輛開始運作。  
    > - 預設狀況下車輛超過320秒之後會停止`pilot.py`的運作