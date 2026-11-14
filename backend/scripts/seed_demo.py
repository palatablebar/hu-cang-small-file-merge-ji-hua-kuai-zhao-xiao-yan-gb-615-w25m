"""幂等 seed：3 账号 / 6 湖表 / 36 分区 / 1170 文件 / 3 组快照 / 4 个合并计划。

自然键 upsert（不覆盖用户改过的复核结论）：
  users.email
  lake_tables.code
  partitions(table_id, partition_key)
  data_files(table_id, path)
  snapshots(table_id, label, seq_no)
  compaction_jobs.seed_key
  audit_logs.seed_key

SEED_SUMMARY 映射口径：
  sources = 湖表数；runs = 合并计划数；findings = manifest 文件数；pending = 待复核计划数。
"""
from __future__ import annotations

from datetime import datetime
from zlib import crc32

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.compaction_job import CompactionJob
from src.models.data_file import DataFile
from src.models.lake_table import LakeTable
from src.models.partition import Partition
from src.models.snapshot import Snapshot
from src.models.user import User
from src.services import data_file_service, job_service, snapshot_verifier
from src.utils.security import hash_password
from src.utils.timeutil import utcnow

from scripts.demo_config import (
    DEMO_PASSWORD,
    DEMO_USERS,
    HOURS,
    ORG,
    SEED_AUDITS,
    SEED_DATE,
    SNAPSHOT_CASES,
    SEED_JOBS,
    TABLES,
    files_for_partition,
    partition_key,
)


def ensure_users(db) -> int:
    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                    org=ORG,
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_tables(db) -> dict[str, LakeTable]:
    tables: dict[str, LakeTable] = {}
    for spec in TABLES:
        table = db.scalar(select(LakeTable).where(LakeTable.code == spec["code"]))
        if table is None:
            table = LakeTable(
                code=spec["code"],
                name=spec["name"],
                layer=spec["layer"],
                fmt=spec["fmt"],
                location=spec["location"],
                partition_spec=spec["partition_spec"],
                target_bytes=spec["target_bytes"],
                min_files=spec["min_files"],
                flow_lag_seconds=spec["flow_lag_seconds"],
                stream_window_start=spec["stream_window"][0],
                stream_window_end=spec["stream_window"][1],
                owner=ORG,
                note=spec.get("note"),
                enabled=True,
            )
            db.add(table)
            db.flush()
        tables[spec["code"]] = table
    return tables


def ensure_partitions_and_files(db, tables: dict[str, LakeTable]) -> tuple[int, int]:
    for spec in TABLES:
        table = tables[spec["code"]]
        salt = crc32(spec["code"].encode()) % 17
        existing_paths = set(db.scalars(select(DataFile.path).where(DataFile.table_id == table.id)).all())
        existing_partitions = {
            row.partition_key: row for row in db.scalars(select(Partition).where(Partition.table_id == table.id)).all()
        }
        for hour in HOURS:
            key = partition_key(hour)
            partition = existing_partitions.get(key)
            if partition is None:
                partition = Partition(
                    table_id=table.id,
                    partition_key=key,
                    dt=SEED_DATE,
                    hour=hour,
                )
                db.add(partition)
                db.flush()
                existing_partitions[key] = partition
            for spec_file in files_for_partition(spec, hour, salt):
                if spec_file["path"] in existing_paths:
                    continue
                db.add(
                    DataFile(
                        table_id=table.id,
                        partition_id=partition.id,
                        partition_key=spec_file["partition_key"],
                        path=spec_file["path"],
                        kind=spec_file["kind"],
                        bytes=spec_file["bytes"],
                        rows=spec_file["rows"],
                        checksum=spec_file["checksum"],
                        file_no=spec_file["file_no"],
                    )
                )
                existing_paths.add(spec_file["path"])
        db.flush()
    partitions = db.scalar(select(func.count()).select_from(Partition)) or 0
    files = db.scalar(select(func.count()).select_from(DataFile)) or 0
    return partitions, files


def _manifest(db, table_id: int) -> list[dict]:
    return [
        {
            "path": row.path,
            "partition_key": row.partition_key,
            "kind": row.kind,
            "bytes": row.bytes,
            "rows": row.rows,
            "checksum": row.checksum,
        }
        for row in db.scalars(
            select(DataFile).where(DataFile.table_id == table_id).order_by(DataFile.partition_key, DataFile.file_no)
        ).all()
    ]


