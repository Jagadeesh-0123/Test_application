import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["API_KEY_SECRET"] = "test-api-key"
