class ReplayReviewError(Exception):
    """Expected user-facing replay-review error."""


class UnsupportedReplayBuild(ReplayReviewError):
    pass


class PlayerResolutionError(ReplayReviewError):
    pass


class InvalidExtraction(ReplayReviewError):
    pass
