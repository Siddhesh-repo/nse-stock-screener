import time
from collections import deque


class FyersRateLimiter:

    def __init__(
        self,
        requests_per_second: int = 3,
        requests_per_minute: int = 180,
    ):
        self.requests_per_second = requests_per_second
        self.requests_per_minute = requests_per_minute

        self.second_requests = deque()
        self.minute_requests = deque()

    def wait(self) -> None:

        while True:

            now = time.monotonic()

            # Remove requests older than 1 second
            while (
                self.second_requests
                and now - self.second_requests[0] >= 1
            ):
                self.second_requests.popleft()

            # Remove requests older than 1 minute
            while (
                self.minute_requests
                and now - self.minute_requests[0] >= 60
            ):
                self.minute_requests.popleft()

            second_limit_reached = (
                len(self.second_requests)
                >= self.requests_per_second
            )

            minute_limit_reached = (
                len(self.minute_requests)
                >= self.requests_per_minute
            )

            if not second_limit_reached and not minute_limit_reached:
                break

            sleep_time = 0.1

            if second_limit_reached:
                sleep_time = max(
                    sleep_time,
                    1 - (
                        now - self.second_requests[0]
                    ),
                )

            if minute_limit_reached:
                sleep_time = max(
                    sleep_time,
                    60 - (
                        now - self.minute_requests[0]
                    ),
                )

            time.sleep(sleep_time)

        now = time.monotonic()

        self.second_requests.append(now)
        self.minute_requests.append(now)