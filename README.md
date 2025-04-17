# HakuRiver - Mini Resource Orchestrator

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

![HakuRiver logo svg](image/logo.svg)

***THIS PROJECT IS EXPERIMENTAL, USE AT YOUR OWN RISK***

**HakuRiver** is a lightweight, self-hosted cluster manager designed for distributing command-line tasks across compute nodes. It focuses on allocating CPU cores (via **systemd CPU Quotas**) and memory limits, managing task lifecycles, and now offers **NUMA node targeting** and **multi-node task submission**.

It leverages **systemd** for execution and basic sandboxing (`PrivateNetwork`, `PrivatePID`). HakuRiver is ideal for small research clusters, development environments, or internal batch processing systems where full-featured HPC schedulers might be overkill but some level of resource control and distribution is needed.

---

## 🤔 What HakuRiver Is (and Isn't)

| HakuRiver IS FOR...                                                                                                                            | HakuRiver IS NOT FOR...                                                                                                                               |
| :--------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------- |
| ✅ Managing command-line tasks/scripts across a small cluster (e.g., < 10 nodes).                                                              | ❌ Replacing feature-rich HPC schedulers (Slurm, PBS, LSF) on large clusters.                                                                         |
| ✅ Distributing tasks to specific **NUMA nodes** for performance tuning (`numactl`).                                                             | ❌ Complex resource management beyond CPU quotas, memory limits, and NUMA binding (e.g., GPU scheduling, network bandwidth, licenses).                |
| ✅ Submitting a single command to run simultaneously on **multiple nodes or NUMA nodes**.                                                      | ❌ Sophisticated task dependency management or workflow orchestration (Use Airflow, Prefect, Snakemake, Nextflow).                                      |
| ✅ Environments needing basic CPU/Memory limits and optional process/network isolation via **systemd**.                                          | ❌ Environments **without systemd** or where the runner user lacks **passwordless `sudo`** for `systemd-run` and `systemctl`.                           |
| ✅ Development, testing, or small research setups needing a simpler alternative to complex schedulers.                                         | ❌ Advanced scheduling policies (fair-share, preemption, backfilling, complex priorities). HakuRiver uses direct user targeting.                     |
| ✅ Internal tools where basic job submission, status checking, log retrieval, and termination are sufficient.                                    | ❌ High-security, multi-tenant environments requiring robust built-in authentication/authorization beyond network accessibility.                        |
| ✅ Running primarily CPU/Memory-bound applications.                                                                                            | ❌ Automatically optimizing NUMA placement – user specifies the target.                                                                               |
| ✅ Using the included `hakurun` utility for local parameter sweeps *before* cluster submission.                                                 | ❌ Replacing `hakurun` itself with cluster submission – they serve different purposes (local vs distributed).                                         |

---

## ✨ Features

*   **CPU/RAM Resource Allocation via systemd:** Jobs request CPU cores (enforced as **CPU Quota percentage**) and a **Memory Limit**, applied via `systemd-run`.
*   **Systemd-Based Task Execution:** Tasks run as transient systemd scope units (`systemd-run --scope`) for better lifecycle management and resource accounting.
*   **NUMA Node Targeting:** Optionally bind tasks to specific NUMA nodes using `numactl` (requires `numactl` installed on runners and path configured).
*   **Multi-Node/NUMA Task Submission:** Submit a single request to run the same command across multiple specified nodes or specific NUMA nodes within nodes.
*   **Optional Sandboxing:** Basic systemd sandboxing (`PrivateNetwork=yes`, `PrivatePIDs=yes`) configurable per task batch.
*   **Persistent Task & Node Records:** Host maintains SQLite DB of nodes (including detected NUMA topology) and tasks (status, target, resource requests, logs).
*   **Node Health & Resource Awareness:** Basic heartbeat detects offline runners. Runners report overall CPU/Memory usage and NUMA topology.
*   **Standalone Argument Spanning (`hakurun`):** Utility for local parameter sweeps (`span:{..}`, `span:[]`) before submitting to the cluster. Improves parallel Python execution robustness.
*   **Web Dashboard (Experimental):** Vue.js frontend for visual monitoring, task submission (incl. multi-target), status checks, and killing tasks.

## 🏗️ Architecture Overview

