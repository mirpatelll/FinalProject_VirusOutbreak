import os


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'battleship.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEFAULT_GRID_SIZE = 8
    MIN_GRID_SIZE = 5
    MAX_GRID_SIZE = 15

    TEST_MODE = False
    TEST_PASSWORD = "clemson-test-2026"


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    TEST_MODE = True