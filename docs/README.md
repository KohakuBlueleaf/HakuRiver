# HakuRiver Documentation

Welcome to the HakuRiver documentation!

HakuRiver is a lightweight, self-hosted cluster manager designed for distributing command-line tasks and launching persistent interactive sessions (VPS Tasks) across compute nodes. It leverages Docker containers as portable virtual environments for reproducible execution.

This documentation is organized into several sections to help you get started, administer your cluster, use its features, and find reference information.

## Documentation Structure

```
docs/
├── README.md                     # This file - Documentation Index
├── 1. getting-started/             # Guides for new users to quickly start and understand core concepts.
│   ├── 1. overview.md            # What HakuRiver is, its purpose, and key features.
│   ├── 2. installation.md        # Step-by-step guide to installing HakuRiver components.
│   ├── 3. quick-start.md         # Hands-on guide to get a basic cluster running and submit your first tasks.
│   ├── 4. concepts.md            # Explains the fundamental ideas behind HakuRiver (Host-Runner, Docker as Env, Tasks/VPS, SSH Proxy).
│   └── 5. alternatives.md        # Comparison of HakuRiver with other tools like HPC schedulers, Kubernetes, and manual methods.
├── 2. admin-guides/                # Guides for administrators setting up and managing the HakuRiver cluster infrastructure.
│   ├── 1. host-setup.md          # Detailed guide for setting up the Host server.
│   ├── 2. runner-setup.md        # Detailed guide for setting up Runner nodes.
│   ├── 3. shared-storage.md      # Guide to configuring shared storage.
│   ├── 4. systemd-integration.md # Guide to running HakuRiver as systemd services.
│   └── 5. security.md            # Security considerations and recommendations for deploying HakuRiver.
├── 3. user-guides/                 # Guides for users submitting and managing tasks and environments.
│   ├── 1. container-workflow.md  # Guide to creating, customizing, and packaging Docker container environments.
│   ├── 2. command-tasks/         # Guides specifically for standard command-line batch tasks.
│   │   ├── 1. submission.md      # Guide to submitting Command tasks using the CLI.
│   │   └── 2. best-practices.md  # Tips for writing robust, container-friendly task scripts.
│   ├── 3. vps-tasks/             # Guides specifically for interactive VPS tasks.
│   │   ├── 1. management.md      # Guide to submitting and managing VPS tasks using the CLI.
│   │   ├── 2. ssh-access.md      # Guide to connecting to VPS tasks via the Host SSH proxy.
│   │   ├── 3. container-prep.md  # Specific notes on preparing a container image for VPS tasks (installing SSHD).
│   │   └── 4. common-use-cases.md# Examples of typical scenarios for using VPS tasks.
│   ├── 4. gpu-allocation/        # Guides for tasks requiring GPU resources.
│   │   ├── 1. allocation.md      # Guide to requesting and allocating GPUs for tasks.
│   │   └── 2. container-prep.md  # Specific notes on preparing a container image for GPU tasks (CUDA/cuDNN).
│   ├── 5. web-dashboard/         # Guides for using the graphical web interface.
│   │   ├── 1. overview.md        # Introduction and setup of the Web Dashboard.
│   │   ├── 2. ui-task-submission.md# Step-by-step guide to submitting tasks via the Web UI forms.
│   │   ├── 3. ui-monitoring.md   # Guide to using the Web UI for monitoring nodes, GPUs, and tasks.
│   │   └── 4. ui-docker.md       # Guide to using the Web UI for Host-side Docker management.
│   └── 6. monitoring/            # Guides for monitoring the cluster and debugging issues.
│       ├── 1. overview.md        # Monitoring concepts, tools (CLI & Web UI), and available data.
│       └── 2. interpreting-logs.md # Guide to locating and understanding logs.
├── 4. reference/                   # Technical reference information for HakuRiver components and APIs.
│   ├── 1. configuration.md       # Detailed reference for the config.toml file options.
│   ├── 2. client-commands.md     # Reference for the general `hakuriver.client` commands (nodes, health, status, kill, command).
│   ├── 3. task-commands.md       # Reference for the `hakuriver.task` submission and log retrieval commands.
│   ├── 4. vps-commands.md        # Reference for the `hakuriver.vps` submission and management commands.
│   ├── 5. ssh-command.md         # Reference for the `hakuriver.ssh` client command for VPS access.
│   ├── 6. api-reference.md       # Detailed reference for the Host and Runner API endpoints.
│   └── 7. architecture.md        # Overview of the HakuRiver system architecture and component interactions.
├── 5. troubleshooting/             # Guides for diagnosing and resolving problems.
│   ├── 1. common-issues.md       # Guide to diagnosing and resolving frequent issues (config, startup, registration, basic task failure).
│   ├── 2. task-execution.md      # Troubleshooting issues specifically related to tasks failing during execution.
│   ├── 3. vps-ssh.md             # Troubleshooting issues with VPS tasks and SSH connectivity.
│   └── 4. network-permissions.md # Diagnosing network connectivity and resolving permission errors.
└── 6. integration-guides/          # Guides for integrating HakuRiver with other systems.
    ├── 1. external-monitoring.md # Guide to pulling data from Host API for external monitoring systems.
    ├── 2. workflow-managers.md   # Guide to using external workflow managers to submit tasks to HakuRiver.
    └── 3. notifications.md       # Examples of setting up notifications for task failures or node status changes.
```

## Section Overviews

*   **[1. Getting Started](1.%20getting-started/1.%20overview.md)**: If you are new to HakuRiver, start here. Learn what HakuRiver is, how to install it, get a cluster running quickly, understand its core concepts, and see how it compares to other tools.
*   **[2. Admin Guides](2.%20admin-guides/)**: These guides are for administrators responsible for setting up and maintaining the HakuRiver cluster infrastructure. They cover detailed Host and Runner setup, shared storage configuration, systemd integration, and security considerations.
*   **[3. User Guides](3.%20user-guides/)**: This section is for users who will submit and manage tasks on the cluster. It explains the Docker container workflow for environment management, how to submit and manage Command tasks and VPS tasks using the CLI, how to request GPU resources, and how to use the optional Web Dashboard for monitoring and submission.
*   **[4. Reference](4.%20reference/)**: This section provides detailed technical information about HakuRiver, including a full reference for the configuration file options, the command-line interface tools (`hakuriver.client`, `hakuriver.task`, `hakuriver.vps`, `hakuriver.ssh`, `hakuriver.docker`), the Host and Runner API endpoints, and the system architecture.
*   **[5. Troubleshooting](5.%20troubleshooting/)**: This section helps you diagnose and resolve common problems that may arise during the setup, operation, or task execution phases of HakuRiver. It covers issues with component startup, task failures, network problems, and permissions.
*   **[6. Integration Guides](6.%20integration-guides/)**: These guides provide information on integrating HakuRiver with external systems, such as pulling monitoring data into external dashboards, using external workflow managers to orchestrate HakuRiver tasks, and setting up notifications.

We recommend starting with the [Getting Started](1.%20getting-started/1.%20overview.md) section and then exploring the other sections based on your role and needs.
