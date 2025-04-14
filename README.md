# [WIP]HakuRiver - Mini Resource Orchestrator

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

![HakuRiver logo svg](image/logo.svg)

***THIS PROJECT IS WORK IN PROGRESS, USE AT YOUR OWN RISK***

A simple, multi-node resource management tool designed for distributing tasks across compute nodes, focusing on CPU core and System RAM allocation, leveraging **systemd** for execution and basic sandboxing.

HakuRiver is a self-hosted cluster manager ideal for small research clusters, development environments, or internal batch processing systems where full-featured HPC schedulers like Slurm might be overkill. It allows users to submit arbitrary commands, manage their execution based on available CPU cores and memory, monitor their status, and apply basic process isolation.

### HakuRiver is for:

* Managing command-line tasks/scripts across a small cluster (e.g., < 10 nodes).
* Development, testing, or small research environments needing a simpler alternative to full HPC schedulers.
* Running primarily CPU/Memory-bound applications where resource limits and optional isolation are beneficial.
* Internal tools where basic job submission, status checking, and termination are sufficient.

### HakuRiver is NOT for:

* Replacing feature-rich HPC schedulers (like Slurm, PBS) on large-scale clusters.
* Environments without systemd or where tasks cannot be launched via `systemd-run` with `sudo`.
* Complex resource management beyond CPU quotas and memory limits (e.g., GPU scheduling, license tracking).
* Sophisticated task dependency management or workflow orchestration (use tools like Airflow, Snakemake, Nextflow).
* Advanced scheduling policies (e.g., fair-share, preemption, complex priorities).
* High-security, multi-tenant environments requiring robust authentication and authorization built-in.

## ✨ Features

* **CPU/RAM Resource Allocation via systemd:** Allows jobs to request a specific number of CPU cores (enforced as a **CPU quota percentage** via `systemd-run`) and a **memory limit** (enforced via `systemd-run`).
* **Systemd-Based Task Execution:** Tasks are launched as transient systemd scope units (`systemd-run --scope`). This provides better resource accounting and lifecycle management compared to simple subprocesses.
* **Optional Sandboxing:** Supports basic sandboxing features provided by systemd, including network isolation (`PrivateNetwork=yes`) and process isolation (`PrivatePIDs=yes`), configurable per task.
* **Persistent Task and Node Records:** The host maintains a persistent record of compute nodes and submitted tasks, including their status, assigned node, resource requests, and output locations, facilitating tracking even after client disconnection.
* **Node Health Awareness:** Includes a basic heartbeat mechanism allowing the host to detect unresponsive runner nodes and appropriately mark tasks that were assigned to them as 'lost'. Runners also report basic CPU/Memory usage.
* **Standalone Argument Spanning Utility (`hakurun`):** Includes a convenient command-line utility, `hakurun`, for locally generating and running multiple variations of a command or Python script. It supports expanding arguments using range (`span:{start..end}`) or list (`span:[a,b]`) syntax, creating the Cartesian product of all combinations. Tasks can be executed sequentially or in parallel (`--parallel`) via subprocesses. This is ideal for simple parameter sweeps or testing variations before submitting larger workloads to the HakuRiver cluster.
  * **Benefit for Python Multiprocessing:** When `hakurun` is used to invoke a Python module or function (e.g., `hakurun my_module:my_func ...` or `hakurun my_module ...`), the child processes spawned (either by `hakurun` itself with `--parallel` or by the target script using `multiprocessing` or `ProcessPoolExecutor`) inherit `hakurun.run` as their entry point. This avoids common pitfalls associated with the `if __name__ == "__main__":` guard in the *target* script, preventing redundant module imports or re-initialization of global variables in spawned processes, leading to cleaner and more robust parallel Python execution.
* **Web-Based Dashboard (Experimental):** An optional Vue.js frontend provides a visual interface to monitor node status, view task lists, submit new tasks (including memory limits and sandboxing options), and kill running tasks.

## 🏗️ Architecture Overview

