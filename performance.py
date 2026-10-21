import logging
from contextlib import contextmanager
from functools import wraps
from time import perf_counter
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger("fnxdirect.performance")


@contextmanager
def timed(label: str):
    started_at = perf_counter()
    try:
        yield
    finally:
        logger.info(
            "performance phase=%s duration_ms=%.2f",
            label,
            (perf_counter() - started_at) * 1000,
        )


def timed_function(label: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with timed(label):
                return function(*args, **kwargs)

        return wrapped

    return decorate
