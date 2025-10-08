from pydantic import BaseModel, Field

# --- Models for HTTP API ---


class CreateContainerRequest(BaseModel):
    """Request model for creating a new persistent container on the Host."""

    image_name: str = Field(
        ..., description="The public Docker image to use (e.g., 'ubuntu:latest')"
    )
    container_name: str = Field(
        ..., description="The desired name for the persistent container on the Host"
    )


class ContainerDetails(BaseModel):
    """Response model for listing containers on the Host."""

    id: str
    name: str
    image: str
    status: str
    # Add other relevant fields from `docker ps` if needed, e.g., ports, created


class ListTarResponseItem(BaseModel):
    """Structure for an item in the list_tars response."""

    timestamp: int
    tarball: str  # Just the filename


class ListTarsDetail(BaseModel):
    """Response model for listing available container tarballs for a specific container name."""

    latest_timestamp: int
    latest_tarball: str
    all_versions: list[ListTarResponseItem]


# --- Models for WebSocket Communication ---


class WebSocketInputMessage(BaseModel):
    """Model for messages received FROM the frontend client over WebSocket."""

    type: str  # e.g., "input", "resize"
    data: str | None = None  # Terminal input
    rows: int | None = None  # For resize
    cols: int | None = None  # For resize


class WebSocketOutputMessage(BaseModel):
    """Model for messages sent TO the frontend client over WebSocket."""

    type: str  # e.g., "output", "error"
    data: str