```ascii
+-----------------+      HTTP API       +-----------------+      HTTP API       +--------------------+
|  Client (CLI)   |<------------------->|   Host Server   |<------------------->|  Frontend (Web UI) |
| (hakuriver.cli) | (Submit, Status,    | (hakuriver.core)| (Node/Task Data,    | (Vue.js)           |
|                 |  Kill, List, ...)   |  - FastAPI      |  Submit, Kill)      |  - Monitoring      |
|                 |                     |  - Peewee (DB)  |                     |  - Submit Task     |
|                 |                     |  - Scheduling*  |                     |  - Check result    |
+-----------------+                     |  - State Mgmt   |                     +--------------------+
                                        +--------+--------+
                                                 | ▲  │ Registration, Heartbeat, Status Update
                                                 │ │  ▼ Task Execution Command, Kill Command
                                        +--------▼-+-------------+      +------------------------+
                                        | Runner Agent (Node 1)  |      | Runner Agent (Node N)  |
                                        | (hakuriver.core)       |      | (hakuriver.core)       |
                                        |  - FastAPI             |      |  - FastAPI             |
                                        |  - NUMA Detect         |      |  - NUMA Detect         |
                                        |  - systemd-run (+sudo) |      |  - systemd-run (+sudo) |
                                        |  - numactl             |      |  - numactl             |
                                        +------------------------+      +------------------------+
                                                    │                               │
 Shared Filesystem (NFS, etc.)                      │ Access (Scripts, Output)      │ Access (Scripts, Output)
+----------------------------------+                ▼                               ▼
| /path/to/shared_dir              |<------------------------------------------------
|  - scripts/                      |                │                               │
|  - task_outputs/ (*.out)         |                │ Access (Temporary data)       │ Access (Temporary data)
|  - task_errors/  (*.err)         |                ▼                               ▼
+----------------------------------+    Node 1 Local Filesystem         Node N Local Filesystem
                                       +--------------------------+     +--------------------------+
                                       | /path/to/local_temp_dir  |     | /path/to/local_temp_dir  |
                                       +--------------------------+     +--------------------------+

 Host Local Filesystem
+----------------------------------+
| /path/to/database/cluster.db     |
+----------------------------------+

* Scheduling: Host validates targets & resources but relies on user specification via Client/Frontend.
```

*   **Host (`hakuriver.host`):** Central coordinator. Manages node registration (including NUMA topology), tracks node status/resources, stores task information in the DB, receives task submission requests (including multi-target), validates targets, generates unique task IDs, and dispatches individual task instances to the appropriate Runners.
*   **Runner (`hakuriver.runner`):** Agent on each compute node. Detects NUMA topology (via `numactl`), registers with Host (reporting cores, RAM, NUMA info, URL). Sends periodic heartbeats (incl. CPU/Mem usage). Executes assigned tasks using `sudo systemd-run`, applying CPU Quota, Memory Limits, optional sandboxing, and optional `numactl` binding. Reports task status updates back to the Host. **Requires passwordless `sudo` for `systemd-run` and `systemctl`.**
*   **Client (`hakuriver.client`):** CLI tool. Communicates with Host to submit tasks (specifying command, args, env, resources, and **one or more targets** like `host1` or `host1:0`), query task/node status (incl. NUMA info), and kill tasks.
*   **Frontend:** Optional web UI providing visual overview and interaction capabilities similar to the Client.
*   **Database:** Host uses SQLite via Peewee to store node inventory (incl. NUMA topology as JSON) and task details (incl. target NUMA ID, batch ID).
*   **Storage:**
    *   **Shared (`shared_dir`):** Mounted at the same path on Host and all Runners. Essential for task output logs (`*.out`, `*.err`) and potentially shared scripts/data.
    *   **Local Temp (`local_temp_dir`):** Node-specific fast storage, path injected as `HAKURIVER_LOCAL_TEMP_DIR` env var for tasks.

---


