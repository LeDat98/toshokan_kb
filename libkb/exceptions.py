class LibKBError(Exception):
    """Base for all LibraryKB errors."""


class NodeNotFound(LibKBError):
    pass


class InvalidParent(LibKBError):
    pass


class SlugCollision(LibKBError):
    pass


class LLMError(LibKBError):
    pass


class IngestError(LibKBError):
    pass


class InsufficientEvidence(LibKBError):
    """Raised by the answerer when read pages cannot support an answer (honest NOT_FOUND)."""
