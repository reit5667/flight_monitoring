from datetime import datetime, timezone
from pathlib import Path

import orjson

from db import get_conn as _get_conn
from models.storage import RawSnapshot

RAW_STORAGE_DIR = Path("raw_storage")


def save_raw(
    data: dict,
    source: str,
    route_id: int,
    records_count: int = 0,
) -> RawSnapshot:
    scraped_at = datetime.now(tz=timezone.utc)
    timestamp = scraped_at.strftime("%Y%m%dT%H%M%S_%f")

    dir_path = RAW_STORAGE_DIR / source / str(route_id)
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / f"{timestamp}.json"
    file_path.write_bytes(orjson.dumps(data))

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_snapshots (route_id, source, file_path, records_count, scraped_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (route_id, source, str(file_path), records_count, scraped_at),
            )
            snapshot_id = cur.fetchone()[0]

    return RawSnapshot(
        id=snapshot_id,
        source=source,
        route_id=route_id,
        file_path=str(file_path),
        records_count=records_count,
        scraped_at=scraped_at,
    )


def load_raw(snapshot_id: int) -> dict:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_path FROM raw_snapshots WHERE id = %s",
                (snapshot_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"Snapshot {snapshot_id} not found")

    return orjson.loads(Path(row[0]).read_bytes())
