"""通道镜像同步：定时从 WVP 拉取设备/通道列表，upsert 到 channels 表。"""
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now
from app.models import Channel
from app.services import wvp as wvp_service

logger = logging.getLogger(__name__)


async def sync_channels(db: AsyncSession) -> dict:
    """全量同步。返回统计信息。每台设备翻页拉取，最多 200 页防御异常数据。"""
    wvp = wvp_service.get_wvp()
    seen: list[tuple[str, str, str, str, bool]] = []  # device_id, channel_id, device_name, name, online
    device_page, device_total = 1, 1
    while (device_page - 1) * 100 < device_total and device_page <= 200:
        devices = await wvp.devices(page=device_page, count=100)
        device_total = devices.get("total") or 0
        for d in devices.get("list") or []:
            device_id = d.get("deviceId")
            device_name = d.get("name") or ""
            if not device_id:
                continue
            ch_page, ch_total = 1, 1
            while (ch_page - 1) * 100 < ch_total and ch_page <= 200:
                resp = await wvp.channels(device_id, page=ch_page, count=100)
                ch_total = resp.get("total") or 0
                for c in resp.get("list") or []:
                    if not c.get("deviceId"):
                        continue
                    seen.append((device_id, c["deviceId"], device_name,
                                 c.get("name") or "", str(c.get("status", "")).upper() == "ON"))
                ch_page += 1
        device_page += 1

    ts = now()
    added = updated = 0
    for device_id, channel_id, device_name, name, online in seen:
        r = await db.execute(
            select(Channel).where(Channel.device_id == device_id, Channel.channel_id == channel_id)
        )
        ch = r.scalar_one_or_none()
        if ch is None:
            db.add(Channel(device_id=device_id, channel_id=channel_id, device_name=device_name,
                           name=name, online=online, active=True, last_sync_at=ts))
            added += 1
        else:
            ch.device_name = device_name
            ch.name = name
            ch.online = online
            ch.active = True
            ch.last_sync_at = ts
            updated += 1

    # 同步中未见到的通道标记 active=False（不删除，保留授权引用与审计追溯）
    seen_keys = {(d, c) for d, c, *_ in seen}
    r = await db.execute(select(Channel))
    removed = 0
    for ch in r.scalars().all():
        if (ch.device_id, ch.channel_id) not in seen_keys and ch.active:
            ch.active = False
            ch.last_sync_at = ts
            removed += 1

    return {"devices": device_total, "channels": len(seen), "added": added,
            "updated": updated, "missing": removed, "syncedAt": ts.isoformat()}


async def sync_job() -> None:
    """APScheduler 定时任务入口：独立会话，异常只记日志。"""
    from app.core.db import _session_factory
    from app.services import audit
    if _session_factory is None:
        return
    try:
        async with _session_factory() as db:
            stats = await sync_channels(db)
            await audit.write(db, action=audit.AuditAction.CHANNEL_SYNC,
                              object_type="channel", object_id=None,
                              params={k: v for k, v in stats.items() if k != "syncedAt"})
            await db.commit()
        logger.info("通道同步完成: %s", stats)
    except Exception:
        logger.exception("通道同步失败")
