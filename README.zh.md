# HakuRiver - 迷你資源協調器

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

![HakuRiver logo svg](image/logo.svg)

***此專案為實驗性質，使用風險自負***

**HakuRiver** 是一個輕量級、自託管的叢集管理器，專為在計算節點間分配命令列任務而設計。它專注於分配 CPU 核心（透過 **systemd CPU 配額**）和記憶體限制、管理任務生命週期，現在還提供 **NUMA 節點定位**和**多節點任務提交**。

HakuRiver 非常適合小型研究叢集、開發環境或內部批次處理系統，這些環境中完整功能的 HPC 排程器可能過於複雜，但仍需要一定程度的資源控制和分配。

---

## 🤔 HakuRiver 的適用場景（和不適用場景）

| HakuRiver 適用於...                                                                                                  | HakuRiver 不適用於...                                                                                                                 |
| :------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------- |
| ✅ 在小型叢集（例如 < 10 個節點）上管理命令列任務/腳本。                                                              | ❌ 在大型叢集上取代功能豐富的 HPC 排程器（Slurm、PBS、LSF）。                                                                          |
| ✅ 將任務分配到特定的 **NUMA 節點**進行效能調整（`numactl`）。                                                        | ❌ 超出 CPU 配額、記憶體限制和 NUMA 綁定之外的複雜資源管理（例如 GPU 調度、網路頻寬、授權）。                                      |
| ✅ 提交單一命令以同時在**多個節點或 NUMA 節點**上運行。                                                               | ❌ 複雜的任務依賴管理或工作流程協調（請使用 Airflow、Prefect、Snakemake、Nextflow）。                                                   |
| ✅ 開發、測試或小型研究設置，需要比複雜排程器更簡單的替代方案。                                                       | ❌ 進階排程策略（公平共享、搶占、回填、複雜優先級）。HakuRiver 使用直接的用戶定位。                                                   |
| ✅ 基本任務提交、狀態檢查、日誌檢索和終止功能足夠的內部工具。                                                         | ❌ 需要超出網路可訪問性之外的強大內建身份驗證/授權的高安全性、多租戶環境。                                                           |
| ✅ 主要運行 CPU/記憶體密集型應用程式。                                                                               | ❌ 自動優化 NUMA 放置 – 用戶指定目標。                                                                                                 |
| ✅ 在叢集提交*之前*使用包含的 `hakurun` 工具進行本地參數掃描。                                                        | ❌ 用叢集提交替代 `hakurun` 本身 – 它們服務於不同目的（本地與分散式）。                                                                |

---

## ✨ 功能

* **通過 systemd 進行 CPU/RAM 資源分配：** 任務請求 CPU 核心（以 **CPU 配額百分比**執行）和**記憶體限制**，通過 `systemd-run` 應用。
* **基於 Systemd 的任務執行：** 任務以臨時 systemd 範圍單元（`systemd-run --scope`）運行，以獲得更好的生命週期管理和資源記帳。
* **NUMA 節點定位：** 可選地使用 `numactl` 將任務綁定到特定 NUMA 節點（需要在運行器上安裝 `numactl` 並配置路徑）。
* **多節點/NUMA 任務提交：** 提交單一請求以在多個指定節點或節點內的特定 NUMA 節點上運行相同命令。
* **持久的任務和節點記錄：** 主機維護 SQLite 數據庫，包含節點（包括檢測到的 NUMA 拓撲）和任務（狀態、目標、資源請求、日誌）。
* **節點健康和資源感知：** 基本心跳檢測離線運行器。運行器報告整體 CPU/記憶體使用情況和 NUMA 拓撲。
* **獨立參數擴展（`hakurun`）：** 用於在提交到叢集之前進行本地參數掃描（`span:{..}`、`span:[]`）的工具。改善並行 Python 執行穩健性。
* **Web 儀表板（實驗性）：** Vue.js 前端，用於視覺化監控、任務提交（包括多目標）、狀態檢查和終止任務。

## 🏗️ 架構概述
![](image/README/HakuRiverArch.jpg)