* **Host (`hakuriver.host`):** The central brain of the cluster. It listens for connections from Runners and Clients. The Host maintains an inventory of registered compute nodes and tracks the availability of their CPU cores and basic resource usage. When a user submits a task via the Client, the Host finds a suitable node (currently based on available cores), records the task details, and instructs the chosen Runner to execute it. It also receives status updates (like 'running', 'completed', 'failed', 'killed_oom') and heartbeats from Runners.
* **Runner (`hakuriver.runner`):** An agent running on each compute node intended to execute tasks. Upon starting, it registers itself, its total core count, and total RAM with the Host. It periodically sends heartbeats (including current CPU/Memory usage) to signal its availability. When instructed by the Host, the Runner uses `sudo systemd-run` to launch the requested command as a transient systemd scope unit, applying the specified **CPU quota**, **memory limit**, and optional **sandboxing** properties (`PrivateNetwork`, `PrivatePID`). It redirects output (stdout/stderr) to files on the shared storage (specified by the Host) and reports the final status (success/failure, exit code, OOM kill) back to the Host. **Requires passwordless `sudo` privileges for the user running the agent.**
* **Client (`hakuriver.client`):** The user's tool for interacting with the cluster. It communicates with the Host server to submit new tasks (specifying the command, arguments, environment variables, required cores, optional memory limit, and optional sandboxing flags), query the status of previously submitted tasks using their unique ID, request the termination of a running task, or get an overview of the registered compute nodes and their current state.
* **Storage:** HakuRiver assumes two types of storage are accessible to the cluster nodes:
  * **Shared Storage (`shared_dir`):** Accessible by the Host and all Runners at the *same path*. Used for scripts, common input data, and crucially, for storing the standard output and error logs generated by tasks. Paths are determined by the Host.
  * **Local Temporary Storage (`local_temp_dir`):** Fast, node-specific storage available on each Runner. Tasks can use this for intermediate files or scratch space during execution (accessible via the `HAKURIVER_LOCAL_TEMP_DIR` environment variable injected into the task). Data here is generally considered temporary.

## 🚀 Getting Started

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/KohakuBlueleaf/HakuRiver.git
   cd HakuRiver
   ```
2. Install the package (preferably in a virtual environment):

   ```bash
   # Installs hakuriver and its dependencies specified in pyproject.toml
   pip install .
   ```

   This will make the `hakurun`, `hakuriver.host`, `hakuriver.runner`, and `hakuriver.client` commands available in your environment.

### Usage - Hakurun

`hakurun` is a utility script included with HakuRiver designed for launching multiple variations of a command or Python script by automatically expanding specified arguments. This is particularly useful for running simple parameter sweeps or executing the same task with different inputs locally *before* submitting potentially many individual jobs to the HakuRiver cluster.

**Key Features:**

* **Argument Spanning:** Define ranges or lists for arguments, and `hakurun` will generate the Cartesian product of all combinations.
  * **Integer Range:** `span:{start..end}` expands to all integers from `start` to `end` (inclusive). Example: `span:{1..3}` becomes `1`, `2`, `3`.
  * **List:** `span:[item1, item2, ...]` expands to the provided list items. Example: `span:[alpha,beta]` becomes `"alpha"`, `"beta"`.
* **Parallel Execution:** Use the `--parallel` flag to run the generated task combinations concurrently as separate subprocesses.
* **Target Flexibility:** Can run Python modules (`my_module`), specific functions within modules (`my_module:my_function`), or general executable scripts/commands.

**Example:**

Consider the `demo_hakurun.py` script provided:

```python
# demo_hakurun.py
import sys
import time
import random

