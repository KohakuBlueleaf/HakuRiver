# HakuRiver - Shared Container Cluster

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

![HakuRiver logo svg](image/logo.svg)

***THIS PROJECT IS EXPERIMENTAL, USE AT YOUR OWN RISK***

**HakuRiver** is a lightweight, self-hosted cluster manager designed for distributing command-line tasks across compute nodes. It primarily leverages **Docker** to manage reproducible task environments, allowing users to treat containers like portable "virtual environments". HakuRiver orchestrates the creation, packaging (via tarballs), distribution, and execution of these containerized environments across your nodes.

It provides resource allocation (CPU/memory limits), multi-node/NUMA task submission, and status tracking, making it ideal for research labs, small-to-medium teams, home labs, or development environments needing simple, reproducible distributed task execution without the overhead of complex HPC schedulers.

---

## 🤔 What HakuRiver Is (and Isn't)

| HakuRiver IS FOR...                                                                                                              | HakuRiver IS NOT FOR...                                                                                                                        |
| :------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------- |
| ✅ Managing command-line tasks/scripts across small clusters (typically < 10-20 nodes).                                         | ❌ Replacing feature-rich HPC schedulers (Slurm, PBS, LSF) on large-scale clusters.                                                          |
| ✅ **Executing tasks within reproducible Docker container environments.**                                                         | ❌ Orchestrating complex, multi-service applications (like Kubernetes or Docker Compose).                                            |
| ✅ **Interactive environment setup on the Host and packaging these environments as portable tarballs for distribution.**           | ❌ Automatically managing complex software dependencies *within* containers (user sets up the env via Host's shell).                    |
| ✅ **Conveniently submitting independent command-line tasks or batches of parallel tasks across nodes/NUMA zones.**             | ❌ Sophisticated task dependency management or complex workflow orchestration (Use Airflow, Prefect, Snakemake, Nextflow).                     |
| ✅ Personal, research lab, small team, or Home Lab usage needing a *simple* multi-node task management system.                     | ❌ Deploying or managing highly available, mission-critical production *services*.                                                                   |
| ✅ Providing a lightweight system with minimal maintenance overhead for distributed task execution in controlled environments. | ❌ High-security, multi-tenant environments requiring robust built-in authentication and authorization layers.                       |
| ✅ Using the included `hakurun` utility for local parameter sweeps *before* cluster submission.                              | ❌ Replacing `hakurun` itself with cluster submission – they serve different purposes (local execution vs distributed execution). |

---

## ✨ Features

*   **Managed Docker Environment Workflow:**
    *   Set up persistent base containers on the Host (`hakuriver.docker create-container`).
    *   Interact with/install software in Host containers (`hakuriver.docker-shell`).
    *   Commit and package environments into versioned tarballs (`hakuriver.docker create-tar`).
    *   Place tarballs in shared storage for Runners.
*   **Containerized Task Execution:** Tasks run inside specified Docker environments (`docker run --rm`).
*   **Automated Environment Sync:** Runners automatically check and sync the required container tarball version from shared storage before running a task.
*   **Systemd Fallback Execution:** Option to run tasks directly on the node using `systemd-run --scope` for system-level access or when Docker isn't needed.
*   **CPU/RAM Resource Allocation:** Jobs request CPU cores (as Docker `--cpus` or systemd `CPUQuota`) and memory limits (Docker `--memory` or systemd `MemoryMax`).
*   **NUMA Node Targeting (Systemd Fallback):** Optionally bind *systemd-run* tasks to specific NUMA nodes using `numactl`. (NUMA in Docker is TODO).
*   **Multi-Node/NUMA Task Submission:** Submit a single request to run the same command across multiple specified nodes or specific NUMA nodes (within Docker or via systemd).
*   **Persistent Task & Node Records:** Host maintains an SQLite DB of nodes (including detected NUMA topology) and tasks (status, target, resources, logs, container used).
*   **Node Health & Resource Awareness:** Basic heartbeat detects offline runners. Runners report overall CPU/Memory usage and NUMA topology.
*   **Web Dashboard (Experimental):** Vue.js frontend for visual monitoring, task submission (incl. multi-target and container selection), status checks, and killing tasks.
*   **Standalone Argument Spanning (`hakurun`):** Utility for local parameter sweeps before submitting to the cluster.

---

## 🚀 Quick Start Guide

### Prerequisites

*   Python >= 3.10
*   Access to a shared filesystem mounted on the Host and all Runner nodes.
*   **Host Node:** Docker Engine installed (for managing environments and creating tarballs).
*   **Runner Nodes:** **Docker Engine** installed (for executing containerized tasks). `numactl` is optional (only needed for the systemd/NUMA fallback). Passwordless `sudo` access might be required for the runner user depending on Docker setup (`docker` commands) or if using the systemd fallback (`systemd-run`, `systemctl`).
*   **Docker Engine**: You don't need any addition configuration for Docker beside just install them, but ensure the data-root and storage driver are set up correctly. HakuRiver uses the default Docker storage driver and data-root (`/var/lib/docker`), but you can change this in the Docker daemon configuration if needed. run `docker run hello-world` to verify Docker is working correctly.

### Steps

1.  **Install HakuRiver** (on Host, Runners, and Client machine):
    ```bash
    # Using pip (recommended)
    python -m pip install git+https://github.com/KohakuBlueleaf/HakuRiver.git
    # Or clone and install locally
    # git clone https://github.com/KohakuBlueleaf/HakuRiver.git
    # cd HakuRiver
    # pip install .
    ```
2.  **Configure HakuRiver** (on Host, Runners, and Client):
    *   Create the default config file:
        ```bash
        hakuriver.init config
        ```
    *   Edit the configuration file (`~/.hakuriver/config.toml`):
        ```bash
        vim ~/.hakuriver/config.toml
        ```
    *   **Crucial**: set `host_reachable_address` to the Host's IP/hostname accessible by Runners/Clients.
    *   **Crucial**: Set `runner_address` to the Runner's IP/hostname accessible by the Host.
    *   **Crucial**: Set `shared_dir` to the absolute path of your shared storage (e.g., `/mnt/shared/hakuriver`). Ensure this directory exists and is writable.
    *   Adjust other settings like ports, Docker defaults, etc., as needed. (See Configuration section below for details).

3.  **Start Host Server** (on the manager node):
    ```bash
    hakuriver.host
    # (Optional) Use a specific config: hakuriver.host --config /path/to/host.toml
    ```
    *   **For Systemd:**
        ```bash
        hakuriver.init service --host [--config /path/to/host.toml]
        sudo systemctl restart hakuriver-host.service
        sudo systemctl enable hakuriver-host.service
        ```

4.  **Start Runner Agents** (on each compute node):
    ```bash
    # Ensure Docker is running and the user can access it, or use passwordless sudo for Docker/Systemd commands.
    hakuriver.runner
    # (Optional) Use a specific config: hakuriver.runner --config /path/to/runner.toml
    ```
    *   **For Systemd:**
        ```bash
        hakuriver.init service --runner [--config /path/to/runner.toml]
        sudo systemctl restart hakuriver-runner.service
        sudo systemctl enable hakuriver-runner.service
        ```

5.  **(Optional) Prepare a Docker Environment** (on the Client/Host):
    *   Create a base container: `hakuriver.docker create-container python:3.11-slim my-py311-env`
    *   Install software: `hakuriver.docker-shell my-py311-env` (then `pip install ...`, `apt install ...`, `exit`)
    *   Package it: `hakuriver.docker create-tar my-py311-env` (creates tarball in shared storage)

6.  **Submit Your First Task** (from the Client machine):
    ```bash
    # Submit a simple echo command using the default Docker env to node1
    hakuriver.client --target node1 -- echo "Hello HakuRiver!"

    # Submit a Python script using your custom env on node2 with 2 cores
    # (Assuming myscript.py is in the shared dir)
    hakuriver.client --target node2 --cores 2 --container my-py311-env -- python /shared/myscript.py --input data.csv
    ```

7.  **Monitor and Manage**:
    *   List nodes: `hakuriver.client --list-nodes`
    *   Check task status: `hakuriver.client --status <task_id>`
    *   Kill a task: `hakuriver.client --kill <task_id>`
    *   (Optional) Access the Web UI (see Frontend section).

This guide provides the basic steps. Refer to the sections below for detailed explanations of configuration, Docker workflow, and advanced usage.

---

## 🏗️ Architecture Overview
![](image/README/HakuRiverArch.jpg)

*   **Host (`hakuriver.host`):** Central coordinator (FastAPI).
    *   Manages node registration (incl. NUMA topology).
    *   Manages **Docker environments**: Creates/starts/stops/deletes persistent Host containers, commits/creates versioned tarballs in shared storage.
    *   Provides **WebSocket terminal** access into managed Host containers.
    *   Tracks node status/resources via heartbeats.
    *   Stores node/task info in SQLite DB.
    *   Receives task submissions (incl. multi-target, Docker env selection).
    *   Validates targets, assigns tasks to Runners (providing Docker image tag or specifying systemd fallback).
*   **Runner (`hakuriver.runner`):** Agent on compute nodes (FastAPI).
    *   Requires **Docker Engine** installed.
    *   Registers with Host (reporting cores, RAM, NUMA info, URL).
    *   Sends periodic heartbeats (incl. CPU/Mem usage).
    *   **Executes tasks:**
        *   **Primary:** Checks for required container tarball in shared storage, syncs if needed (`docker load`), runs task via `docker run --rm` with specified image, resource limits, and mounts.
        *   **Fallback:** If no container specified, runs task via `sudo systemd-run --scope` with resource limits and optional `numactl` binding.
    *   Reports task status updates back to Host.
    *   **Requires passwordless `sudo`** for `systemctl` (if using systemd fallback) or potentially for `docker` commands depending on setup.
*   **Client (`hakuriver.client`, `hakuriver.docker`, `hakuriver.docker-shell`):** CLI tools.
    *   Communicate with Host to submit tasks (specifying command, args, resources, **Docker container name**, and **one or more targets**).
    *   Query task/node status, get health info.
    *   Kill/Pause/Resume tasks.
    *   Manage Host-side Docker containers and environment tarballs.
    *   Access interactive shell in Host containers.
*   **Frontend:** Optional web UI providing visual overview and interaction similar to the Client.
*   **Database:** Host uses SQLite via Peewee to store node inventory (incl. NUMA topology) and task details (incl. target NUMA ID, batch ID, container used).
*   **Storage:**
    *   **Shared (`shared_dir`):** Mounted on Host and all Runners. Essential for **container tarballs**, task output logs (`*.out`, `*.err`), and potentially shared scripts/data.
    *   **Local Temp (`local_temp_dir`):** Node-specific fast storage, path injected as `HAKURIVER_LOCAL_TEMP_DIR` env var for tasks.

The communication flow chart of HakuRiver:
![](image/README/HakuRiverFlow.jpg)

---

## 🐳 Docker-Based Environment Workflow

HakuRiver uses Docker containers as portable "virtual environments". Here's the typical workflow:

1.  **Prepare Base Environment (submitted by Client, execute by Host):**
    *   Use `hakuriver.docker create-container <image> <env_name>` to create a persistent container on the Host machine from a base image (e.g., `ubuntu:latest`, `python:3.11`).
    *   Use `hakuriver.docker start-container <env_name>` if it's stopped.
    *   Use `hakuriver.docker-shell <env_name>` to get an interactive shell inside the container. Install necessary packages (`apt install ...`, `pip install ...`), configure files, etc.
2.  **Package the Environment (submitted by Client, execute by Host):**
    *   Once the environment is set up, use `hakuriver.docker create-tar <env_name>`.
    *   This commits the container state to a new Docker image (`hakuriver/<env_name>:base`) and saves it as a timestamped `.tar` file in the configured `shared_dir/hakuriver-containers/`. Older tarballs for the same environment are automatically cleaned up.
3.  **Runner Synchronization (Automatic):**
    *   When a task is submitted targeting a Runner and specifying `--container <env_name>`, the Runner checks its local Docker images.
    *   If the required image (`hakuriver/<env_name>:base`) is missing or outdated compared to the latest tarball in `shared_dir`, the Runner automatically loads the latest `.tar` file (`docker load -i ...`).
4.  **Task Execution (on Runner):**
    *   The Runner executes the submitted command inside a *temporary* container created from the synced `hakuriver/<env_name>:base` image using `docker run --rm ...`.
    *   Resource limits (`--cpus`, `--memory`), the shared directory (`/shared`), local temp (`/local_temp`), and any extra mounts are applied.

This workflow ensures tasks run in consistent, pre-configured environments across all nodes without requiring manual setup on each Runner beyond installing the Docker engine.

---

## `hakurun`: Local Argument Spanning Utility

`hakurun` is a **local helper utility** for testing commands or Python scripts with multiple argument combinations *before* submitting them to the HakuRiver cluster. It does **not** interact with the cluster itself.

*   **Argument Spanning:**
    *   `span:{start..end}` -> Integers (e.g., `span:{1..3}` -> `1`, `2`, `3`)
    *   `span:[a,b,c]` -> List items (e.g., `span:[foo,bar]` -> `"foo"`, `"bar"`)
*   **Execution:** Runs the Cartesian product of all spanned arguments. Use `--parallel` to run combinations concurrently via local subprocesses.
*   **Targets:** Runs Python modules (`mymod`), functions (`mymod:myfunc`), or executables (`python script.py`, `my_executable`).

**Example (`demo_hakurun.py`):**

```python
# demo_hakurun.py
import sys, time, random, os
time.sleep(random.random() * 0.1)
print(f"Args: {sys.argv[1:]}, PID: {os.getpid()}")
```

```bash
# Runs 2 * 1 * 2 = 4 tasks locally and in parallel
hakurun --parallel python ./demo_hakurun.py span:{1..2} fixed_arg span:[input_a,input_b]
```

Use `hakurun` to generate commands you might later submit individually or as a batch using `hakuriver.client` to run *within* a specific Docker environment on the cluster.

---

## 🔧 Configuration - HakuRiver

*   Create a default config: `hakuriver.init config`. This creates `~/.hakuriver/config.toml`.
*   Review and edit the default config (`src/hakuriver/utils/default_config.toml` shows defaults).
*   Override with `--config /path/to/custom.toml` for any `hakuriver.*` command.
*   **CRITICAL SETTINGS TO REVIEW/EDIT:**
    *   `[network] host_reachable_address`: **Must** be the IP/hostname of the Host reachable by Runners and Clients.
    *   `[network] runner_address`: **Must** be the IP/hostname of the Runner reachable by Host.
    *   `[paths] shared_dir`: Absolute path to shared storage (must exist and be writable on Host and Runner nodes). **Crucial for logs and container tarballs.**
    *   `[paths] local_temp_dir`: Absolute path to local temp storage (must exist and be writable on Runner nodes). Injected into containers as `/local_temp`.
    *   `[paths] numactl_path`: Absolute path to `numactl` executable on Runner nodes (only needed for systemd fallback).
    *   `[docker] container_dir`: Subdirectory within `shared_dir` for container tarballs.
    *   `[docker] default_container_name`: Default environment name if `--container` isn't specified during task submission.
    *   `[docker] initial_base_image`: Public Docker image used to create the default tarball if it doesn't exist on Host start.
    *   `[docker] tasks_privileged`: Default setting for running containers with `--privileged`.
    *   `[docker] additional_mounts`: List of default "host:container" mounts for tasks.
    *   `[database] db_file`: Path for the Host's SQLite database. Ensure the directory exists.

---

## 💻 Usage - HakuRiver Cluster

This section details the core commands for setting up, managing environments, and running tasks.

### Initial Setup

Follow the **Quick Start Guide** above for installation, configuration, and starting the Host/Runners.

### Managing Docker Environments

HakuRiver allows you to manage Docker environments directly on the Host, package them, and distribute them via shared storage.

**Docker Management Command Reference:**

| Action                        | Command Example                                             | Notes                                                           |
| :---------------------------- | :---------------------------------------------------------- | :-------------------------------------------------------------- |
| List Host Containers          | `hakuriver.docker list-containers`                         | Shows persistent containers on the Host.                       |
| Create Host Container         | `hakuriver.docker create-container <image> <env_name>`      | Creates a container on Host from `<image>`.                     |
| Start Host Container          | `hakuriver.docker start-container <env_name>`              | Starts the container if stopped.                                |
| Stop Host Container           | `hakuriver.docker stop-container <env_name>`               | Stops the container.                                            |
| Interactive Shell             | `hakuriver.docker-shell <env_name>`                        | Opens interactive shell inside the Host container.              |
| Create/Update Tarball         | `hakuriver.docker create-tar <env_name>`                   | Commits container, creates/updates tarball in `shared_dir`.     |
| List Available Tarballs       | `hakuriver.docker list-tars`                               | Shows packaged environments in `shared_dir`.                  |
| Delete Host Container         | `hakuriver.docker delete-container <env_name>`             | Deletes the persistent container from Host (tarball remains). |

### Submitting and Managing Tasks

Use `hakuriver.client` to interact with the cluster.

**Example Task Submissions:**

*   **Run a script in your custom Python environment on node1:**
    ```bash
    hakuriver.client --target node1 --container my-py311-env -- python /shared/analyze_data.py --input data.csv
    ```
    *(Assumes `analyze_data.py` is accessible at `/shared/analyze_data.py` inside the container, which usually maps to your `shared_dir`)*

*   **Run a command using the default environment across multiple nodes:**
    ```bash
    hakuriver.client --target node1 --target node3 --cores 2 -- memory 512M -- my_processing_tool --verbose /shared/input_file
    ```
    *(Uses the `default_container_name` from config, allocates 2 cores and 512MB RAM per task)*

*   **Run a system command directly on node2 (no Docker):**
    ```bash
    hakuriver.client --target node2 --container NULL -- df -h /
    ```

*   **Run a systemd task bound to NUMA node 0 on node1:**
    ```bash
    hakuriver.client --target node1:0 --container NULL --cores 4 -- ./run_numa_benchmark.sh
    ```

**Task Management Command Reference:**

| Action                          | Command Example                                                               | Notes                                                             |
| :------------------------------ | :---------------------------------------------------------------------------- | :---------------------------------------------------------------- |
| List Nodes                      | `hakuriver.client --list-nodes`                                              | Shows status, cores, NUMA summary.                               |
| Node Health                     | `hakuriver.client --health [<node>]`                                         | Detailed stats for specific node or all nodes.                  |
| Submit Task                     | `hakuriver.client [--target <node[:n]>] [--container <env>] [--cores N] [--] CMD [ARGS...]` | Submits task(s). See examples above.                       |
| Check Status                    | `hakuriver.client --status <task_id>`                                        | Shows detailed status (incl. target, batch ID, container).     |
| Kill Task                       | `hakuriver.client --kill <task_id>`                                          | Requests termination (Docker/systemd).                          |
| Pause Task                      | `hakuriver.client pause <task_id>`                                           | Sends SIGSTOP / `docker pause`.                                 |
| Resume Task                     | `hakuriver.client resume <task_id>`                                          | Sends SIGCONT / `docker unpause`.                               |
| Submit + Wait                   | `hakuriver.client --wait ...`                                                 | Waits for submitted task(s) to finish.                          |
| Combine w/ `hakurun` (Many Jobs)| `hakurun hakuriver.client --container <env> -- python script.py span:{1..10}` | Submits 10 independent HakuRiver jobs.                          |
| Combine w/ `hakurun` (One Job) | `hakuriver.client --container <env> -- hakurun --parallel python proc.py span:{A..Z}` | Submits 1 HakuRiver job that runs `hakurun` internally. |

**`--target` Syntax:**

| Format             | Description                             | Execution Method Depends On `--container` |
| :----------------- | :-------------------------------------- | :---------------------------------------- |
| `my-node`        | Target the physical node `my-node`.   | Docker (default/specified) or systemd   |
| `my-node:0`      | Target NUMA node 0 on `my-node`.      | Docker (NUMA ignored) or systemd (NUMA 0) |
| `another-node:1` | Target NUMA node 1 on `another-node`. | Docker (NUMA ignored) or systemd (NUMA 1) |

---

## 🌐 Usage - Frontend Web UI (Experimental)

| Overview                                       | Node list and Task list                                                                       | Submit Task from Manager UI                    |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| ![1744643963836](image/README/1744643963836.png) | ![1744643981874](image/README/1744643981874.png) ![1744643997740](image/README/1744643997740.png) | ![1744644009190](image/README/1744644009190.png) |

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
    *   View node list, status, resources, and NUMA topology.
    *   View task list, details (incl. Batch ID, Target NUMA, Container).
    *   Submit new tasks using a form (allows **multi-target** selection and **Docker container** selection).
    *   Kill/Pause/Resume running tasks.
    *   View task stdout/stderr logs.

**Building (Production):**

1.  Build static files:
    ```bash
    npm run build
    ```
2.  Serve the contents of `frontend/dist` using any static web server (Nginx, Apache, etc.).
3.  **Important:** Configure your production web server to proxy API requests (e.g., requests to `/api/*`) to the actual running HakuRiver Host address and port, OR modify `src/services/api.js` to use the Host's absolute URL before building.

---

## 📝 Future Work / TODO

*   **Web UI Docker Management:** Add frontend components to interact with the Host's Docker management APIs (`hakuriver.docker` functionality).
*   **NUMA Awareness within Docker:** Implement mechanisms to pass NUMA binding preferences (`--cpuset-cpus`, `--cpuset-mems`) to `docker run` based on the `--target node:numa_id` syntax.
*   **GPU Resource Management:** Add support for requesting and allocating GPU resources (e.g., via `--gpus` flag in Docker).
*   **Basic Scheduling Strategies:** Explore other simple but useful options beyond simple "first fit" for node selection. Such as round-robin, least loaded, priority-based, etc.

## 🙏 Acknowledgement

*   Gemini 2.5 pro: Basic implementation and initial README generation.
*   Claude 3.7 Sonnet: Refining the logo SVG code.