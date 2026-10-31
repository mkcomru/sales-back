import logging
import sys

import structlog
from structlog.types import Processor

log = structlog.get_logger()

OWN_PACKAGES = (
    "backend",
    "sales_agent",
    "common",
    "telegram_module",
    "wappi_module",
)

SKIP_ACCESS_LOG_PATHS = ("/health ", "/healthz ", "/api/v1/transport/connectors?type=")


class DropNoisyAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(path in msg for path in SKIP_ACCESS_LOG_PATHS)


def setup_logging(environment: str, debug: bool = False) -> None:
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
        structlog.dev.ConsoleRenderer(),
    ]

    structlog.configure(
        processors=shared_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.WARNING,
    )

    log_level = logging.DEBUG if debug else logging.INFO
    for package in OWN_PACKAGES:
        logging.getLogger(package).setLevel(log_level)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(logging.INFO)
    access_logger.addFilter(DropNoisyAccessFilter())
