"""当前用户可见的通道树（按设备分组，仅含已授权通道）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.timezone import now
from app.models import Channel, ChannelGrant, User
from app.schemas import ChannelNode, ChannelTree, DeviceGroup

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/tree", response_model=ChannelTree)
async def channel_tree(user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    now_ = now()
    if user.role == "ADMIN":
        r = await db.execute(select(Channel).where(Channel.active.is_(True)).order_by(Channel.device_id, Channel.channel_id))
        channels = r.scalars().all()
        items = [
            (ch, {"live": True, "playback": True, "download": True}) for ch in channels
        ]
    else:
        r = await db.execute(
            select(Channel, ChannelGrant)
            .join(ChannelGrant, ChannelGrant.channel_id == Channel.id)
            .where(ChannelGrant.user_id == user.id)
            .order_by(Channel.device_id, Channel.channel_id)
        )
        items = []
        for ch, g in r.all():
            valid = True
            if g.valid_from and now_ < g.valid_from:
                valid = False
            if g.valid_until and now_ > g.valid_until:
                valid = False
            if valid:
                items.append((ch, {"live": g.can_live, "playback": g.can_playback,
                                   "download": g.can_download}))

    groups: dict[str, DeviceGroup] = {}
    for ch, grants in items:
        g = groups.setdefault(ch.device_id, DeviceGroup(deviceId=ch.device_id,
                                                        deviceName=ch.device_name or ch.device_id,
                                                        children=[]))
        g.children.append(ChannelNode(
            channelId=ch.id, channelGbId=ch.channel_id,
            name=ch.display_name or ch.name, online=ch.online, grants=grants))

    return ChannelTree(total=sum(len(g.children) for g in groups.values()),
                       devices=list(groups.values()))