time.sleep(random.random() * 0.1)
print(sys.argv)
```

You can run this script with multiple combinations of arguments using `hakurun` with two different methods:

Module import:

```bash
# Command (runs 2 * 1 * 2 = 4 tasks in parallel)
hakurun --parallel demo_hakurun "span:{1..2}" "fixed_arg" "span:[input_a, input_b]"
```

General script/executable (with python):

```bash
hakurun --parallel python ./demo_hakurun.py "span:{1..2}" "fixed_arg" "span:[input_a, input_b]"
```

**Example Output (order may vary with `--parallel`):**

```
[HakuRun]-|xx:xx:xx|-INFO: Running 4 tasks in parallel via subprocess...
[HakuRun]-|xx:xx:xx|-INFO:   Task 1/4: python /path/to/demo_hakurun.py 1 fixed_arg input_a
[HakuRun]-|xx:xx:xx|-INFO:   Task 2/4: python /path/to/demo_hakurun.py 1 fixed_arg input_b
[HakuRun]-|xx:xx:xx|-INFO:   Task 3/4: python /path/to/demo_hakurun.py 2 fixed_arg input_a
[HakuRun]-|xx:xx:xx|-INFO:   Task 4/4: python /path/to/demo_hakurun.py 2 fixed_arg input_b
[HakuRun]-|xx:xx:xx|-INFO: Waiting for parallel tasks to complete...
['/path/to/demo_hakurun.py', '1', 'fixed_arg', 'input_a']
['/path/to/demo_hakurun.py', '2', 'fixed_arg', 'input_a']
['/path/to/demo_hakurun.py', '1', 'fixed_arg', 'input_b']
['/path/to/demo_hakurun.py', '2', 'fixed_arg', 'input_b']
[HakuRun]-|xx:xx:xx|-INFO: All parallel tasks finished successfully.
```

**Note:** `hakurun` executes these tasks locally on the machine where it's invoked. It does **not** interact with the HakuRiver host or runners and does not submit jobs to the cluster. It's a standalone helper utility for generating and running command variations.

**Hint:** When you want to submit multiple similar commands into HakuRiver, it is recommended to combine them into a single job using the `hakurun` utility. This allows you to treat a bunch of commands as a single HakuRiver task, which can be useful for tasks like web crawling or dataset preprocessing involving many small, similar operations.

### Configuration - Hakuriver

* A default configuration file is located at `src/hakuriver/utils/default_config.toml`.
* **Crucially, review and potentially edit these settings in your default or a custom config file:**
  * `[network] host_reachable_address`: Must be the IP or hostname of the Host server reachable by Runners and Clients.
  * `[paths] shared_dir`: Absolute path to shared storage (must exist and be accessible with the same path on all nodes).
  * `[paths] local_temp_dir`: Absolute path to local temp storage (must exist and be writable on runner nodes).
  * `[database] db_file`: Path for the host's SQLite database file. Ensure the directory exists.
* You can override the default configuration by providing a custom TOML file using the `--config` flag when running any `hakuriver.*` command.

### Usage - HakuRiver

**1. Initialize Database (Run once on the Host machine):**
The Host server attempts to initialize the database on startup. Ensure the directory specified in `database.db_file` exists and is writable by the user running the host.

**2. Start the Host Server (on the manager node):**

```bash
hakuriver.host
# Or with a custom config:
# hakuriver.host --config /path/to/host_config.toml
```

**3. Start the Runner Agent (on each compute node):**

```bash
# IMPORTANT: Run this command as a user who has NOPASSWD sudo access
# for systemd-run and systemctl commands. This is required for task
# execution, resource limiting, and killing.
# Example sudoers entry:
# your_user ALL=(ALL) NOPASSWD: /usr/bin/systemd-run, /usr/bin/systemctl

hakuriver.runner
# Or with a custom config:
# hakuriver.runner --config /path/to/runner_config.toml
```

**Important Considerations for `systemd-run` Execution:**

* **Sudo Requirement:** As noted above, the user running `hakuriver.runner` needs passwordless `sudo` access for `systemd-run` and `systemctl`.
* **Working Directory:** Tasks launched via `systemd-run` do *not* inherit the working directory of the `hakuriver.runner` process. They typically start in the home directory of the user specified (`--property=User=...`, which defaults to the user running the runner) or `/`. Your scripts should generally use absolute paths or rely on environment variables like `HAKURIVER_SHARED_DIR` and `HAKURIVER_LOCAL_TEMP_DIR`.
* **Environment:** While HakuRiver passes specified environment variables (`--env`) and injects its own (`HAKURIVER_*`), the overall environment might differ slightly from a direct shell execution due to systemd's handling.

**4. Use the Client:**

```bash
# List nodes
hakuriver.client --list-nodes

