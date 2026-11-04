import os
from pathlib import Path

import pytest
import json


TEST_DB = Path(__file__).with_name("test_aegis.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["AEGIS_TOKEN_SECRET"] = "test-only-token-secret"
os.environ["SUPERVISOR_EMAIL"] = "supervisor@example.test"
os.environ["SUPERVISOR_PASSWORD"] = "TestSupervisor!123"
os.environ.pop("GROQ_API_KEY", None)


@pytest.fixture(scope="session", autouse=True)
def remove_test_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    from db.database import Base, engine, ensure_schema, SessionLocal
    from db.seed import seed_demo
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with SessionLocal() as db:
        seed_demo(db)
    yield
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


def pytest_sessionfinish(session, exitstatus):
    report = {
        "total": session.testscollected,
        "passed": max(0, session.testscollected - session.testsfailed),
        "failed": session.testsfailed,
        "exit_status": exitstatus,
        "categories": ["prompt_injection", "authorization", "tool_ownership", "reviewer"],
    }
    Path(session.config.rootpath, "security_evaluation_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
