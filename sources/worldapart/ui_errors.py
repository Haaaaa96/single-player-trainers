"""Shared exception types also when app.py is launched as __main__."""


class RefreshAfterWriteError(RuntimeError):
    """The operation was verified; only its subsequent UI refresh failed."""


class ReadOnlyPageError(RuntimeError):
    """A pure read failed, but the same worker revalidated the core adapter."""

    def __init__(self, error, adapter, state):
        super().__init__(str(error))
        self.original = error
        self.adapter = adapter
        self.state = state
