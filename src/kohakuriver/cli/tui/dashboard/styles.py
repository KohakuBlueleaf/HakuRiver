"""
Shared styles and constants for the TUI Dashboard.
"""

# Status colors mapping
STATUS_COLORS = {
    "online": "green",
    "offline": "red",
    "running": "green",
    "pending": "yellow",
    "assigning": "yellow",
    "completed": "cyan",
    "failed": "red",
    "killed": "red",
    "unknown": "dim",
    "exited": "yellow",
}


def get_status_style(status: str) -> str:
    """Get color style for a status string."""
    return STATUS_COLORS.get(status.lower(), "white")


def format_bytes(num_bytes: int) -> str:
    """Format bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


# Common CSS styles
COMMON_CSS = """
/* Header bar */
#header-bar {
    dock: top;
    height: 3;
    background: $primary-darken-2;
    padding: 0 1;
}

#header-bar .title {
    text-style: bold;
    color: $primary-lighten-2;
}

#header-bar .datetime {
    color: $text-muted;
    dock: right;
}

/* Navigation tabs */
#nav-tabs {
    dock: top;
    height: 1;
    background: $surface;
}

#nav-tabs .tab {
    padding: 0 2;
}

#nav-tabs .tab.active {
    background: $primary;
    text-style: bold;
}

/* Footer */
#footer {
    dock: bottom;
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
}

#footer .key {
    text-style: bold;
    color: $text;
}

/* Content area */
#content {
    height: 100%;
    width: 100%;
}

/* DataTable styling */
DataTable {
    height: 100%;
}

DataTable > .datatable--header {
    text-style: bold;
    background: $surface;
}

DataTable > .datatable--cursor {
    background: $primary-darken-1;
}

/* Status indicator colors */
.status-online, .status-running {
    color: green;
}

.status-offline, .status-failed, .status-killed {
    color: red;
}

.status-pending, .status-assigning, .status-exited {
    color: yellow;
}

.status-completed {
    color: cyan;
}

/* Modal dialogs */
ModalScreen {
    align: center middle;
}

#modal-dialog {
    width: 60;
    height: auto;
    max-height: 80%;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

#modal-dialog .title {
    text-style: bold;
    text-align: center;
    width: 100%;
    padding-bottom: 1;
}

#modal-dialog Input {
    width: 100%;
    margin-bottom: 1;
}

#modal-dialog Select {
    width: 100%;
    margin-bottom: 1;
}

#modal-dialog .buttons {
    height: 3;
    align: center middle;
}

#modal-dialog Button {
    margin: 0 1;
}

/* Summary cards */
.summary-card {
    border: solid $primary;
    padding: 1;
    margin: 0 1;
    height: auto;
}

.summary-card .label {
    text-style: bold;
    color: $text-muted;
}

.summary-card .value {
    text-style: bold;
    color: $text;
}

/* Detail view */
#detail-panel {
    height: 100%;
    padding: 1;
}

#detail-info {
    height: auto;
    border: solid $primary;
    padding: 1;
    margin-bottom: 1;
}

#detail-logs {
    height: 1fr;
}

#stdout-panel, #stderr-panel {
    height: 100%;
    border: solid green;
    padding: 0 1;
    overflow-y: auto;
}

#stderr-panel {
    border: solid red;
}
"""
