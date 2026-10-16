"""AI Podcast Generator — build complete, multi-speaker podcast episodes with the Sarvam API.

Public entry points:
    from podcastgen import PodcastGenerator, SarvamClient
    from podcastgen.config import Config
"""

from .config import Config
from .client import SarvamClient, SarvamError
from .pipeline import PodcastGenerator, EpisodeResult

__all__ = [
    "Config",
    "SarvamClient",
    "SarvamError",
    "PodcastGenerator",
    "EpisodeResult",
]

__version__ = "0.1.0"
