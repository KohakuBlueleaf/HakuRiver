# HakuRiver - Shared Container Cluster & VPS Tasks

[![en](https://img.shields.io/badge/lang-en-red.svg)](./README.md)
[![中文](https://img.shields.io/badge/lang-%E4%B8%AD%E6%96%87-green.svg)](./README.zh.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

![HakuRiver logo svg](image/logo.svg)

**HakuRiver** is a lightweight, self-hosted cluster manager designed for distributing command-line tasks and launching persistent interactive sessions (referred to as **VPS Tasks**) across compute nodes. It primarily leverages **Docker** to manage reproducible task environments, allowing users to treat containers like portable "virtual environments". HakuRiver orchestrates the creation, packaging (via tarballs), distribution, and execution of these containerized environments across your nodes.

It provides resource allocation (CPU/memory/GPU limits), multi-node/NUMA/GPU task submission, and status tracking, making it ideal for research labs, small-to-medium teams, home labs, or development environments needing simple, reproducible distributed task execution and on-demand interactive compute environments without the overhead of complex HPC schedulers.

## Introduction to HakuRiver

### Problem Statement

Researchers and small teams often face a challenging middle ground when working with a modest number of compute nodes (typically 3-8 machines). This creates an awkward situation:

- **Too many machines** to manage manually with SSH and shell scripts
- **Too few machines** to justify the overhead of complex HPC schedulers like Slurm
- **Unsuitable complexity** of container orchestration systems like Kubernetes for simple task distribution or single, long-running interactive sessions.

You have these powerful compute resources at your disposal, but no efficient way to utilize them as a unified computing resource without significant operational overhead.

### Core Concept: Your Nodes as One Big Computer

HakuRiver addresses this problem by letting you treat your small cluster as a single powerful computer, with these key design principles:

- **Lightweight Resource Management**: Distribute command-line tasks and interactive VPS sessions across your nodes with minimal setup
- **Environment Consistency**: Use Docker containers as portable virtual environments, not as complex application deployments
- **Seamless Synchronization**: Automatically distribute container environments to runners without manual setup on each node
- **Familiar Workflow**: Submit tasks through a simple interface that feels like running a command or launching an environment on your local machine

> Docker in HakuRiver functions as a virtual environment that can be dynamically adjusted and automatically synchronized. You can run dozens of tasks or launch multiple interactive sessions using the same container environment, but execute them on completely different nodes.

### How It Works

1.  **Environment Management**: Create and customize Docker containers on the Host node using `hakuriver.docker` commands and interactive shells (`hakuriver.docker-shell`).
2.  **Package & Distribute**: The environment is packaged as a tarball using `hakuriver.docker create-tar` and stored in shared storage.
3.  **Automatic Synchronization**: Runner nodes automatically fetch the required environment from shared storage before executing tasks.
4.  **Parallel/Interactive Execution**: Submit single commands, batches of parallel tasks, or launch persistent VPS tasks to run across multiple nodes, with each task isolated in its own container instance (or executed directly via systemd for command tasks).

This approach aligns with the philosophy that:

> For a small local cluster, you should prioritize solutions that are "lightweight, simple, and just sufficient." You shouldn't need to package every command into a complex Dockerfile - Docker's purpose here is environment management and synchronization.

HakuRiver is built on the assumption that in small local clusters:

-   Nodes can easily establish network communication
-   Shared storage is readily available
-   Doesn't require authentication or the complexity can be minimized
-   High availability and fault tolerance are less critical at this scale

By focusing on these practical realities of small-scale computing, HakuRiver provides a "just right" solution for multi-node task execution and interactive environments without the administrative burden of enterprise-grade systems.

---

## 🤔 What HakuRiver Is (and Isn't)

| HakuRiver IS FOR...                                                                                                            | HakuRiver IS NOT FOR...                                                                                                    |
| :----------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------- |
| ✅ Managing command-line tasks/scripts and persistent VPS sessions across small clusters (typically < 10-20 nodes).          | ❌ Replacing feature-rich HPC schedulers (Slurm, PBS, LSF) on large-scale clusters.                                        |
| ✅**Executing tasks & VPS sessions within reproducible Docker container environments (managed by HakuRiver).**               | ❌ Orchestrating complex, multi-service applications (like Kubernetes or Docker Compose).                                  |
| ✅**Interactive environment setup on the Host and packaging these environments as portable tarballs for distribution.**  | ❌ Automatically managing complex software dependencies*within* containers (user sets up the env via Host's shell).      |
| ✅**Conveniently submitting independent command-line tasks, batches of parallel tasks, or single-instance VPS sessions across nodes/NUMA zones/GPUs.** | ❌ Sophisticated task dependency management or complex workflow orchestration (Use Airflow, Prefect, Snakemake, Nextflow). |
| ✅ Providing on-demand interactive compute environments with SSH access (VPS tasks).                                         | ❌ Providing highly available, load-balanced production*services* accessible directly by external users.                     |
| ✅ Personal, research lab, small team, or Home Lab usage needing a*simple* multi-node task/VPS management system.           | ❌ Deploying or managing highly available, mission-critical production*services*.                                        |
| ✅ Providing a lightweight system with minimal maintenance overhead for distributed task execution in controlled environments. | ❌ High-security, multi-tenant environments requiring robust built-in authentication and authorization layers.             |

---

## ✨ Features

*   **Managed Docker Environment Workflow:**
    *   Set up persistent base containers on the Host (`hakuriver.docker create-container`).
    *   Interact with/install software in Host containers (`hakuriver.docker-shell`).
    *   Commit and package environments into versioned tarballs (`hakuriver.docker create-tar`).
*   **Containerized Task Execution:** Command tasks run inside specified Docker environments (managed by HakuRiver).
*   **VPS Tasks with SSH Access:** Launch persistent Docker containers configured with an SSH daemon for interactive sessions. Provide your public key for root access.
*   **SSH Proxy:** Securely connect to your VPS tasks via SSH through the Host server as a relay, without needing direct network access to each Runner node's dynamic SSH port.
*   **Automated Environment Sync:** Runners automatically check and sync the required container tarball version from shared storage before running a task.
*   **Systemd Fallback Execution:** Option (`--container NULL`) for *command tasks* to run directly on the node using the system's service manager (`systemd-run --scope`) for system-level access or when Docker isn't needed.
*   **CPU/RAM Resource Allocation:** Jobs request CPU cores (`--cores`) and memory limits (`--memory`) for both Docker and Systemd tasks, and VPS tasks.
*   **NUMA Node Targeting:** Optionally bind tasks to specific NUMA nodes (`--target node:numa_id`). *Command tasks* support multiple NUMA targets; *VPS tasks* target a single node or NUMA node.
*   **GPU Resource Allocation:** Request specific GPU devices (`--target node::gpu_id1,gpu_id2...`) on target nodes for Docker tasks and VPS tasks. Runners report available GPUs via heartbeats. *Command tasks* support multi-GPU targets; *VPS tasks* target a single node's GPUs.
*   **Multi-Node/NUMA/GPU Task Submission:** Submit a single request (`hakuriver.task submit`) to run the same command across multiple specified nodes, specific NUMA nodes, or specific GPU devices.
*   **Persistent Task & Node Records:** Host maintains an SQLite DB of nodes (incl. detected NUMA topology and GPU info) and tasks (status, type, target, resources, logs, container used, SSH port for VPS).
*   **Node Health & Resource Awareness:** Basic heartbeat detects offline runners. Runners report overall CPU/Memory usage, NUMA topology, and GPU details.
*   **Web Dashboard:** Vue.js frontend for visual monitoring, task submission (incl. multi-target and container/GPU selection), status checks, and killing/pausing/resuming tasks. Includes web-based terminal access to Host containers and log viewing modals. Dedicated views for Nodes, GPUs, and **VPS Tasks**.
*   **Task Control:** Pause and Resume running tasks (`hakuriver.task command <task_id> pause/resume`, `hakuriver.vps command <task_id> pause/resume`, or via Web UI).
*   **Standalone Argument Spanning (`hakurun`):** Utility for local parameter sweeps before submitting to the cluster.

---

## 🚀 Quick Start Guide

### Prerequisites

*   Python >= 3.10
*   Access to a shared filesystem mounted on the Host and all Runner nodes.
*   **Host Node:** Docker Engine installed (for managing environments and creating tarballs).
*   **Runner Nodes:** **Docker Engine** installed (for executing containerized tasks and VPS). `numactl` is optional (only needed for the systemd/NUMA fallback for command tasks). `pynvml` and NVIDIA drivers are optional (only needed for GPU reporting/allocation). Passwordless `sudo` access might be required for the runner user depending on Docker setup (`docker` commands) or if using the systemd fallback (`systemd-run`, `systemctl`).
*   **Client Machines:** SSH client installed (`ssh` command).
*   **Docker Engine**: You don't need any addition configuration for Docker beside just install them, but ensure the data-root and storage driver are set up correctly. HakuRiver uses the default Docker storage driver and data-root (`/var/lib/docker`), but you can change this in the Docker daemon configuration if needed. run `docker run hello-world` to verify Docker is working correctly.

### Steps

1.  **Install HakuRiver** (on Host, all Runner nodes, and Client machines):

    ```bash
    # Using pip (recommended)
    python -m pip install hakuriver
    # To include GPU monitoring support on Runners (requires pynvml & nvidia drivers)
    # python -m pip install "hakuriver[gpu]"

    # Or install from source (latest version)
    python -m pip install git+https://github.com/KohakuBlueleaf/HakuRiver.git
    # For GPU support from source
    # python -m pip install "git+https://github.com/KohakuBlueleaf/HakuRiver.git#egg=hakuriver[gpu]"

    # Or clone and install locally
    # git clone https://github.com/KohakuBlueleaf/HakuRiver.git
    # cd HakuRiver
    # pip install .
    # For GPU support locally
    # pip install ".[gpu]"
    ```
2.  **Configure HakuRiver** (on Host, all Runners, and Client machines):

    *   Create the default config file:
        ```bash
        hakuriver.init config
        ```
    *   Edit the configuration file (`~/.hakuriver/config.toml`):
        ```bash
        vim ~/.hakuriver/config.toml
        ```
    *   **Crucial**: set `host_reachable_address` to the Host's IP/hostname accessible by Runners/Clients.
    *   **Crucial**: Set `runner_address` to the Runner's IP/hostname accessible by the Host (must be unique per Runner).
    *   **Crucial**: Set `shared_dir` to the absolute path of your shared storage (e.g., `/mnt/shared/hakuriver`). Ensure this directory exists and is writable by the user running HakuRiver components.
    *   **Crucial**: Note the `host_ssh_proxy_port` (default 8002) in the `[network]` section. This port must be accessible on the Host by your client machines for `hakuriver.ssh` to work.
    *   Adjust other settings like other ports, Docker defaults, `numactl_path`, `local_temp_dir`, etc., as needed. (See Configuration section below for details).
3.  **Start Host Server** (on the manager node):

    ```bash
    hakuriver.host
    # (Optional) Use a specific config: hakuriver.host --config /path/to/host.toml
    ```

    *   **For Systemd:**
        ```bash
        hakuriver.init service --host [--config /path/to/host.toml]
        sudo systemctl daemon-reload # Needed after creating/updating service file
        sudo systemctl restart hakuriver-host.service
        sudo systemctl enable hakuriver-host.service
        ```
4.  **Start Runner Agents** (on each compute node):

    ```bash
    # Ensure Docker is running and the user can access it, or use passwordless sudo for Docker/Systemd commands.
    # Ensure pynvml is installed and drivers are loaded if using GPUs.
    hakuriver.runner
    # (Optional) Use a specific config: hakuriver.runner --config /path/to/runner.toml
    ```

    *   **For Systemd:**
        ```bash
        hakuriver.init service --runner [--config /path/to/runner.toml]
        sudo systemctl daemon-reload # Needed after creating/updating service file
        sudo systemctl restart hakuriver-runner.service
        sudo systemctl enable hakuriver-runner.service
        ```
5.  **(Optional) Prepare a Docker Environment** (on the Client/Host):

    *   Create a base container on the Host: `hakuriver.docker create-container python:3.12-slim my-py312-env`
    *   Install software interactively: `hakuriver.docker-shell my-py312-env` (then `pip install ...`, `apt install ...`, `exit`)
    *   Package it into a tarball: `hakuriver.docker create-tar my-py312-env` (creates tarball in `shared_dir`)
6.  **Submit Your First Task** (from the Client machine):

    *   **Submit a standard command task** (using `hakuriver.task`):
        ```bash
        # Submit a simple echo command using the default Docker env to node1
        hakuriver.task submit --target node1 -- echo "Hello HakuRiver!"

        # Submit a Python script using your custom env on node2 with 2 cores
        # (Assuming myscript.py is in the shared dir, accessible via /shared)
        hakuriver.task submit --target node2 --cores 2 --container my-py312-env -- python /shared/myscript.py --input /shared/data.csv

        # Submit a GPU command task to node3 using GPU 0 and 1
        hakuriver.task submit --target node3::0,1 --container my-cuda-env -- python /shared/train_gpu_model.py

        # Submit a system command directly on node4 (no Docker)
        hakuriver.task submit --target node4 --container NULL -- df -h /
        ```
        Note the `--` separator before your command and arguments for `hakuriver.task submit`.

    *   **Submit a VPS task** (using `hakuriver.vps`):
        ```bash
        # Launch a VPS on node1 using the default container, 1 core, and your public key
        # (Assumes ~/.ssh/id_rsa.pub or ~/.ssh/id_ed25519.pub exists by default)
        hakuriver.vps submit --target node1 --cores 1

        # Launch a VPS on node2 using a specific container and public key file
        hakuriver.vps submit --target node2 --container my-dev-env --public-key-file ~/.ssh/other_key.pub --cores 4 --memory 8G

        # Launch a VPS using GPU 0 on node3 with auto-selected core/memory (cores 0 = auto)
        hakuriver.vps submit --target node3::0 --container my-cuda-env --cores 0 --public-key-file ~/.ssh/gpu_key.pub
        ```
7.  **Monitor and Manage**:

    *   List nodes: `hakuriver.client nodes`
    *   Check task status (any task type): `hakuriver.client status <task_id>`
    *   Kill a task (any task type): `hakuriver.client kill <task_id>`
    *   Pause/Resume a task (any task type): `hakuriver.client command <task_id> pause/resume`
    *   List active VPS tasks: `hakuriver.vps status`
    *   Connect to a running VPS task via SSH: `hakuriver.ssh <vps_task_id>`
    *   (Optional) Access the Web UI (see Frontend section).

This guide provides the basic steps. Refer to the sections below for detailed explanations of configuration, Docker workflow, and advanced usage.

---

## 🏗️ Architecture Overview

![](image/README/HakuRiverArch.jpg)

*   **Host (`hakuriver.host`):** Central coordinator (FastAPI).
    *   Manages node registration (incl. NUMA topology, GPU info).
    *   Manages **Docker environments** on itself: Creates/starts/stops/deletes persistent Host containers, commits/creates versioned tarballs in shared storage.
    *   Provides **WebSocket terminal** access into managed Host containers.
    *   Tracks node status/resources via heartbeats.
    *   Stores node/task info in SQLite DB.
    *   Receives task submissions (incl. multi-target, container/GPU selection).
    *   Validates targets, assigns tasks to Runners (providing Docker image tag or specifying systemd fallback).
    *   Runs the **Host-side SSH Proxy server** to forward connections for VPS tasks.
*   **Runner (`hakuriver.runner`):** Agent on compute nodes (FastAPI).
    *   Requires **Docker Engine** installed. `systemd` and `numactl` are optional dependencies for systemd fallback. `pynvml` is optional for GPU monitoring.
    *   Registers with Host (reporting cores, RAM, NUMA info, GPU info, URL).
    *   Sends periodic heartbeats (incl. CPU/Mem/GPU usage, Temps).
    *   **Executes tasks:**
        *   **Primary (Docker):** Checks for required container tarball in shared storage, syncs if needed (`docker load`), runs task via `docker run --rm` (for command tasks) or persistent `docker run -d --restart unless-stopped` (for VPS tasks) with specified image, resource limits (`--cpus`, `--memory`, `--gpus`), and mounts. For VPS tasks, configures SSH and maps a random host port to container port 22, reporting the host port back to the Host.
        *   **Fallback (Systemd):** If `--container NULL` specified for *command tasks*, runs via `sudo systemd-run --scope` with resource limits (`CPUQuota`, `MemoryMax`) and optional `numactl` binding (`--target node:numa_id`).
    *   Reports task status updates back to Host.
    *   Handles kill/pause/resume signals from Host (translating to `docker kill/pause/unpause` or `systemctl stop/kill`).
    *   **Requires passwordless `sudo`** for `systemctl` (if using systemd fallback) or potentially for `docker` commands depending on setup.
*   **Client (`hakuriver.client`, `hakuriver.task`, `hakuriver.vps`, `hakuriver.docker`, `hakuriver.docker-shell`, `hakuriver.ssh`):** CLI tools.
    *   `hakuriver.task submit`: Submits command-line tasks.
    *   `hakuriver.vps submit`: Submits VPS tasks (requiring public key and Docker).
    *   `hakuriver.client status/kill/command`: Manage any task by ID.
    *   `hakuriver.client nodes/health`: Query cluster info.
    *   `hakuriver.docker`: Manage Host-side Docker environments.
    *   `hakuriver.docker-shell`: Access interactive shell in Host containers via WebSocket.
    *   `hakuriver.ssh <task_id>`: Connects to a *running VPS task*'s SSH port via a local client proxy that tunnels through the Host's SSH proxy server.
*   **Frontend:** Optional web UI providing visual overview and interaction similar to the Client, including dedicated views for Node, GPU, and VPS tasks, and advanced task submission forms.
*   **Database:** Host uses SQLite via Peewee to store node inventory (incl. NUMA topology, GPU info) and task details (incl. task type, target NUMA ID, required GPUs, batch ID, container used, SSH port).
*   **Storage:**
    *   **Shared (`shared_dir`):** Mounted on Host and all Runners. Essential for **container tarballs**, task output logs (`*.out`, `*.err`), and potentially shared scripts/data (mounted as `/shared` in Docker tasks).
    *   **Local Temp (`local_temp_dir`):** Node-specific fast storage, path injected as `HAKURIVER_LOCAL_TEMP_DIR` env var for tasks (mounted as `/local_temp` in Docker tasks).

The communication flow chart of HakuRiver (Note: The diagram below illustrates the *core* flow, but the new SSH Proxy flow is separate and involves SSH client -> **Client Proxy** (local) -> **Host Proxy** (Host) -> Runner (via VPS container's mapped port)).

![](image/README/HakuRiverFlow.jpg)

---

## 🐳 Docker-Based Environment Workflow

HakuRiver uses Docker containers as portable "virtual environments" for **both command tasks and VPS tasks**. Here's the typical workflow, triggered by `hakuriver.docker` commands on the Client (which communicate with the Host) or automatically by the Runner:

1.  **Prepare Base Environment (executed by Host):**
    *   Use `hakuriver.docker create-container <image> <env_name>` to create a persistent container on the Host machine from a base image (e.g., `ubuntu:latest`, `python:3.11`).
    *   Use `hakuriver.docker start-container <env_name>` if it's stopped.
    *   Use `hakuriver.docker-shell <env_name>` to get an interactive shell inside the container. Install necessary packages (`apt install ...`, `pip install ...`), configure files, etc. For VPS tasks, ensure an SSH server is installed and configured (e.g., openssh-server).
2.  **Package the Environment (executed by Host):**
    *   Once the environment is set up, use `hakuriver.docker create-tar <env_name>`.
    *   This commits the container state to a new Docker image (`hakuriver/<env_name>:base`) and saves it as a timestamped `.tar` file in the configured `shared_dir/hakuriver-containers/`. Older tarballs for the same environment are automatically cleaned up.
3.  **Runner Synchronization (Automatic):**
    *   When a task is submitted targeting a Runner and specifying `--container <env_name>`, the Runner checks its local Docker images.
    *   If the required image (`hakuriver/<env_name>:base`) is missing or outdated compared to the latest tarball in `shared_dir`, the Runner automatically loads the latest `.tar` file into its Docker registry.
4.  **Task Execution (on Runner):**
    *   **Command Tasks:** The Runner executes the submitted command inside a *temporary* container created from the synced `hakuriver/<env_name>:base` image using `docker run --rm ...`. Resource limits and mounts are applied.
    *   **VPS Tasks:** The Runner launches a *persistent* container (`docker run -d --restart unless-stopped ...`) from the synced `hakuriver/<env_name>:base` image. It configures the container for SSH access (injecting the public key, starting `sshd`) and maps a random host port to container port 22. Resource limits and mounts are applied. The assigned host port is reported back to the Host database.

This workflow ensures tasks run in consistent, pre-configured environments across all nodes without requiring manual setup on each Runner beyond installing the Docker engine and relevant drivers (like for GPUs) and ensuring required directories exist.

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
# Print arguments received from hakurun (sys.argv[0] is the script name)
print(f"Args: {sys.argv[1:]}, PID: {os.getpid()}")
```

```bash
# Runs 2 * 1 * 2 = 4 tasks locally and in parallel
hakurun --parallel python ./demo_hakurun.py span:{1..2} fixed_arg span:[input_a,input_b]
```

Use `hakurun` to generate commands you might later submit individually or as a batch using `hakuriver.task submit` to run *within* a specific Docker environment on the cluster.

---

## 🔧 Configuration - HakuRiver

*   Create a default config: `hakuriver.init config`. This creates `~/.hakuriver/config.toml`.
*   Review and edit the default config (`src/hakuriver/utils/default_config.toml` shows defaults).
*   Override with `--config /path/to/custom.toml` for any `hakuriver.*` command.
*   **CRITICAL SETTINGS TO REVIEW/EDIT:**
    *   `[network] host_reachable_address`: **Must** be the IP/hostname of the Host reachable by Runners and Clients.
    *   `[network] runner_address`: **Must** be the IP/hostname of the Runner reachable by Host. (Needs to be unique per Runner).
    *   `[network] host_ssh_proxy_port`: The port the Host will listen on for incoming SSH proxy connections from `hakuriver.ssh`. Clients need to reach this port. (Default: 8002)
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

## 💻 Usage - HakuRiver Cluster (CLI)

This section details the core commands for setting up, managing environments, and running tasks using the command-line interface.

### Initial Setup

Follow the **Quick Start Guide** above for installation, configuration, and starting the Host/Runners.

### Managing Docker Environments (on Host)

HakuRiver allows you to manage Docker environments directly on the Host, package them, and distribute them via shared storage using the `hakuriver.docker` and `hakuriver.docker-shell` commands.

**Docker Management Command Reference:**

| Action                  | Command Example                                          | Notes                                                         |
| :---------------------- | :------------------------------------------------------- | :------------------------------------------------------------ |
| List Host Containers    | `hakuriver.docker list-containers`                     | Shows persistent containers on the Host.                      |
| Create Host Container   | `hakuriver.docker create-container <image> <env_name>` | Creates a container on Host from `<image>`.                 |
| Start Host Container    | `hakuriver.docker start-container <env_name>`          | Starts the container if stopped.                              |
| Stop Host Container     | `hakuriver.docker stop-container <env_name>`           | Stops the container.                                          |
| Interactive Shell       | `hakuriver.docker-shell <env_name>`                    | Opens interactive shell inside the Host container (WebSocket).            |
| Create/Update Tarball   | `hakuriver.docker create-tar <env_name>`               | Commits container state, creates/updates tarball in `shared_dir`. |
| List Available Tarballs | `hakuriver.docker list-tars`                           | Shows packaged environments in `shared_dir`.                |
| Delete Host Container   | `hakuriver.docker delete-container <env_name>`         | Deletes the persistent container from Host (tarball remains). |

### Submitting and Managing Command Tasks

Use `hakuriver.task submit` to launch standard command-line tasks. Use `hakuriver.client` for general task status and control.

**`hakuriver.task submit` Options:**

| Option                          | Description                                                                                                                                                                                                                                                                                                                                            |
| :------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--target <node[:n][::g]>`    | **Required.** Specifies target(s). Repeat for multiple targets.<br>`node`: hostname.<br>`:n`: optional NUMA node ID.<br>`::g`: optional comma-separated GPU ID(s) (e.g., `::0` or `::0,1,3`). Multiple `--target` options create multiple tasks in a batch.                                                                                 |
| `--cores N`                   | Number of CPU cores required per task instance (Default: 1).                                                                                                                                                                                                                                                    |
| `--memory SIZE`               | Memory limit per task instance (e.g.,`512M`, `4G`). Uses 1000-based units (K, M, G). Optional.                                                                                                                                                                            |
| `--env KEY=VALUE`             | Set environment variable in task environment (repeatable).                                                                                                                                                                                                          |
| `--container NAME`            | HakuRiver container environment name. Use `NULL` for Systemd fallback (no Docker). Defaults to host config (`[docker] default_container_name`).                                                                                                                                                       |
| `--privileged`                | Run Docker container with `--privileged` (overrides default, use with caution).                                                                                                                                                                                   |
| `--mount HOST_PATH:CONT_PATH` | Additional host directory to mount into Docker task container (repeatable, overrides default `[docker] additional_mounts`).                                                                                                                                                                      |
| `--wait`                      | Wait for the submitted task(s) to complete before exiting.                                                                                                                                                                                                          |
| `--poll-interval SEC`         | Interval in seconds for status checks when using `--wait` (Default: 1).                                                                                                                                                                                                        |
| `-- COMMAND ARGS...`          | **Required.** Separator (`--`) followed by the command and its arguments to execute.                                                                                                                                                                                                     |

**Example Command Task Submissions:**

*   Run a script in your custom Python environment on node1:
    ```bash
    hakuriver.task submit --target node1 --container my-py311-env -- python /shared/analyze_data.py --input data.csv
    ```
    *(Assumes `analyze_data.py` is accessible at `/shared/analyze_data.py` inside the container, which usually maps to your `shared_dir`)*
*   Run a command using the default environment across multiple nodes:
    ```bash
    hakuriver.task submit --target node1 --target node3 --cores 2 --memory 512M -- my_processing_tool --verbose /shared/input_file
    ```
    *(Uses the `default_container_name` from config, allocates 2 cores and 512MB RAM per task instance)*
*   Run a command directly on node2 (Systemd fallback, no Docker):
    ```bash
    hakuriver.task submit --target node2 --container NULL -- df -h /
    ```
*   Run a Systemd task bound to NUMA node 0 on node1:
    ```bash
    hakuriver.task submit --target node1:0 --container NULL --cores 4 -- ./run_numa_benchmark.sh
    ```
*   Run a GPU command task on node3 using devices 0 and 1:
    ```bash
    hakuriver.task submit --target node3::0,1 --container my-cuda-env -- python /shared/train_gpu_model.py
    ```

### Submitting and Managing VPS Tasks

Use `hakuriver.vps submit` to launch persistent VPS tasks. Use `hakuriver.vps status` to list active VPS tasks and their SSH ports. Use `hakuriver.ssh` to connect to a VPS task. Use `hakuriver.client` for general task status and control (kill, pause, resume).

**`hakuriver.vps submit` Options:**

| Option                              | Description                                                                                                                                                                                                                                                           |
| :---------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--target <node[:n][::g]>`        | Specifies a **single** target node, NUMA node, or GPU set. If omitted, the Host will auto-select a suitable node based on resource requirements. Requires Docker.                                                                                                    |
| `--public-key-string <KEY_STRING>`  | Provide SSH public key directly. Mutually exclusive with `--public-key-file`.                                                                                                                                                                                         |
| `--public-key-file <PATH>`          | Path to SSH public key file (e.g., ~/.ssh/id_rsa.pub). If neither `--public-key-string` nor `--public-key-file` is used, defaults to `~/.ssh/id_rsa.pub` or `~/.ssh/id_ed25519.pub`.                                                                                |
| `--cores N`                       | Number of CPU cores required for the VPS (Default: 0 for auto-select).                                                                                                                                                                                                |
| `--memory SIZE`                   | Memory limit for the VPS (e.g.,`512M`, `4G`). Uses 1000-based units (K, M, G). Optional.                                                                                                                                                                               |
| `--container NAME`                | HakuRiver container environment name. Defaults to host config. **VPS tasks require a Docker container environment (cannot use NULL).**                                                                                                                            |
| `--privileged`                    | Run Docker container with `--privileged` (overrides default, use with caution).                                                                                                                                                                                       |
| `--mount HOST_PATH:CONT_PATH`     | Additional host directory to mount into the container (repeatable, overrides default).                                                                                                                                                                                |

**Example VPS Task Submissions:**

*   Launch a VPS on an auto-selected node using the default container and your default public key:
    ```bash
    hakuriver.vps submit --cores 2 --memory 4G
    ```
*   Launch a VPS on node2 binding to NUMA node 1:
    ```bash
    hakuriver.vps submit --target node2:1 --cores 8 --container my-ubuntu-env --public-key-file ~/.ssh/my_custom.pub
    ```
*   Launch a VPS on node3 using GPUs 0 and 1:
    ```bash
    hakuriver.vps submit --target node3::0,1 --container my-gpu-env --cores 0 --public-key-string "ssh-rsa AAAA..."
    ```

**Connecting to a VPS Task:**

Once a VPS task is running, use its Task ID to connect via SSH:

```bash
hakuriver.ssh <vps_task_id>
# Example: hakuriver.ssh 7323718749301768192
```

This command starts a local proxy listener and initiates an SSH connection through the Host's SSH proxy server to the correct Runner and the dynamically assigned SSH port for that task. The default user inside the container is `root`.

### General Task Management & Info (for any task type)

Use `hakuriver.client` for listing nodes/health and for basic status/control actions when you know the Task ID.

**`hakuriver.client` Command Reference:**

| Action                            | Command Example                                     | Notes                                                            |
| :-------------------------------- | :-------------------------------------------------- | :--------------------------------------------------------------- |
| List Nodes                        | `hakuriver.client nodes`                            | Shows status, cores, NUMA, GPU summary.                          |
| Node Health                       | `hakuriver.client health [<node>]`                  | Detailed stats for specific node or all nodes (incl. GPU).       |
| Check Status                      | `hakuriver.client status <task_id>`                 | Shows detailed status (incl. type, target, batch ID, container, GPUs, SSH port). |
| Kill Task                         | `hakuriver.client kill <task_id>`                   | Requests termination (Docker/systemd).                           |
| Pause Task                        | `hakuriver.client command <task_id> pause`          | Requests pause (Docker/systemd). Requires runner support.        |
| Resume Task                       | `hakuriver.client command <task_id> resume`         | Requests resume (Docker/systemd). Requires runner support.       |
| List Active VPS Tasks             | `hakuriver.vps status`                              | Lists tasks of type 'vps' that are not completed/failed/killed. |

---

## 🌐 Usage - Frontend Web UI

HakuRiver includes an optional web dashboard that provides a graphical interface for monitoring, submitting, and managing tasks, including dedicated views for GPU status and VPS tasks.

### Homepage Overview

<p align="center">
  <img src="image/README/1745625487479.png" alt="HakuRiver Dashboard Homepage" width="700">
</p>
<p align="center">The main dashboard provides an overview of cluster status and resource usage, including CPU and Memory.</p>

<br>

### Nodes View

<p align="center">
  <img src="image/README/1745625516131.png" alt="HakuRiver Nodes List" width="700">
</p>
<p align="center">View a list of registered nodes with their status, resources, allocated tasks, NUMA topology, and GPU count.</p>

<br>

### GPU View

<p align="center">
  <img src="image/README/1745625528455.png" alt="HakuRiver GPU Info List" width="700">
</p>
<p align="center">Dedicated view showing details and utilization of GPUs reported by nodes.</p>

<br>

### Tasks Workflow

The Tasks section allows submitting, listing, and managing **command tasks**.

<h4>Task List (Command Tasks)</h4>
<p align="center">
  <img src="image/README/1745625541004.png" alt="HakuRiver Task List" width="700">
</p>
<p align="center">Browse all command tasks with their status, assigned node, and basic information.</p>

<h4>Command Task Submission and Details</h4>
<table style="width: 100%; border-collapse: collapse; border: none;">
  <thead>
    <tr>
      <th style="width: 50%; text-align: center; padding: 10px; border-bottom: 1px solid #ddd;">Command Task Submission Form</th>
      <th style="width: 50%; text-align: center; padding: 10px; border-bottom: 1px solid #ddd;">Command Task Details Dialog</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="padding: 10px; vertical-align: top; border-right: 1px solid #ddd; border-bottom: 1px solid #ddd;">
        <p align="center">
          <img src="image/README/1745625554460.png" alt="Task Submission Form" width="100%">
        </p>
        <p align="center" style="font-size: 0.9em; color: #555;">Submit new command tasks specifying command, arguments, resources, and targets (allows multi-target, NUMA, and GPU selection).</p>
      </td>
      <td style="padding: 10px; vertical-align: top; border-bottom: 1px solid #ddd;">
        <p align="center">
          <img src="image/README/1745625574031.png" alt="Task Details Dialog" width="100%">
        </p>
        <p align="center" style="font-size: 0.9em; color: #555;">View comprehensive information about a selected command task.</p>
      </td>
    </tr>
  </tbody>
</table>

<h4>Task Logs</h4>
<p align="center">
  <img src="image/README/1745625583209.png" alt="Task Logs Modal" width="700">
</p>
<p align="center">Access standard output and error logs via a dedicated modal within the task details.</p>

<br>

### VPS Tasks Workflow

The VPS Tasks section lists and manages active VPS sessions.

<h4>Active VPS Task List</h4>
<p align="center">
  <!-- No specific screenshot for VPS list provided, describe based on code -->
  <img src="image/README/1746178499670.png" alt="Example Task List (similar layout for VPS)">
  <!-- Use a placeholder image or similar layout if no specific VPS screenshot exists -->
</p>
<p align="center">Browse active VPS tasks with their status, assigned node, allocated resources, and SSH port. (Screenshot may show Command tasks, but layout is similar).</p>

<h4>VPS Task Submission</h4>
<p align="center">
  <!-- No specific screenshot for VPS submit provided, describe based on code -->
  <img src="image/README/1746178521397.png" alt="Example Submission Form (similar layout for VPS)" width="35%">
  <!-- Use a placeholder image or similar layout if no specific VPS screenshot exists -->
</p>
<p align="center" style="font-size: 0.9em; color: #555;">Submit new VPS tasks by providing an SSH public key and selecting resource requirements and a single target (node/NUMA/GPU) or allowing auto-selection.</p>

<br>

### Docker Workflow

Manage Docker environments and container tarballs on the Host.

<h4>Host Containers and Tarballs</h4>
<p align="center">
  <img src="image/README/1745625595530.png" alt="HakuRiver Docker Container List" width="700">
</p>
<p align="center">List and manage persistent containers on the Host machine and available tarballs in shared storage.</p>

<h4>Interactive Container Shell</h4>
<p align="center">
  <img src="image/README/1745625631904.png" alt="Docker Container Shell Terminal" height="600">
</p>
<p align="center">Open a web-based terminal session directly into a running Host container for environment setup.</p>

<br>

---

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
    *   View node list, status, resources, NUMA topology, and **GPU details**.
    *   View **Command Task** list, details (incl. Batch ID, Target NUMA, Required GPUs, Container), logs, kill/pause/resume.
    *   View **Active VPS Task** list, details (incl. Target NUMA, Required GPUs, Container, **SSH Port**), kill/pause/resume.
    *   Submit new **Command Tasks** using a form (allows **multi-target** selection including node, NUMA, and **GPU selection**, and **Docker container** selection).
    *   Submit new **VPS Tasks** using a form (requires SSH public key, allows **single-target** node/NUMA/GPU selection or auto, **Docker container** selection).
    *   Manage Host-side Docker containers (create, start, stop, delete).
    *   View shared container tarballs.
    *   Access interactive terminal in Host containers (via terminal modal).

**Building (Production):**

1.  Build static files:
    ```bash
    npm run build
    ```
2.  Serve the contents of `frontend/dist` using any static web server (Nginx, Apache, etc.).
3.  **Important:** Configure your production web server to proxy API requests (e.g., requests to `/api/*`) to the actual running HakuRiver Host address and port, OR modify `src/services/api.js` to use the Host's absolute URL before building.

---

## 📝 Future Work / TODO

*   **Persistent state management inside runners:** Persist task state (e.g., logs, status, etc.) inside runner node for better fault tolerance.
*   **Basic Scheduling Strategies:** Explore other simple but useful options beyond simple "first fit" for node selection. Such as round-robin, least loaded, priority-based, etc.
*   **Refine SSH proxy robustness:** Improve error handling and connection management in the SSH proxy component.
*   **More sophisticated GPU scheduling:** Implement logic for sharing GPUs among multiple tasks (e.g., using MIG or limiting processes/memory per GPU if possible).

## 🙏 Acknowledgement

*   Gemini 2.5 pro: Basic implementation and initial README generation.
*   Gemini 2.5 flash: README/Documentation improvements.
*   Claude 3.7 Sonnet: Refining the logo SVG code.