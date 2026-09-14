"""Contract checks for the single Docker environment template."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _env_keys() -> set[str]:
    keys = set()
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_template_contains_required_runtime_keys():
    keys = _env_keys()
    assert {
        "PG_DATABASE_URL",
        "FILE2EDI_POSTGRES_STRICT",
        "DATABRICKS_HOST",
        "DATABRICKS_TOKEN",
        "DATABRICKS_MODEL_ENDPOINT",
        "SFTP_ENABLED",
        "APP_REQUIRE_AUTH",
        "APP_ADMIN_USERS",
    } <= keys