## 🚀 Getting Started

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/KohakuBlueleaf/HakuRiver.git
    cd HakuRiver
    ```
2.  Install the package (preferably in a virtual environment):
    ```bash
    # Installs hakuriver and its dependencies
    pip install .
    # Or for development:
    # pip install -e .
    ```
    This makes `hakurun`, `hakuriver.host`, `hakuriver.runner`, and `hakuriver.client` available.
3.  **(Runner Nodes)** Install `numactl` if you intend to use NUMA targeting:
    ```bash
    # Example for Debian/Ubuntu
    sudo apt update && sudo apt install numactl
    # Example for CentOS/RHEL
    sudo yum install numactl
    ```

---

## `hakurun`: Local Argument Spanning Utility

`hakurun` helps run commands or Python scripts *locally* with multiple argument combinations, useful for testing before submitting to the HakuRiver cluster.

*   **Argument Spanning:**
    *   `span:{start..end}` -> Integers (e.g., `span:{1..3}` -> `1`, `2`, `3`)
    *   `span:[a,b,c]` -> List items (e.g., `span:[foo,bar]` -> `"foo"`, `"bar"`)
*   **Execution:** Runs the Cartesian product of all spanned arguments. Use `--parallel` to run combinations concurrently via subprocesses.
*   **Targets:** Runs Python modules (`mymod`), functions (`mymod:myfunc`), or executables (`python script.py`, `my_executable`).

**Example (`demo_hakurun.py`):**
```python
# demo_hakurun.py
import sys, time, random
time.sleep(random.random() * 0.1)
print(f"Args: {sys.argv[1:]}, PID: {os.getpid()}")
```
```bash
# Runs 2 * 1 * 2 = 4 tasks locally and in parallel
hakurun --parallel python ./demo_hakurun.py span:{1..2} fixed_arg span:[input_a,input_b]
```

**Note:** `hakurun` is a local helper. It does **not** interact with the HakuRiver cluster. Use it to generate commands you might later submit individually or as a batch using `hakuriver.client`.

---

## 🔧 Configuration - HakuRiver

*   You can create a global default config with `hakuriver.init`, this command will create a default config file in `~/.hakuriver/config.toml`, all the command will use this config by default.
*   Content of default config: `src/hakuriver/utils/default_config.toml`.
*   Override with `--config /path/to/custom.toml` for any `hakuriver.*` command.
*   **CRITICAL SETTINGS TO REVIEW/EDIT:**
    *   `[network] host_reachable_address`: **Must** be the IP/hostname of the Host reachable by Runners and Clients.
    *   `[network] runner_address`: **Must** be the IP/hostname of the Runner reachable by Host.
    *   `[paths] shared_dir`: Absolute path to shared storage (must exist and be writable on runner nodes and readable on host node).
    *   `[paths] local_temp_dir`: Absolute path to local temp storage (must exist and be writable on runner nodes).
    *   `[paths] numactl_path`: Absolute path to `numactl` executable on runner nodes (e.g., `/usr/bin/numactl`). If empty, runner will try to use `numactl` directly.
    *   `[database] db_file`: Path for the Host's SQLite database. Ensure the directory exists.

---

## 💻 Usage - HakuRiver Cluster

**1. Initialize Database (Run once on Host machine):**
   The Host attempts this on startup. Ensure the directory for `db_file` exists and is writable. Delete the DB file if upgrading with schema changes.

**2. Start Host Server (on manager node):**
   ```bash
   hakuriver.host
   # With custom config:
   # hakuriver.host --config /path/to/host_config.toml
   ```

**3. Start Runner Agent (on each compute node):**
   ```bash
   # IMPORTANT: Run as a user with NOPASSWD sudo access for:
   # /usr/bin/systemd-run, /usr/bin/systemctl
   # (Needed for task launch, resource limits, killing tasks, potentially numactl if run via sudo)
   # Example sudoers entry:
   # your_user ALL=(ALL) NOPASSWD: /usr/bin/systemd-run, /usr/bin/systemctl

   hakuriver.runner
   # With custom config:
   # hakuriver.runner --config /path/to/runner_config.toml
   ```
   *The runner will detect and report its NUMA topology if `numactl` is found and configured.*

**4. Systemd Execution Notes:**
   *   Tasks run via `systemd-run` do *not* inherit the Runner's working directory (usually start in user's home or `/`). Use absolute paths or env vars (`HAKURIVER_SHARED_DIR`, `HAKURIVER_LOCAL_TEMP_DIR`).
   *   The task environment includes variables set via `--env`, `HAKURIVER_*` variables, and potentially variables inherited by the `systemd --user` instance or system instance depending on how `systemd-run` is invoked by sudo.
   *   If `numactl` is used, it prepends the user's actual command within the systemd scope.

**5. Use the Client (`hakuriver.client`):**

   | Action                 | Command Example                                                                                                                               | Notes                                                                          |
   | :--------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------- |
   | **List Nodes**         | `hakuriver.client --list-nodes`                                                                                                               | Shows status, cores, NUMA summary.                                             |
   | **Node Health**        | `hakuriver.client --health` <br> `hakuriver.client --health <node-hostname>`                                                                    | Shows detailed stats, including full NUMA topology if available.               |
   | **Submit Single Task** | `hakuriver.client --target <host1> --cores 1 -- echo "Basic Task"`                                                                              | Runs on any available core on `<host1>`.                                         |
   | **Submit (NUMA)**      | `hakuriver.client --target <host1>:0 --cores 2 --memory 1G -- ./my_numa_script.sh`                                                             | Runs bound to NUMA node 0 on `<host1>`. Requires `numactl` on runner.          |
   | **Submit (Multi-NUMA)**| `hakuriver.client --target <host1>:0 --target <host1>:1 --cores 1 -- ./process_shard.sh`                                                        | Runs two task instances on `<host1>`, one on NUMA 0, one on NUMA 1.            |
   | **Submit (Multi-Node)**| `hakuriver.client --target <host1>:0 --target <host2> --cores 4 --env P=1 -- ./parallel_job.sh`                                                 | Runs on NUMA 0 of `<host1>` and any core on `<host2>`.                         |
   | **Submit (Sandbox)**   | `hakuriver.client --target <host1> --cores 1 --private-network --private-pid -- ./isolated_task.sh`                                              | Applies systemd sandboxing options.                                            |
   | **Check Status**       | `hakuriver.client --status <task_id>`                                                                                                         | Shows detailed status, including target NUMA, batch ID.                      |
   | **Kill Task**          | `hakuriver.client --kill <task_id>`                                                                                                           | Requests termination of a specific task instance.                              |
   | **Submit + Wait**      | `hakuriver.client --target <host1>:0 --wait -- sleep 30`                                                                                        | Waits for the specified task(s) to finish. Use cautiously with multi-target. |
   | **Use Custom Config**  | `hakuriver.client --config client.toml --list-nodes`                                                                                          | Loads client config overrides.                                                 |
   | **Combine w/ hakurun** | `hakurun hakuriver.client --target <host1>:0 --cores 1 -- python script.py span:{1..10}`<br>(Submits 10 separate HakuRiver jobs)                 | Useful for submitting many similar *independent* cluster jobs.                 |
   | **Combine w/ hakurun** | `hakuriver.client --target <host1>:0 --cores 4 -- hakurun --parallel python process.py span:{A..Z}`<br>(Submits 1 HakuRiver job running hakurun) | Useful for grouping many small, related steps into *one* cluster job.          |

   **`--target` Syntax:**

   | Format           | Description                           |
   | :--------------- | :------------------------------------ |
   | `my-node`        | Target the physical node `my-node`.   |
   | `my-node:0`      | Target NUMA node 0 on `my-node`.      |
   | `another-node:1` | Target NUMA node 1 on `another-node`. |

---

## 🌐 Usage - Frontend Web UI (Experimental)


| Overview | Node list and Task list | Submit Task from Manager UI |
| -|-|-|
|![1744643963836](image/README/1744643963836.png)| ![1744643981874](image/README/1744643981874.png) ![1744643997740](image/README/1744643997740.png) | ![1744644009190](image/README/1744644009190.png)|

HakuRiver includes an optional Vue.js dashboard for visual monitoring and management.

**Prerequisites:**
*   Node.js and npm/yarn/pnpm.
*   Running HakuRiver Host accessible from where you run the frontend dev server.

**Setup:**
```bash
cd frontend
npm install
```

**Running (Development):**
1.  Ensure Host is running (e.g., `http://127.0.0.1:8000`).
2.  Start Vite dev server:
    ```bash
    npm run dev
    ```
