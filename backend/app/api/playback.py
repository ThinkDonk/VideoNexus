"""录像查询与回放控制。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import client_ip, get_current_user
from app.core.timezone import parse_dt
from app.models import User
from app.schemas import (PlaybackStartRequest, RecordItem, RecordQueryResponse,
                          SeekRequest, SpeedRequest)
from app.services import audit, play_service, wvp as wvp_service
from app.services.audit import AuditAction
from app.services.grants import get_channel_or_404, require_grant
from app.services.play_service import get_own_session
from app.services.wvp import WvpError

router = APIRouter(prefix="/api", tags=["playback"])


def _req_host(request: Request) -> str:
    return request.headers.get("host") or request.url.netloc


@router.get("/record/{channel_id}", response_model=RecordQueryResponse)
async def query_records(channel_id: int, startTime: str, endTime: str, request: Request,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    channel = await get_channel_or_404(db, channel_id)
    await require_grant(db, user, channel_id, "playback")
    try:
        start, end = parse_dt(startTime), parse_dt(endTime)
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式应为 yyyy-MM-dd HH:mm:ss")
    if start >= end:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间")

    wvp = wvp_service.get_wvp()
    try:
        data = await wvp.record_query(channel.device_id, channel.channel_id,
                                      startTime, endTime)
    except WvpError as e:
        raise HTTPException(status_code=502, detail=f"WVP 录像查询失败: {e}")

    records = []
    for item in (data.get("recordList") or []):
        try:
            s = parse_dt(item["startTime"])
            e = parse_dt(item["endTime"])
        except (KeyError, ValueError):
            continue
        records.append(RecordItem(startTime=item["startTime"], endTime=item["endTime"],
                                  durationSeconds=int((e - s).total_seconds()),
                                  type=item.get("type")))

    await audit.write(db, action=AuditAction.RECORD_QUERY, user=user,
                      object_type="channel", object_id=channel.id,
                      params={"channel": channel.channel_id, "startTime": startTime,
                              "endTime": endTime, "count": len(records)},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return RecordQueryResponse(channelId=channel_id, records=records)


@router.post("/playback/{channel_id}")
async def start_playback(channel_id: int, body: PlaybackStartRequest, request: Request,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    channel = await get_channel_or_404(db, channel_id)
    await require_grant(db, user, channel_id, "playback")
    try:
        start, end = parse_dt(body.startTime), parse_dt(body.endTime)
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式应为 yyyy-MM-dd HH:mm:ss")
    if start >= end:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间")

    session = await play_service.start_playback(db, user, channel, body.startTime,
                                               body.endTime, _req_host(request),
                                               client_ip(request),
                                               request.headers.get("user-agent"))
    return play_service.session_payload(session, channel, _req_host(request))


async def _own_session(db, user: User, session_id: int):
    return await get_own_session(db, user, session_id)


@router.post("/playback/sessions/{session_id}/pause")
async def playback_pause(session_id: int, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    session = await _own_session(db, user, session_id)
    try:
        await wvp_service.get_wvp().playback_control("pause", session.stream)
    except WvpError as e:
        raise HTTPException(status_code=502, detail=f"暂停失败: {e}")
    return {"ok": True}


@router.post("/playback/sessions/{session_id}/resume")
async def playback_resume(session_id: int, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    session = await _own_session(db, user, session_id)
    try:
        await wvp_service.get_wvp().playback_control("resume", session.stream)
    except WvpError as e:
        raise HTTPException(status_code=502, detail=f"恢复失败: {e}")
    return {"ok": True}


@router.post("/playback/sessions/{session_id}/seek")
async def playback_seek(session_id: int, body: SeekRequest,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    session = await _own_session(db, user, session_id)
    try:
        await wvp_service.get_wvp().playback_control("seek", session.stream, str(body.seconds))
    except WvpError as e:
        raise HTTPException(status_code=502, detail=f"拖动失败: {e}")
    return {"ok": True}


@router.post("/playback/sessions/{session_id}/speed")
async def playback_speed(session_id: int, body: SpeedRequest,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if body.speed not in (0.25, 0.5, 1, 2, 4, 8):
        raise HTTPException(status_code=400, detail="倍速仅支持 0.25/0.5/1/2/4/8")
    session = await _own_session(db, user, session_id)
    speed_str = str(int(body.speed)) if body.speed == int(body.speed) else str(body.speed)
    try:
        await wvp_service.get_wvp().playback_control("speed", session.stream, speed_str)
    except WvpError as e:
        raise HTTPException(status_code=502, detail=f"倍速失败: {e}")
    return {"ok": True}


@router.post("/playback/sessions/{session_id}/stop")
async def playback_stop(session_id: int, request: Request,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    session = await _own_session(db, user, session_id)
    await play_service.stop_session(db, user, session, client_ip(request),
                                    request.headers.get("user-agent"))
    return {"ok": True}
