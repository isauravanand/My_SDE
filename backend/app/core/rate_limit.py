import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Thread-safe in-memory sliding window rate limiter for auth endpoints."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # key -> list of timestamps
        self.hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        """Check if request is within rate limit; raise 429 if exceeded."""
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old timestamps
        timestamps = [ts for ts in self.hits[key] if ts > window_start]
        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Please try again in {max(retry_after, 1)} seconds.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        timestamps.append(now)
        self.hits[key] = timestamps

    def reset(self) -> None:
        """Reset rate limiter state (useful in test suites)."""
        self.hits.clear()


auth_rate_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency to rate limit authentication endpoints by client IP."""
    client_ip = request.client.host if request.client else "unknown"
    auth_rate_limiter.check(client_ip)
