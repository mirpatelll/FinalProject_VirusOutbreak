import os


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'virus_outbreak.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Game defaults
    DEFAULT_GRID_SIZE = 6
    MIN_GRID_SIZE = 4
    MAX_GRID_SIZE = 20
    MIN_PLAYERS_TO_START = 2

    # Test mode
    TEST_MODE = os.environ.get("TEST_MODE", "true").lower() == "true"
    TEST_PASSWORD = "clemson-test-2026"


class TestConfig(Config):
    """Uses in-memory SQLite for testing."""
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    TEST_MODE = True

    