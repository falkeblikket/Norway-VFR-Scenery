class SceneryError(Exception):
    """An actionable error suitable for display to the user."""


class UnsafeArchive(SceneryError):
    pass


class Conflict(SceneryError):
    pass


class RecoveryError(SceneryError):
    pass
