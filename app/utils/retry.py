"""Retry utilities for resilient operations."""

import asyncio
from functools import wraps
from typing import Any, Callable, Tuple, Type

from loguru import logger


def async_retry(
    max_attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable:
    """Decorator for async functions with exponential backoff retry."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 1
            current_delay = delay
            last_error: BaseException | None = None

            while attempt <= max_attempts:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_error = exc
                    logger.warning(
                        "Retry {}/{} for {} failed: {}",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                    )
                    if attempt == max_attempts:
                        break
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1

            if last_error:
                raise last_error
            raise RuntimeError(f"Retry exhausted for {func.__name__}")

        return wrapper

    return decorator


def sync_retry(
    max_attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable:
    """Decorator for sync functions with exponential backoff retry."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import time

            attempt = 1
            current_delay = delay
            last_error: BaseException | None = None

            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_error = exc
                    logger.warning(
                        "Retry {}/{} for {} failed: {}",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                    )
                    if attempt == max_attempts:
                        break
                    time.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1

            if last_error:
                raise last_error
            raise RuntimeError(f"Retry exhausted for {func.__name__}")

        return wrapper

    return decorator
