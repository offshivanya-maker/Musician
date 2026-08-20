import logging
from typing import List, Optional
from app.config import Config

logger = logging.getLogger(__name__)


class PermissionManager:
    """Manages user permissions for bot commands"""
    
    def __init__(self, config: Config):
        self.config = config
        self.admin_ids = set(config.admin_user_ids or [])
    
    def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin"""
        return user_id in self.admin_ids
    
    def can_control_stream(self, user_id: int) -> bool:
        """Check if user can control the stream (stop, skip, etc.)"""
        return self.is_admin(user_id)
    
    def can_add_media(self, user_id: int) -> bool:
        """Check if user can add media to queue"""
        # Currently, any user can add media
        # Can be extended for more granular control
        return True
    
    def get_admins(self) -> List[int]:
        """Get list of admin user IDs"""
        return list(self.admin_ids)
