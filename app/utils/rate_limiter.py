import time
from collections import defaultdict
from fastapi import HTTPException, status

class RateLimiter:
    def __init__(self, max_requests: int = 5, window: int = 900):  # 5 requests per 15 minutes
        self.max_requests = max_requests
        self.window = window
        self.requests = defaultdict(list)
    
    def is_rate_limited(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window
        
        # Clean old requests
        self.requests[key] = [req_time for req_time in self.requests[key] if req_time > window_start]
        
        # Check if rate limited
        if len(self.requests[key]) >= self.max_requests:
            return True
        
        # Add current request
        self.requests[key].append(now)
        return False

# Global rate limiter instance
email_rate_limiter = RateLimiter()