3.  Open the URL provided (e.g., `http://localhost:5173`).
4.  The dev server proxies `/api` requests to the Host (see `vite.config.js`).
5.  **Features:**
    *   View node list, status, resources, and **NUMA topology**.
    *   View task list, details (incl. Batch ID, Target NUMA), logs.
    *   Submit new tasks using a form that includes a **multi-target selector** allowing node-wide or specific NUMA node selection.
    *   Kill running tasks.

**Building (Production):**
1.  Build static files:
    ```bash
    npm run build
    ```
2.  Serve the contents of `frontend/dist` using any static web server (Nginx, Apache, etc.).
3.  **Important:** Configure your production web server to proxy API requests (e.g., requests to `/api/*`) to the actual running HakuRiver Host address and port, similar to the Vite dev server proxy, OR modify `src/services/api.js` to use the Host's absolute URL before building.

## Feature Details

### NUMA Awareness

Modern multi-socket or high-core-count CPUs often have Non-Uniform Memory Access (NUMA) architectures. Accessing memory attached to the *same* NUMA node (socket) as the running CPU core is faster than accessing memory attached to a *different* NUMA node.

```ascii
+------------------------------- Node: my-compute-01 ------------------------------+
| +------------- NUMA Node-------------+       +--------- NUMA Node 1 -----------+ |
| |  +--- Memory Bank 0 (64 GiB) ---+  |       | +--- Memory Bank 1 (64GiB) ---+ | │
| |  |                              |  |       | |                             | | │
| |  +------------------------------+  |       | +-----------------------------+ | │
| |        ▲                           |       |       ▲                         | │
| |        │ Fast Access               │       │       │ Fast Access             | │
| |  +-----▼------------------------+  |       | +-----▼-----------------------+ | │
| |  | CPU Cores [0, 1, 2, ... 15] <-Interconnect-> CPU Cores [16..31]         | | │
| |  +------------------------------+  |       | +-----------------------------+ | │
| +------------------------------------+       +---------------------------------+ │
+----------------------------------------------------------------------------------+

Example Task Binding:
  Task A --> Bound to NUMA Node 0 (Uses Cores 0-15, Prefers Memory Bank 0) via `numactl --cpunodebind=0 --membind=0 ...`
  Task B --> Bound to NUMA Node 1 (Uses Cores 16-31, Prefers Memory Bank 1) via `numactl --cpunodebind=1 --membind=1 ...`
```

