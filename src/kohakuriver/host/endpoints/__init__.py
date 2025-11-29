"""
Host API Endpoints.

This package contains all FastAPI route handlers for the host server.

Modules:
    - container_filesystem: Filesystem operations for host Docker containers
    - docker: Docker container and tarball management
    - docker_terminal: WebSocket terminal for host containers
    - filesystem: Filesystem proxy for task/VPS containers on runners
    - health: Cluster health monitoring endpoints
    - nodes: Node registration and heartbeat handling
    - task_terminal: WebSocket terminal proxy for remote tasks
    - tasks: Task submission and management
    - vps: VPS creation and lifecycle management
"""
