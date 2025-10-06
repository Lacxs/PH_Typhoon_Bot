"""Data fetching modules for PAGASA and JTWC"""

from .pagasa_parser import PAGASAParser
from .jtwc_parser import JTWCParser

__all__ = ['PAGASAParser', 'JTWCParser']
