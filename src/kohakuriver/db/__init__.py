"""
Database models and utilities for HakuRiver.

This package provides the persistence layer using Peewee ORM with SQLite.

Submodules:
    - base: Database configuration and connection management
    - task: Task model for job tracking
    - node: Node model for cluster node management

Usage:
    from kohakuriver.db import initialize_database, Task, Node

    # Initialize at startup
    initialize_database("/path/to/db.sqlite")

    # Query tasks
    pending = Task.select().where(Task.status == "pending")

    # Create task
    task = Task.create(task_id=123, command="echo hello", ...)
"""

from kohakuriver.db.base import (
    BaseModel,
    close_database,
    db,
    initialize_database,
    run_in_executor,
)
from kohakuriver.db.node import Node
from kohakuriver.db.task import Task

__all__ = [
    # Database utilities
    "db",
    "BaseModel",
    "initialize_database",
    "close_database",
    "run_in_executor",
    # Models
    "Node",
    "Task",
]