*   **Detection:** Runners use `numactl --hardware` (if available and configured via `numactl_path`) to detect their NUMA layout (nodes, cores per node, memory per node).
*   **Reporting:** Runners send this topology info to the Host during registration.
*   **Targeting:** Users can specify a target like `my-compute-01:0` via the Client or Frontend to request the task run specifically on NUMA node 0 of that host.
*   **Execution:** The Runner prepends the `numactl --cpunodebind=<id> --membind=<id>` command to the user's task command within the `systemd-run` scope, enforcing the binding.

### Multi-Node / Multi-NUMA Task Submission

Users can now submit a single request that HakuRiver replicates across multiple specified targets.

```ascii
+-----------------+       +----------------------------------------------------+
|  Client/        | ----> | Host Server                                        |
|  Frontend       |       | Receives:                                          |
|                 |       |  - Command: `my_script.sh --input {i}`             |
| Request:        |       |  - Cores: 2                                        |
|  Run my_script  |       |  - Targets: ["node1:0", "node1:1", "node2"]        |
|  on node1:0,    |       +----------------------------------------------------+
|  node1:1, node2 |        │                        │                        │                         
+-----------------+        │ Dispatch Task          │ Dispatch Task          │ Dispatch Task           
                           │ (ID: 102, Target: 1:0) │ (ID: 103, Target: 1:1) │ (ID: 103, Target: 2)
                 +---------▼----------+   +---------▼----------+   +---------▼----------+
                 | Runner (Node 1)    |   | Runner (Node 1)    |   | Runner (Node 2)    |
                 | Executes Task 101  |   | Executes Task 102  |   | Executes Task 103  |
                 | (numactl bind 0)   |   | (numactl bind 1)   |   | (no numactl)       |
                 +--------------------+   +--------------------+   +--------------------+
```

*   **Request:** The Client/Frontend sends a single `/submit` request containing a list of `targets` (e.g., `["node1:0", "node1:1", "node2"]`).
*   **Host Processing:** The Host iterates through the targets. For each valid and available target, it:
    *   Generates a unique Task ID (e.g., 101, 102, 103).
    *   Creates a separate database record for that task instance, linking it to the target node/NUMA ID and potentially a common Batch ID.
    *   Dispatches the task instance to the appropriate Runner, including the specific `target_numa_node_id` if applicable.
*   **Response:** The Host responds with a list of the Task IDs successfully created and dispatched.

---

## 🙏 Acknowledgement

*   Gemini 2.5 pro: Basic implementation and initial README generation.
*   Claude 3.7 Sonnet: Refining the logo SVG code.