* **主機（`hakuriver.host`）：** 中央協調器。管理節點註冊（包括 NUMA 拓撲），追蹤節點狀態/資源，在數據庫中存儲任務信息，接收任務提交請求（包括多目標），驗證目標，生成唯一任務 ID，並將單個任務實例分派到適當的運行器。
* **運行器（`hakuriver.runner`）：** 每個計算節點上的代理。檢測 NUMA 拓撲（通過 `numactl`），向主機註冊（報告核心、RAM、NUMA 信息、URL）。定期發送心跳（包括 CPU/記憶體使用情況）。使用 `sudo systemd-run` 執行分配的任務，應用 CPU 配額、記憶體限制和可選的 `numactl` 綁定。將任務狀態更新報告回主機。**需要 `systemd-run` 和 `systemctl` 的無密碼 `sudo`。**
* **客戶端（`hakuriver.client`）：** CLI 工具。與主機通信以提交任務（指定命令、參數、環境、資源和**一個或多個目標**，如 `host1` 或 `host1:0`），查詢任務/節點狀態（包括 NUMA 信息），並終止任務。
* **前端：** 可選的 Web UI，提供類似於客戶端的視覺化概覽和交互功能。
* **數據庫：** 主機通過 Peewee 使用 SQLite 存儲節點清單（包括作為 JSON 的 NUMA 拓撲）和任務詳情（包括目標 NUMA ID、批次 ID）。
* **存儲：**
  * **共享（`shared_dir`）：** 在主機和所有運行器上以相同路徑掛載。對於任務輸出日誌（`*.out`、`*.err`）和潛在的共享腳本/數據至關重要。
  * **本地臨時（`local_temp_dir`）：** 節點特定的快速存儲，路徑作為 `HAKURIVER_LOCAL_TEMP_DIR` 環境變量注入任務。


HakuRiver 的通信流程圖：
![](image/README/HakuRiverFlow.jpg)

---

## 🚀 開始使用

### 安裝

1. 複製儲存庫：
   ```bash
   git clone https://github.com/KohakuBlueleaf/HakuRiver.git
   cd HakuRiver
   ```
2. 安裝包（最好在虛擬環境中）：
   ```bash
   # 安裝 hakuriver 及其依賴項
   pip install .
   # 或用於開發：
   # pip install -e .
   ```

   這樣即可使用 `hakurun`、`hakuriver.host`、`hakuriver.runner` 和 `hakuriver.client`。
3. **（運行器節點）** 如果打算使用 NUMA 定位，請安裝 `numactl`：
   ```bash
   # Debian/Ubuntu 示例
   sudo apt update && sudo apt install numactl
   # CentOS/RHEL 示例
   sudo yum install numactl
   ```

---

## `hakurun`：本地參數擴展工具

`hakurun` 幫助*本地*運行帶有多個參數組合的命令或 Python 腳本，在提交到 HakuRiver 叢集之前進行測試非常有用。

* **參數擴展：**
  * `span:{start..end}` -> 整數（例如，`span:{1..3}` -> `1`、`2`、`3`）
  * `span:[a,b,c]` -> 列表項目（例如，`span:[foo,bar]` -> `"foo"`、`"bar"`）
* **執行：** 運行所有擴展參數的笛卡爾積。使用 `--parallel` 通過子進程並行運行組合。
* **目標：** 運行 Python 模塊（`mymod`）、函數（`mymod:myfunc`）或可執行文件（`python script.py`、`my_executable`）。

**示例（`demo_hakurun.py`）：**

```python
# demo_hakurun.py
import sys, time, random
time.sleep(random.random() * 0.1)
print(f"Args: {sys.argv[1:]}, PID: {os.getpid()}")
```

```bash
# 本地並行運行 2 * 1 * 2 = 4 個任務
hakurun --parallel python ./demo_hakurun.py span:{1..2} fixed_arg span:[input_a,input_b]
```

**注意：** `hakurun` 是本地輔助工具。它**不**與 HakuRiver 叢集交互。使用它生成以後可能單獨或作為批次使用 `hakuriver.client` 提交的命令。

---

## 🔧 配置 - HakuRiver

