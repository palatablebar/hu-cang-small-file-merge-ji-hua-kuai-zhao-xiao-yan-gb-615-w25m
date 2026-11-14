"""seed 幂等集成测试：同一库跑两次，SEED_SUMMARY 逐字一致且计数不变。"""
from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.models import Base, CompactionJob, DataFile, LakeTable, Partition, Snapshot, User

EXPECTED = "SEED_SUMMARY brand=compactlab users=3 sources=6 runs=4 findings=1170 pending=2"


def test_seed_twice_is_identical(tmp_path, monkeypatch, capsys):
    import src.config.database as dbmod

    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", session_factory)
    Base.metadata.create_all(bind=engine)

    from scripts.seed_demo import seed_all

    seed_all()
    seed_all()

    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("SEED_SUMMARY")]
    assert len(lines) == 2
    assert lines[0] == lines[1] == EXPECTED

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 3
        assert db.scalar(select(func.count()).select_from(LakeTable)) == 6
        assert db.scalar(select(func.count()).select_from(Partition)) == 36
        assert db.scalar(select(func.count()).select_from(DataFile)) == 1170
        assert db.scalar(select(func.count()).select_from(CompactionJob)) == 4
        # 3 组快照 = 6 行
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 6
        verdicts = dict(
            db.execute(select(Snapshot.verdict, func.count()).where(Snapshot.label == "after").group_by(Snapshot.verdict)).all()
        )
        assert verdicts == {"consistent": 1, "lossy": 1, "unverifiable": 1}
        # 复核结论不被 seed 覆盖
        job = db.scalar(select(CompactionJob).where(CompactionJob.plan_no == "CP20261113-0001"))
        job.review_status = "dismissed"
        db.commit()
    seed_all()
    with session_factory() as db:
        job = db.scalar(select(CompactionJob).where(CompactionJob.plan_no == "CP20261113-0001"))
        assert job.review_status == "dismissed"
