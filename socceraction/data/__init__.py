"""Implements serializers for the event data of various providers."""

__all__ = [
    "opta",
    "statsbomb",
    "wyscout",
    "impect",
]

from . import impect, opta, statsbomb, wyscout