* 您可以使用 `hakuriver.init` 創建全局默認配置，此命令將在 `~/.hakuriver/config.toml` 中創建默認配置文件，所有命令默認將使用此配置。
* 默認配置內容：`src/hakuriver/utils/default_config.toml`。
* 對任何 `hakuriver.*` 命令使用 `--config /path/to/custom.toml` 進行覆蓋。
* **需要審查/編輯的關鍵設置：**
  * `[network] host_reachable_address`：**必須**是運行器和客戶端可訪問的主機 IP/主機名。
  * `[network] runner_address`：**必須**是主機可訪問的運行器 IP/主機名。
  * `[paths] shared_dir`：共享存儲的絕對路徑（必須在運行器節點上存在且可寫，在主機節點上可讀）。
  * `[paths] local_temp_dir`：本地臨時存儲的絕對路徑（必須在運行器節點上存在且可寫）。
  * `[paths] numactl_path`：運行器節點上 `numactl` 可執行文件的絕對路徑（例如，`/usr/bin/numactl`）。如果為空，運行器將嘗試直接使用 `numactl`。
  * `[database] db_file`：主機 SQLite 數據庫的路徑。確保目錄存在。

---

## 💻 使用 - HakuRiver 叢集

**1. 初始化配置：**
在每個節點（主機和運行器）上使用 `hakuriver.init` 命令在 ~/.hakuriver/config.toml 創建配置文件。
然後您可以根據您的設置修改配置。
```bash
hakuriver.init
vim ~/.hakuriver/config.toml
```

**2. 啟動主機服務器（在管理節點上）：**

```bash
   hakuriver.host
   # 使用自定義配置：
   # hakuriver.host --config /path/to/host_config.toml
```

或者您可以在系統中創建服務：
```bash
   hakuriver.init service --host
   # 使用自定義配置：
   # hakuriver.init service --host --config /path/to/host_config.toml
   systemctl restart hakuriver-host
   systemctl enable hakuriver-host
   # 檢查運行狀態
   # systemctl status hakuriver-host
```

**3. 啟動運行器代理（在每個計算節點上）：**

```bash
   # 重要：以具有以下命令 NOPASSWD sudo 訪問權限的用戶身份運行：
   # /usr/bin/systemd-run, /usr/bin/systemctl
   # （需要用於任務啟動、資源限制、終止任務，如果通過 sudo 運行可能還需要 numactl）
   # sudoers 條目示例：
   # your_user ALL=(ALL) NOPASSWD: /usr/bin/systemd-run, /usr/bin/systemctl

   hakuriver.runner
   # 使用自定義配置：
   # hakuriver.runner --config /path/to/runner_config.toml
```

或者您可以在系統中創建服務：
```bash
   hakuriver.init service --runner
   # 使用自定義配置：
   # hakuriver.init service --runner --config /path/to/runner_config.toml
   systemctl restart hakuriver-runner
   systemctl enable hakuriver-runner
   # 檢查運行狀態
   # systemctl status hakuriver-runner
```

**4. Systemd 執行說明：**
* `systemd-run` 和 `systemctl` 用於任務執行和管理。這些命令通過 `sudo` 運行以確保適當的權限。您應該擁有這些命令的無密碼 sudo 訪問權限。
* 通過 `systemd-run` 運行的任務將繼承運行器的工作目錄（通常在用戶的主目錄或 `/` 中啟動）。使用絕對路徑或環境變量（`HAKURIVER_SHARED_DIR`、`HAKURIVER_LOCAL_TEMP_DIR`）。
* 任務環境包括通過 `--env` 設置的變量、`HAKURIVER_*` 變量，以及可能由 `systemd --user` 實例或系統實例繼承的變量，取決於 `systemd-run` 如何被 sudo 調用。

**5. 使用客戶端（`hakuriver.client`）：**

