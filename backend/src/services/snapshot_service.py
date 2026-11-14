"""快照服务：before/after 成对查询 + 守恒校验（算法 B 的落地点）。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import SNAPSHOT_LABEL_LABELS, VERDICT_LABELS
from src.models.lake_table import LakeTable
from src.models.snapshot import Snapshot
from src.services import snapshot_verifier
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc, utcnow


def serialize(snapshot: Snapshot, table_code: str | None = None, table_name: str | None = None) -> dict:
    return {
        "id": snapshot.id,
        "table_id": snapshot.table_id,
        "table_code": table_code,
        "table_name": table_name,
        "label": snapshot.label,
        "label_text": SNAPSHOT_LABEL_LABELS.get(snapshot.label, snapshot.label),
        "seq_no": snapshot.seq_no,
        "snapshot_no": snapshot.snapshot_no,
        "job_id": snapshot.job_id,
        "data_file_count": snapshot.data_file_count,
        "delete_file_count": snapshot.delete_file_count,
        "file_count": snapshot.data_file_count + snapshot.delete_file_count,
        "total_rows": snapshot.total_rows,
        "checksum": snapshot.checksum,
        "bytes": snapshot.bytes,
        "gb": round(snapshot.bytes / 1073741824, 3),
        "verdict": snapshot.verdict,
        "verdict_label": VERDICT_LABELS.get(snapshot.verdict or "", "未校验"),
        "verify": snapshot.verify or {},
        "committed_at": iso_utc(snapshot.committed_at),
    }


def get_snapshot(db: Session, snapshot_id: int) -> Snapshot:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise not_found("snapshot", snapshot_id)
    return snapshot


def get_detail(db: Session, snapshot_id: int) -> dict:
    snapshot = get_snapshot(db, snapshot_id)
    table = db.get(LakeTable, snapshot.table_id)
    payload = serialize(snapshot, table.code if table else None, table.name if table else None)
    payload["manifest_preview"] = (snapshot.manifest or [])[:40]
    payload["manifest_total"] = len(snapshot.manifest or [])
    return payload


def latest_seq(db: Session, table_id: int) -> int:
    return db.scalar(select(func.coalesce(func.max(Snapshot.seq_no), 0)).where(Snapshot.table_id == table_id)) or 0


def latest_after(db: Session, table_id: int) -> Snapshot | None:
    return db.scalar(
        select(Snapshot)
        .where(Snapshot.table_id == table_id, Snapshot.label == "after")
        .order_by(Snapshot.seq_no.desc())
        .limit(1)
    )


def latest_before(db: Session, table_id: int) -> Snapshot | None:
    return db.scalar(
        select(Snapshot)
        .where(Snapshot.table_id == table_id, Snapshot.label == "before")
        .order_by(Snapshot.seq_no.desc())
        .limit(1)
    )


def list_pairs(
    db: Session,
    *,
    table_id: int | None = None,
    verdict: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    """按 (table, seq_no) 聚合出 before/after 成对视图。"""
    stmt = select(Snapshot, LakeTable).join(LakeTable, LakeTable.id == Snapshot.table_id)
    if table_id:
        stmt = stmt.where(Snapshot.table_id == table_id)
    rows = db.execute(stmt.order_by(Snapshot.table_id, Snapshot.seq_no)).all()

    grouped: dict[tuple[int, int], dict] = {}
    for snapshot, table in rows:
        key = (snapshot.table_id, snapshot.seq_no)
        entry = grouped.setdefault(
            key,
            {
                "key": f"{snapshot.table_id}-{snapshot.seq_no}",
                "table_id": snapshot.table_id,
                "table_code": table.code,
                "table_name": table.name,
                "layer": table.layer,
                "seq_no": snapshot.seq_no,
                "before_id": None,
                "after_id": None,
                "before": None,
                "after": None,
                "rows_before": 0,
                "rows_after": 0,
                "rows_delta": 0,
                "checksum_before": 0,
                "checksum_after": 0,
                "verdict": None,
                "reasons": [],
                "committed_at": None,
            },
        )
        item = serialize(snapshot, table.code, table.name)
        if snapshot.label == "before":
            entry["before"] = item
            entry["before_id"] = snapshot.id
            entry["rows_before"] = snapshot.total_rows
            entry["checksum_before"] = snapshot.checksum
        else:
            entry["after"] = item
            entry["after_id"] = snapshot.id
            entry["rows_after"] = snapshot.total_rows
            entry["checksum_after"] = snapshot.checksum
            entry["verdict"] = snapshot.verdict
            entry["reasons"] = (snapshot.verify or {}).get("reasons", [])
            entry["committed_at"] = iso_utc(snapshot.committed_at)
        entry["rows_delta"] = entry["rows_after"] - entry["rows_before"]

    items = list(grouped.values())
    if verdict:
        items = [item for item in items if item["verdict"] == verdict]
    items.sort(key=lambda item: (item["table_id"], item["seq_no"]))
    total = len(items)
    window = items[offset : offset + limit]
    return {"items": window, "total": total, "limit": limit, "offset": offset}


def verify_pair(db: Session, before_id: int, after_id: int) -> dict:
    before = get_snapshot(db, before_id)
    after = get_snapshot(db, after_id)
    if before.table_id != after.table_id:
        raise AppError("VALIDATION", 422, {"reason": "table_mismatch"})
    if before.label != "before" or after.label != "after":
        raise AppError("VALIDATION", 422, {"reason": "label_mismatch"})
    result = snapshot_verifier.verify_manifests(before.manifest or [], after.manifest or [])
    result.update(
        {
            "table_id": before.table_id,
            "seq_no": before.seq_no,
            "before_id": before.id,
            "after_id": after.id,
            "before_snapshot_no": before.snapshot_no,
            "after_snapshot_no": after.snapshot_no,
        }
    )
    return result


def record_pair(
    db: Session,
    *,
    table_id: int,
    job_id: int | None,
    before_manifest: list[dict],
    after_manifest: list[dict],
) -> dict:
    """执行模拟后落一对快照并写守恒结论（幂等：seq_no = 当前最大 +1）。"""
    seq = latest_seq(db, table_id) + 1
    before_summary = snapshot_verifier.manifest_summary(before_manifest)
    after_summary = snapshot_verifier.manifest_summary(after_manifest)
    verify = snapshot_verifier.verify_manifests(before_manifest, after_manifest)

    before = Snapshot(
        table_id=table_id,
        label="before",
        seq_no=seq,
        snapshot_no=f"snap-{table_id}-{seq}-b",
        job_id=job_id,
        manifest=before_manifest,
        data_file_count=before_summary["data_file_count"],
        delete_file_count=before_summary["delete_file_count"],
        total_rows=before_summary["total_rows"],
        checksum=before_summary["checksum"],
        bytes=before_summary["bytes"],
        committed_at=utcnow(),
    )
    after = Snapshot(
        table_id=table_id,
        label="after",
        seq_no=seq,
        snapshot_no=f"snap-{table_id}-{seq}-a",
        job_id=job_id,
        manifest=after_manifest,
        data_file_count=after_summary["data_file_count"],
        delete_file_count=after_summary["delete_file_count"],
        total_rows=after_summary["total_rows"],
        checksum=after_summary["checksum"],
        bytes=after_summary["bytes"],
        verdict=verify["verdict"],
        verify=verify,
        committed_at=utcnow(),
    )
    db.add(before)
    db.add(after)
    db.flush()
    return {"before": before, "after": after, "verify": verify, "seq_no": seq}


def snapshot_stats(db: Session) -> dict:
    rows = db.execute(
        select(Snapshot.verdict, func.count()).where(Snapshot.label == "after").group_by(Snapshot.verdict)
    ).all()
    stats = {"consistent": 0, "lossy": 0, "unverifiable": 0, "pairs": 0}
    for verdict, count in rows:
        stats[verdict or "unverifiable"] = int(count or 0)
        stats["pairs"] += int(count or 0)
    return stats
