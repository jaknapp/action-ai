import pytest

from action.app.logging_config import init_logging_from_env


@pytest.fixture(scope="session", autouse=True)
def configure_logging_fixture() -> None:
    init_logging_from_env()