"""Base adapter interface."""

from abc import ABC, abstractmethod
from typing import Optional


class ChannelAdapter(ABC):
    """Abstract base for channel adapters."""

    @abstractmethod
    async def send_text(self, to: str, text: str) -> dict:
        """Send a text message."""
        ...

    @abstractmethod
    async def send_images(self, to: str, image_urls: list[str], caption: Optional[str] = None) -> dict:
        """Send images with optional caption."""
        ...
