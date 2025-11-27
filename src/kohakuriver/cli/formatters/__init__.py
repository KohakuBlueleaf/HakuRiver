"""Output formatters for CLI."""

from kohakuriver.cli.formatters.docker import (
    format_container_table,
    format_image_table,
)
from kohakuriver.cli.formatters.node import (
    format_cluster_summary,
    format_node_detail,
    format_node_table,
)
from kohakuriver.cli.formatters.task import (
    format_task_detail,
    format_task_list_compact,
    format_task_table,
)
from kohakuriver.cli.formatters.vps import (
    format_vps_created,
    format_vps_detail,
    format_vps_table,
)

__all__ = [
    "format_task_table",
    "format_task_detail",
    "format_task_list_compact",
    "format_node_table",
    "format_node_detail",
    "format_cluster_summary",
    "format_vps_table",
    "format_vps_detail",
    "format_vps_created",
    "format_image_table",
    "format_container_table",
]
