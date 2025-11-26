"""Database base configuration and utilities."""

import asyncio

import peewee

from hakuriver.utils.logger import logger

# Global database instance - initialized with None, set path later
db = peewee.SqliteDatabase(None)


class BaseModel(peewee.Model):
    """Base model for all HakuRiver database models."""

    class Meta:
        database = db


def initialize_database(db_path: str) -> None:
    """
    Connect to the database and create tables if they don't exist.

    Args:
        db_path: Path to the SQLite database file
    """
    # Import here to avoid circular imports
    from hakuriver.db.node import Node
    from hakuriver.db.task import Task

    logger.debug(f"initialize_database called with path: {db_path}")
    try:
        logger.debug("Calling db.init()...")
        db.init(db_path)
        logger.debug("Calling db.connect()...")
        db.connect()
        logger.debug("Creating tables Node and Task...")
        db.create_tables([Node, Task], safe=True)
        logger.info(f"Database initialized at: {db_path}")

        # Debug: Check if tables exist and count records
        try:
            task_count = Task.select().count()
            node_count = Node.select().count()
            logger.debug(f"Database stats: {task_count} tasks, {node_count} nodes")
        except Exception as e:
            logger.debug(f"Error counting records: {e}")

    except peewee.OperationalError as e:
        logger.error(f"Error initializing database '{db_path}': {e}")
        raise


def close_database() -> None:
    """Close the database connection."""
    if not db.is_closed():
        db.close()
        logger.debug("Database connection closed")


async def run_in_executor(func, *args, **kwargs):
    """
    Run a blocking database function in an executor.

    Use this for async contexts to avoid blocking the event loop.

    Example:
        task = await run_in_executor(Task.get_or_none, Task.task_id == task_id)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
