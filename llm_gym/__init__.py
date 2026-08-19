"""Layered implementation package for the LLM Gym project."""

from .sources.youtube import IngestionResult, ingest_one_video
from .sources.discovery import DiscoveredVideo, DiscoveryResult, discover_channel_videos
from .sources.channel import ChannelIngestionResult, ingest_channel
from .sources.youtube_api import discover_channel_videos_api
from .sources.state import IngestionState
from .sources.source_registry import SourceRegistry

__all__ = [
    "DiscoveredVideo",
    "DiscoveryResult",
    "ChannelIngestionResult",
    "IngestionResult",
    "discover_channel_videos",
    "discover_channel_videos_api",
    "IngestionState",
    "SourceRegistry",
    "ingest_channel",
    "ingest_one_video",
]
