from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class MessageCreate(BaseModel):
    target_type: Literal["room", "dm"]
    target: str
    body: str = ""
    file_id: Optional[int] = None


class FileOut(BaseModel):
    id: int
    filename: str
    size_bytes: int
    content_type: Optional[str] = None
    sha256: Optional[str] = None
    created_at: str


class MessageOut(BaseModel):
    id: int
    sender: str
    target_type: str
    target: str
    body: str
    file_id: Optional[int] = None
    file: Optional[FileOut] = None
    created_at: str


class InboxResponse(BaseModel):
    messages: list[MessageOut]
    next_since: int


class AgentOut(BaseModel):
    name: str
    created_at: str


class AgentsResponse(BaseModel):
    agents: list[AgentOut]


class ReceiptsRequest(BaseModel):
    message_ids: list[int]


class MarkReadResponse(BaseModel):
    marked: int


class ReceiptOut(BaseModel):
    agent: str
    seen_at: str


class MessageReceiptsResponse(BaseModel):
    message_id: int
    receipts: list[ReceiptOut]


class PresenceSet(BaseModel):
    status: str


class PresenceOut(BaseModel):
    agent: str
    status: Optional[str] = None
    updated_at: Optional[str] = None
    stale: bool


class PresenceResponse(BaseModel):
    presence: list[PresenceOut]


class HealthResponse(BaseModel):
    status: str
    version: str
