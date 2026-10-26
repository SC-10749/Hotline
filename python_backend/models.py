from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FileInfo:
    fileId: str
    fileName: str
    fileType: str
    fileSize: int
    minioPath: str | None = None
    status: str = "SUCCESS"
    extractedText: str = ""
    conversationId: str | None = None
    embed: int = 0
    createdAt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentRecord:
    fileId: str = ""
    fileName: str = ""
    docType: str = ""
    status: str = "PENDING"
    convertedVia: str = ""
    markdownUrl: str = ""
    imageCount: int = 0
    captionCount: int = 0
    charCount: int = 0
    errorMsg: str = ""
    embed: int = 0
    version: int = 0
    createdAt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionMessage:
    id: int
    conversationId: str
    question: str
    answer: str | None
    thinking: str | None
    tools: str | None
    reference: str | None
    agentType: str
    fileid: str | None
    recommend: str | None
    createTime: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "thinking": self.thinking,
            "tools": self.tools,
            "reference": self.reference,
            "agentType": self.agentType,
            "fileid": self.fileid,
            "recommend": self.recommend,
            "createTime": self.createTime,
        }
