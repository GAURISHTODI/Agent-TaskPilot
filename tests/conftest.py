import pytest
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401
from app.db.seed import seed
from app.db.session import Base, make_engine
from app.llm.factory import build_llm
from app.orchestrator import Orchestrator

PHONE = "+91 90000 00001"


@pytest.fixture()
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    seed(s)
    yield s
    s.close()


@pytest.fixture()
def orch(db):
    return Orchestrator(db, build_llm("fake"))
