"""Controlled exception hierarchy for EDIFACT Orders Generator."""
from __future__ import annotations


class EdifactGeneratorError(Exception):
    """Base class for all generator errors."""


class ConfigError(EdifactGeneratorError):
    """Invalid or missing configuration."""


class N8nAnalysisError(EdifactGeneratorError):
    """n8n project analysis failed."""


class MasterDataError(EdifactGeneratorError):
    """Master data loading or validation failed."""


class PdfExtractionError(EdifactGeneratorError):
    """PDF text extraction failed."""


class MatchingError(EdifactGeneratorError):
    """Sold-to or Ship-to matching failed below confidence threshold."""


class MaterialResolutionError(EdifactGeneratorError):
    """One or more materials could not be resolved."""


class ValidationError(EdifactGeneratorError):
    """Pre-generation business rule validation failed."""


class DuplicateOrderError(EdifactGeneratorError):
    """Order already submitted (duplicate detected)."""


class ForbiddenProfileError(EdifactGeneratorError):
    """Unauthorised UNB sender, receiver, or profile detected."""


class EdifactBuildError(EdifactGeneratorError):
    """EDIFACT message construction failed."""


class SftpDeliveryError(EdifactGeneratorError):
    """SFTP upload or verification failed."""


class FileRoutingError(EdifactGeneratorError):
    """PDF routing to processed/error folder failed."""