| 操作                         | 命令示例                                                                                                                                            | 備註                                                                         |
| :--------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------- |
| **列出節點**                 | `hakuriver.client --list-nodes`                                                                                                                     | 顯示狀態、核心、NUMA 摘要。                                                   |
| **節點健康狀況**             | `hakuriver.client --health` <br> `hakuriver.client --health <node-hostname>`                                                                        | 顯示詳細統計信息，包括完整 NUMA 拓撲（如果可用）。                            |
| **提交單一任務**             | `hakuriver.client --target <host1> --cores 1 -- echo "Basic Task"`                                                                                  | 在 `<host1>` 的任何可用核心上運行。                                         |
| **提交（NUMA）**             | `hakuriver.client --target <host1>:0 --cores 2 --memory 1G -- ./my_numa_script.sh`                                                                  | 綁定在 `<host1>` 的 NUMA 節點 0 上運行。需要運行器上有 `numactl`。         |
| **提交（多 NUMA）**          | `hakuriver.client --target <host1>:0 --target <host1>:1 --cores 1 -- ./process_shard.sh`                                                            | 在 `<host1>` 上運行兩個任務實例，一個在 NUMA 0，一個在 NUMA 1。           |
| **提交（多節點）**           | `hakuriver.client --target <host1>:0 --target <host2> --cores 4 --env P=1 -- ./parallel_job.sh`                                                     | 在 `<host1>` 的 NUMA 0 和 `<host2>` 的任何核心上運行。                     |
| **檢查狀態**                 | `hakuriver.client --status <task_id>`                                                                                                               | 顯示詳細狀態，包括目標 NUMA、批次 ID。                                        |
| **終止任務**                 | `hakuriver.client --kill <task_id>`                                                                                                                 | 請求終止特定任務實例。                                                       |
| **提交 + 等待**              | `hakuriver.client --target <host1>:0 --wait -- sleep 30`                                                                                            | 等待指定任務完成。與多目標一起使用時要謹慎。                                  |
| **使用自定義配置**           | `hakuriver.client --config client.toml --list-nodes`                                                                                                | 加載客戶端配置覆蓋。                                                         |
| **與 hakurun 結合**          | `hakurun hakuriver.client --target <host1>:0 --cores 1 -- python script.py span:{1..10}` <br>（提交 10 個獨立的 HakuRiver 任務）                   | 適用於提交多個類似*獨立*叢集任務。                                          |
| **與 hakurun 結合**          | `hakuriver.client --target <host1>:0 --cores 4 -- hakurun --parallel python process.py span:{A..Z}` <br>（提交 1 個運行 hakurun 的 HakuRiver 任務） | 適用於將多個小型、相關步驟分組為*一個*叢集任務。                            |

   **`--target` 語法：**

| 格式                | 描述                                      |
| :------------------ | :---------------------------------------- |
| `my-node`         | 目標物理節點 `my-node`。                |
| `my-node:0`       | 目標 `my-node` 上的 NUMA 節點 0。       |
| `another-node:1`  | 目標 `another-node` 上的 NUMA 節點 1。   |

---

## 🌐 使用 - 前端 Web UI（實驗性）

| 概述                                               | 節點列表和任務列表                                                                                  | 從管理器 UI 提交任務                             |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| ![1744643963836](image/README/1744643963836.png) | ![1744643981874](image/README/1744643981874.png) ![1744643997740](image/README/1744643997740.png) | ![1744644009190](image/README/1744644009190.png) |

HakuRiver 包含一個可選的 Vue.js 儀表板，用於視覺化監控和管理。

**先決條件：**

* Node.js 和 npm/yarn/pnpm。
* 從您運行前端開發服務器的位置可訪問的運行中 HakuRiver 主機。

**設置：**

```bash
cd frontend
npm install
```

**運行（開發）：**

1. 確保主機正在運行（例如，`http://127.0.0.1:8000`）。
2. 啟動 Vite 開發服務器：
   ```bash
   npm run dev
   ```
3. 打開提供的 URL（例如，`http://localhost:5173`）。
4. 開發服務器將 `/api` 請求代理到主機（見 `vite.config.js`）。
5. **功能：**
   * 查看節點列表、狀態、資源和 **NUMA 拓撲**。
   * 查看任務列表、詳情（包括批次 ID、目標 NUMA）、日誌。
   * 使用表單提交新任務，該表單包括**多目標選擇器**，允許選擇整個節點或特定 NUMA 節點。
   * 終止正在運行的任務。

**構建（生產）：**

1. 構建靜態文件：
   ```bash
   npm run build
   ```
2. 使用任何靜態 Web 服務器（Nginx、Apache 等）提供 `frontend/dist` 的內容。
3. **重要：** 配置您的生產 Web 服務器以代理 API 請求（例如，對 `/api/*` 的請求）到實際運行的 HakuRiver 主機地址和端口，類似於 Vite 開發服務器代理，或者在構建前修改 `src/services/api.js` 以使用主機的絕對 URL。


## 🙏 致謝

* Gemini 2.5 pro：基本實現和初始 README 生成。
* Claude 3.7 Sonnet：完善 logo SVG 代碼。