def _seed_pair(db, table: LakeTable, case: dict) -> tuple[Snapshot, Snapshot] | None:
    seq = case["seq_no"]
    existing_before = db.scalar(
        select(Snapshot).where(Snapshot.table_id == table.id, Snapshot.label == "before", Snapshot.seq_no == seq)
    )
    existing_after = db.scalar(
        select(Snapshot).where(Snapshot.table_id == table.id, Snapshot.label == "after", Snapshot.seq_no == seq)
    )
    if existing_before is not None and existing_after is not None:
        return existing_before, existing_after

    before_manifest = _manifest(db, table.id)
    plan = job_service.build_plan_for_table(db, table, target_bytes=table.target_bytes, min_files=table.min_files)
    after_manifest = job_service.apply_merge(before_manifest, plan["merge_groups"])

    if case["mode"] == "lossy":
        # 模拟「合并写坏了」：某个合并文件少写 3 行，校验和仍按合并结果写（静默丢行）
        for item in after_manifest:
            if item["path"].endswith("merged-0001.parquet") and "hour=00" in str(item["partition_key"]):
                item["rows"] = max(0, int(item["rows"]) - 3)
                break
    elif case["mode"] == "unverifiable":
        for item in after_manifest:
            item["checksum"] = None

    before_summary = snapshot_verifier.manifest_summary(before_manifest)
    after_summary = snapshot_verifier.manifest_summary(after_manifest)
    verify = snapshot_verifier.verify_manifests(before_manifest, after_manifest)
    committed = datetime.fromisoformat(f"{SEED_DATE}T07:10:00")

    before = existing_before or Snapshot(
        table_id=table.id,
        label="before",
        seq_no=seq,
        snapshot_no=f"snap-{table.code}-{seq}-b",
        manifest=before_manifest,
        data_file_count=before_summary["data_file_count"],
        delete_file_count=before_summary["delete_file_count"],
        total_rows=before_summary["total_rows"],
        checksum=before_summary["checksum"],
        bytes=before_summary["bytes"],
        committed_at=committed,
    )
    after = existing_after or Snapshot(
        table_id=table.id,
        label="after",
        seq_no=seq,
        snapshot_no=f"snap-{table.code}-{seq}-a",
        manifest=after_manifest,
        data_file_count=after_summary["data_file_count"],
        delete_file_count=after_summary["delete_file_count"],
        total_rows=after_summary["total_rows"],
        checksum=after_summary["checksum"],
        bytes=after_summary["bytes"],
        verdict=verify["verdict"],
        verify=verify,
        committed_at=committed,
    )
    if existing_before is None:
        db.add(before)
    if existing_after is None:
        db.add(after)
    db.flush()
    return before, after


def ensure_snapshots(db, tables: dict[str, LakeTable]) -> dict[tuple[str, int], tuple[Snapshot, Snapshot]]:
    pairs: dict[tuple[str, int], tuple[Snapshot, Snapshot]] = {}
    for case in SNAPSHOT_CASES:
        table = tables[case["table_code"]]
        pair = _seed_pair(db, table, case)
        if pair is not None:
            pairs[(case["table_code"], case["seq_no"])] = pair
    return pairs


def _pair_for(code: str, seq: int, snapshots: dict[tuple[str, int], tuple[Snapshot, Snapshot]]):
    return snapshots.get((code, seq))


