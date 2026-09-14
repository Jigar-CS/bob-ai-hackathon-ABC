"""Domain-level exception hierarchy.

The API layer translates these into HTTP responses; nothing below the API
layer should raise ``HTTPException`` so the domain stays framework-agnostic
and unit-testable.
"""

from __future__ import annotations


class PortPulseError(Exception):
    """Base class for all errors raised by PortPulse itself."""


class ConfigurationError(PortPulseError):
    """Raised when the application is misconfigured (missing files, bad settings)."""


class DataFileError(PortPulseError):
    """Raised when a dataset on disk is missing or unreadable."""


class CsvValidationError(PortPulseError):
    """Raised when supplied CSV content is malformed or missing required columns."""


class PlanningError(PortPulseError):
    """Raised when a plan cannot be produced from the supplied inputs."""
