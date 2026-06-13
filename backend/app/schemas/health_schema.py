from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str | None = None


class VersionResponse(BaseModel):
    name: str
    version: str
    environment: str


class HealthFullDatabaseResponse(BaseModel):
    connected: bool


class HealthFullStorageResponse(BaseModel):
    writable: bool
    free_bytes: int


class HealthFullToolsResponse(BaseModel):
    ffmpeg: bool
    ffprobe: bool


class HealthFullAIResponse(BaseModel):
    runtime_available: bool
    engine: str


class HealthFullQueueResponse(BaseModel):
    worker_running: bool


class HealthFullResponse(BaseModel):
    status: str
    service: str
    version: str
    database: HealthFullDatabaseResponse
    storage: HealthFullStorageResponse
    tools: HealthFullToolsResponse
    ai: HealthFullAIResponse
    queue: HealthFullQueueResponse
    warnings: list[str]