def ensure_jobs(
    db, tables: dict[str, LakeTable], snapshots: dict[tuple[str, int], tuple[Snapshot, Snapshot]]
) -> int:
    for spec in SEED_JOBS:
        exists = db.scalar(select(CompactionJob).where(CompactionJob.seed_key == spec["seed_key"]))
        if exists is not None:
            continue
        table = tables[spec["table_code"]]
        plan = job_service.build_plan_for_table(db, table, target_bytes=table.target_bytes, min_files=table.min_files)
        window_start = datetime.fromisoformat(spec["window"][0])
        window_end = datetime.fromisoformat(spec["window"][1])
        conflict = snapshot_verifier.check_window(
            job_start=window_start,
            job_end=window_end,
            flow_lag_seconds=table.flow_lag_seconds,
            stream_start=table.stream_window_start,
            stream_end=table.stream_window_end,
        )
        metrics = {
            key: value
            for key, value in plan.items()
            if key not in ("merge_groups", "rewrite_partitions", "skipped_partitions")
        }
        metrics["flow_lag_seconds"] = table.flow_lag_seconds

        pair = _pair_for(spec["table_code"], spec["snapshot_seq"], snapshots) if spec["snapshot_seq"] else None
        verify: dict = {}
        before_id = None
        after_id = None
        if pair is not None:
            before, after = pair
            before_id = before.id
            after_id = after.id
            verify = dict(after.verify or {})
            if spec["status"] == "executed":
                metrics["executed_by"] = spec["operator"]
                metrics["snapshot_seq"] = after.seq_no
                metrics["after_files"] = len(after.manifest or [])
                metrics["verify_verdict"] = (after.verify or {}).get("verdict")
            if spec["status"] == "blocked":
                verify = {
                    "verdict": "lossy",
                    "reasons": (after.verify or {}).get("reasons", ["rows_mismatch"]),
                    "blocked_by": "snapshot_verify",
                    "snapshot_no": after.snapshot_no,
                    "detail": after.verify or {},
                }
                metrics["blocked_reason"] = "snapshot_lossy"
        elif spec["status"] == "blocked":
            verify = {"verdict": "unverifiable", "reasons": ["stream_conflict"], "blocked_by": "stream_window", "detail": conflict}

        job = CompactionJob(
            plan_no=spec["plan_no"],
            table_id=table.id,
            trigger=spec["trigger"],
            status=spec["status"],
            target_bytes=plan["target_bytes"],
            min_files=plan["min_files"],
            flow_lag_seconds=table.flow_lag_seconds,
            window_start=window_start,
            window_end=window_end,
            operator_email=spec["operator"],
            metrics=metrics,
            merge_groups=plan["merge_groups"],
            rewrite_partitions=plan["rewrite_partitions"],
            skipped_partitions=plan["skipped_partitions"],
            conflict=conflict,
            before_snapshot_id=before_id,
            after_snapshot_id=after_id,
            verify=verify,
            review_status=spec["review_status"],
            reviewer=spec["reviewer"],
            review_note=spec["review_note"],
            seed_key=spec["seed_key"],
            executed_at=datetime.fromisoformat("2026-11-13T08:31:00") if spec["status"] == "executed" else None,
        )
        db.add(job)
        db.flush()
        if pair is not None:
            for snapshot in pair:
                if snapshot.job_id is None:
                    snapshot.job_id = job.id
    db.flush()
    return db.scalar(select(func.count()).select_from(CompactionJob)) or 0


def ensure_audit(db) -> None:
    for seed_key, email, role, action, entity, detail in SEED_AUDITS:
        exists = db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key))
        if exists is None:
            db.add(
                AuditLog(
                    actor_email=email,
                    actor_role=role,
                    action=action,
                    entity=entity,
                    detail=detail,
                    layer="seed",
                    seed_key=seed_key,
                )
            )
    db.flush()


def seed_all() -> dict:
    with session_scope() as db:
        users = ensure_users(db)
        tables = ensure_tables(db)
        _, _ = ensure_partitions_and_files(db, tables)
        data_file_service.scan(db)
        snapshots = ensure_snapshots(db, tables)
        ensure_jobs(db, tables, snapshots)
        ensure_audit(db)

        tables_total = db.scalar(select(func.count()).select_from(LakeTable)) or 0
        jobs_total = db.scalar(select(func.count()).select_from(CompactionJob)) or 0
        files_total = db.scalar(select(func.count()).select_from(DataFile)) or 0
        pending = db.scalar(
            select(func.count()).select_from(CompactionJob).where(CompactionJob.review_status == "pending")
        ) or 0
        summary = (
            f"SEED_SUMMARY brand=compactlab users={users} sources={tables_total} "
            f"runs={jobs_total} findings={files_total} pending={pending}"
        )
        print(summary, flush=True)
        return {
            "users": users,
            "sources": tables_total,
            "runs": jobs_total,
            "findings": files_total,
            "pending": pending,
        }


if __name__ == "__main__":
    seed_all()
