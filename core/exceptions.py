class UpstreamUnavailable(Exception):
    """Raised when an upstream service doesn't respond in time -- most often
    because it's a free-tier Render service cold-starting (~25-30s) after
    idling. Carries a message meant to be shown to the calling model/user
    directly, inviting a retry, rather than a raw stack trace.
    """
