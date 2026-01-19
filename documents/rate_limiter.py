import threading
import time
from typing import Optional


class RateLimiter:
    """
    Token bucket rate limiter.

    Example: RateLimiter(rate_per_minute=15) enforces ~15 RPM.
    """

    def __init__(self, rate_per_minute: int, bucket_size: Optional[int] = None):
        self.rate_per_minute = rate_per_minute
        self.bucket_size = bucket_size or rate_per_minute
        self.tokens = float(self.bucket_size)
        self.lock = threading.Lock()
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens_to_add = (elapsed / 60.0) * self.rate_per_minute
        if tokens_to_add > 0:
            self.tokens = min(self.bucket_size, self.tokens + tokens_to_add)
            self.last_refill = now

    def allow(self, tokens: float = 1.0) -> bool:
        """Return True if there are enough tokens to proceed."""
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