# Get health status for all nodes
hakuriver.client --health

# Get health for a specific node
hakuriver.client --health node-01.compute.local

# Submit a simple task requesting 1 core, 512MB RAM, and wait
hakuriver.client --cores 1 --memory 512M --wait -- python -c "import time; print('Hello'); time.sleep(5)"

# Submit a task with args, env vars, and network isolation
hakuriver.client --cores 4 --memory 2G --env MY_VAR=ABC --private-network -- /path/to/shared/my_job.sh --input data.txt

# Check task status
hakuriver.client --status <task_id>

# Kill a task
hakuriver.client --kill <task_id>

# Use a custom config for the client
hakuriver.client --config client.toml --list-nodes

# Combine multiple commands into one job using hakurun
hakuriver.client --cores 4 --memory 1G -- hakurun --parallel python -c "import sys; print(f'Arg: {sys.argv[1]}')" "span:{1..10}"

# Submit multiple similar commands as distinct HakuRiver jobs using hakurun + hakuriver.client
hakurun hakuriver.client --cores 1 --memory 256M -- python -c "import sys; print(f'Task {sys.argv[1]}')" "span:{A..D}"
```

### Usage - Frontend Web UI (Experimental)

| Overview | Node list and Task list | Submit Task from Manager UI |
| -|-|-|
|![1744643963836](image/README/1744643963836.png)| ![1744643981874](image/README/1744643981874.png) ![1744643997740](image/README/1744643997740.png) | ![1744644009190](image/README/1744644009190.png)|

HakuRiver includes an optional web-based dashboard built with Vue.js and Element Plus for visual monitoring and management.

**Prerequisites:**

1. **Node.js and npm (or yarn/pnpm):** You need Node.js installed to build and run the frontend development server. You can download it from [https://nodejs.org/](https://nodejs.org/). npm is usually included with Node.js.
2. **Running HakuRiver Host:** The frontend communicates with the HakuRiver Host API. Ensure the `hakuriver.host` server is running and accessible (by default at `http://127.0.0.1:8000` as configured in `vite.config.js` proxy).

**Setup:**

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   # or: yarn install / pnpm install
   ```

**Running in Development Mode:**

1. Start the Vite development server:
   ```bash
   npm run dev
   ```
2. Vite will typically start the server and print the local URL (e.g., `http://localhost:5173`). Open this URL in your web browser.
3. The development server is configured with a proxy (see `frontend/vite.config.js`). API requests made by the frontend (e.g., to `/api/nodes`) will be automatically forwarded to the HakuRiver Host server configured in the proxy target (default: `http://127.0.0.1:8000`). **Make sure your HakuRiver Host is running at this address.**
4. The "Submit Task" dialog in the UI now includes fields for specifying a **Memory Limit** (e.g., "512M", "4G") and checkboxes for **Sandboxing Options** (Isolate Network, Isolate Processes).

**Building for Production:**

1. To create a production-ready build (static HTML, JS, CSS files):
   ```bash
   npm run build
   ```
2. The optimized static files will be generated in the `frontend/dist` directory.
3. These static files can then be served by any web server (like Nginx, Apache, or even Python's `http.server`).
4. **Important:** When deploying the built frontend, you need to ensure it can correctly reach the HakuRiver Host API. The `src/services/api.js` file has a placeholder for the production URL (`http://your-production-hakuriver-host:8000`). You will need to:
   * Modify `src/services/api.js` before building to point to your actual host address, OR
   * Configure your deployment web server (e.g., Nginx) to proxy requests from the frontend's path (like `/api`) to the backend HakuRiver Host, similar to how the Vite dev server does it.

## Acknowledgement

* Gemini 2.5 pro: basic implementation and this README
* Claude 3.7 Sonnet: refine the code of logo.svg
