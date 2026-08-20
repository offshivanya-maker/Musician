import asyncio
import logging
from typing import Optional, List, Dict, Any
from collections import deque
from app.models import QueueItem, StreamStatus, StreamState

logger = logging.getLogger(__name__)


class QueueManager:
    """Manages the playback queue"""
    
    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._queue: deque = deque()
        self._current: Optional[QueueItem] = None
        self._lock = asyncio.Lock()
        self._state = StreamState.IDLE
        self._state_lock = asyncio.Lock()
        
    async def add_item(self, item: QueueItem) -> int:
        """Add an item to the queue"""
        async with self._lock:
            if len(self._queue) >= self.max_size:
                raise ValueError(f"Queue is full (max {self.max_size})")
            
            position = len(self._queue) + 1
            item.position = position
            self._queue.append(item)
            logger.info(f"Added to queue: {item.title} (position {position})")
            return position
    
    async def get_next(self) -> Optional[QueueItem]:
        """Get the next item from the queue"""
        async with self._lock:
            if self._queue:
                item = self._queue.popleft()
                # Update positions
                for i, q_item in enumerate(self._queue, 1):
                    q_item.position = i
                return item
            return None
    
    async def clear_queue(self) -> int:
        """Clear the queue (excluding current item)"""
        async with self._lock:
            cleared = len(self._queue)
            self._queue.clear()
            logger.info(f"Cleared {cleared} items from queue")
            return cleared
    
    async def remove_item(self, position: int) -> Optional[QueueItem]:
        """Remove an item from the queue by position"""
        async with self._lock:
            if position < 1 or position > len(self._queue):
                return None
            
            # Convert to list for easier removal
            items = list(self._queue)
            removed = items.pop(position - 1)
            self._queue = deque(items)
            
            # Update positions
            for i, item in enumerate(self._queue, 1):
                item.position = i
            
            logger.info(f"Removed item at position {position}: {removed.title}")
            return removed
    
    async def get_queue(self) -> List[Dict[str, Any]]:
        """Get the current queue as a list of dicts"""
        async with self._lock:
            return [item.to_dict() for item in self._queue]
    
    async def get_current(self) -> Optional[QueueItem]:
        """Get the currently playing item"""
        async with self._lock:
            return self._current
    
    async def set_current(self, item: Optional[QueueItem]) -> None:
        """Set the currently playing item"""
        async with self._lock:
            self._current = item
            if item:
                logger.info(f"Now playing: {item.title}")
    
    async def get_queue_size(self) -> int:
        """Get the number of items in the queue"""
        async with self._lock:
            return len(self._queue)
    
    async def get_status(self) -> StreamStatus:
        """Get the current stream status"""
        async with self._state_lock:
            async with self._lock:
                return StreamStatus(
                    state=self._state,
                    current_track=self._current,
                    queue_size=len(self._queue)
                )
    
    async def set_state(self, state: StreamState) -> None:
        """Set the stream state"""
        async with self._state_lock:
            self._state = state
            logger.debug(f"Stream state changed to: {state.value}")
    
    async def get_state(self) -> StreamState:
        """Get the current stream state"""
        async with self._state_lock:
            return self._state
    
    async def is_empty(self) -> bool:
        """Check if the queue is empty"""
        async with self._lock:
            return len(self._queue) == 0
    
    async def get_queue_info(self) -> str:
        """Get formatted queue information"""
        async with self._lock:
            if not self._current and not self._queue:
                return "🎵 Queue is empty"
            
            result = "🎵 Queue\n"
            
            if self._current:
                result += f"▶️ Current: {self._current.title}\n"
            
            if self._queue:
                for i, item in enumerate(self._queue, 1):
                    result += f"{i}. {item.title}\n"
            
            return result.strip()
