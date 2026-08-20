from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import asyncio


class MediaType(Enum):
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


class StreamState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class QueueItem:
    """Represents a media item in the queue"""
    
    message_id: int
    chat_id: int
    media_type: MediaType
    file_name: str
    title: Optional[str] = None
    duration: Optional[int] = None
    position: Optional[int] = None
    added_by: Optional[int] = None
    added_at: datetime = None
    
    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now()
        if self.title is None:
            self.title = self.file_name or f"Track #{self.position}"
    
    def __str__(self):
        return f"{self.title} ({self.media_type.value})"
    
    def to_dict(self):
        return {
            "position": self.position,
            "title": self.title,
            "file_name": self.file_name,
            "media_type": self.media_type.value,
            "duration": self.duration,
            "added_by": self.added_by,
        }


@dataclass
class StreamStatus:
    """Current stream status"""
    
    state: StreamState
    current_track: Optional[QueueItem] = None
    queue_size: int = 0
    start_time: Optional[datetime] = None
    duration_played: Optional[int] = None
    
    def to_dict(self):
        return {
            "state": self.state.value,
            "current_track": self.current_track.to_dict() if self.current_track else None,
            "queue_size": self.queue_size,
            "duration_played": self.duration_played,
        }
