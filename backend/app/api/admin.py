"""管理端：机构、用户、通道台账、授权管理、审计查询/导出、下载任务总览。

所有写操作均记审计；授权变更逐条记录（谁把哪路视频授权给谁/收回、有效期）。
"""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import client_ip, require_admin, require_auditor
from app.core.security import hash_password
from app.core.timezone import fmt_dt, now, parse_dt
from app.models import AuditLog, Channel, ChannelGrant, DownloadTask, Org, User
from app.schemas import (ChannelUpdate, GrantItem, GrantsSaveRequest, OrgCreate,
                          OrgUpdate, ResetPasswordRequest, UserCreate, UserUpdate)
from app.services import audit, download_worker
from app.services.audit import AuditAction

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_auditor)])
# 写操作一律要求 ADMIN
write_router = APIRouter(prefix="/api/admin", tags=["admin"],
                          dependencies=[Depends(require_admin)])


# ================= 机构 =================

def _org_ok(org: Org) -> dict:
    return {"id": org.id, "name": org.name, "status": org.status,
            "ipWhitelist": org.ip_whitelist, "maxConcurrentPlays": org.max_concurrent_plays,
            "quotaGb": org.quota_gb, "remark": org.remark,
            "createdAt": fmt_dt(org.created_at)}


@router.get("/orgs")
async def list_orgs(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Org).order_by(Org.id))
    return [_org_ok(o) for o in r.scalars().all()]


@write_router.post("/orgs", status_code=201)
async def create_org(body: OrgCreate, request: Request,
                     admin: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Org).where(Org.name == body.name))
    if r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="机构名称已存在")
    org = Org(name=body.name, status=body.status, ip_whitelist=body.ipWhitelist,
              max_concurrent_plays=body.maxConcurrentPlays, quota_gb=body.quotaGb,
              remark=body.remark)
    db.add(org)
    await db.flush()
    await audit.write(db, action=AuditAction.ORG_CREATED, user=admin, object_type="org",
                      object_id=org.id, params={"name": body.name, "quotaGb": body.quotaGb},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return _org_ok(org)


@write_router.put("/orgs/{org_id}")
async def update_org(org_id: int, body: OrgUpdate, request: Request,
                     admin: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Org).where(Org.id == org_id))
    org = r.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在")
    changes = {"old": {"name": org.name, "status": org.status,
                        "ipWhitelist": org.ip_whitelist,
                        "maxConcurrentPlays": org.max_concurrent_plays, "quotaGb": org.quota_gb}}
    org.name = body.name
    org.status = body.status
    org.ip_whitelist = body.ipWhitelist
    org.max_concurrent_plays = body.maxConcurrentPlays
    org.quota_gb = body.quotaGb
    org.remark = body.remark
    changes["new"] = {"name": body.name, "status": body.status,
                       "ipWhitelist": body.ipWhitelist,
                       "maxConcurrentPlays": body.maxConcurrentPlays, "quotaGb": body.quotaGb}
    await audit.write(db, action=AuditAction.ORG_UPDATED, user=admin, object_type="org",
                      object_id=org.id, params=changes,
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return _org_ok(org)


@write_router.delete("/orgs/{org_id}")
async def delete_org(org_id: int, request: Request, admin: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Org).where(Org.id == org_id))
    org = r.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在")
    r = await db.execute(select(func.count(User.id)).where(User.org_id == org_id))
    if r.scalar_one() > 0:
        raise HTTPException(status_code=400, detail="机构下仍有用户，无法删除")
    await db.delete(org)
    await audit.write(db, action=AuditAction.ORG_DELETED, user=admin, object_type="org",
                      object_id=org_id, params={"name": org.name},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return {"ok": True}


# ================= 用户 =================

def _user_ok(user: User, org: Org | None = None) -> dict:
    return {"id": user.id, "username": user.username, "displayName": user.display_name,
            "role": user.role, "status": user.status, "orgId": user.org_id,
            "orgName": org.name if org else None,
            "mustChangePassword": user.must_change_password,
            "lockedUntil": fmt_dt(user.locked_until),
            "lastLoginAt": fmt_dt(user.last_login_at),
            "createdAt": fmt_dt(user.created_at)}


@router.get("/users")
async def list_users(orgId: int | None = None, query: str | None = None,
                     page: int = Query(1, ge=1), count: int = Query(20, ge=1, le=100),
                     db: AsyncSession = Depends(get_db)):
    stmt = select(User).order_by(User.id)
    total_stmt = select(func.count(User.id))
    if orgId is not None:
        stmt = stmt.where(User.org_id == orgId)
        total_stmt = total_stmt.where(User.org_id == orgId)
    if query:
        like = f"%{query}%"
        stmt = stmt.where((User.username.like(like)) | (User.display_name.like(like)))
        total_stmt = total_stmt.where((User.username.like(like)) | (User.display_name.like(like)))
    r = await db.execute(stmt.limit(count).offset((page - 1) * count))
    users = r.scalars().all()
    r2 = await db.execute(total_stmt)
    total = r2.scalar_one()
    orgs = {}
    for u in users:
        if u.org_id and u.org_id not in orgs:
            orgs[u.org_id] = (await db.execute(select(Org).where(Org.id == u.org_id))).scalar_one_or_none()
    return {"total": total, "list": [_user_ok(u, orgs.get(u.org_id)) for u in users]}


@write_router.post("/users", status_code=201)
async def create_user(body: UserCreate, request: Request, admin: User = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.username == body.username))
    if r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if body.role == "BANK_USER" and body.orgId is None:
        raise HTTPException(status_code=400, detail="机构用户必须归属某机构")
    user = User(username=body.username, password_hash=hash_password(body.password),
                display_name=body.displayName, org_id=body.orgId, role=body.role,
                must_change_password=True)
    db.add(user)
    await db.flush()
    await audit.write(db, action=AuditAction.USER_CREATED, user=admin, object_type="user",
                      object_id=user.id,
                      params={"username": body.username, "role": body.role, "orgId": body.orgId},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    org = None
    if body.orgId:
        org = (await db.execute(select(Org).where(Org.id == body.orgId))).scalar_one_or_none()
    return _user_ok(user, org)


@write_router.put("/users/{user_id}")
async def update_user(user_id: int, body: UserUpdate, request: Request,
                      admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and body.status is False:
        raise HTTPException(status_code=400, detail="不能停用当前登录管理员")
    changes = {}
    if body.displayName is not None:
        changes["displayName"] = {"old": user.display_name, "new": body.displayName}
        user.display_name = body.displayName
    if body.role is not None:
        changes["role"] = {"old": user.role, "new": body.role}
        user.role = body.role
    if body.orgId is not None:
        changes["orgId"] = {"old": user.org_id, "new": body.orgId}
        user.org_id = body.orgId
    if body.status is not None:
        changes["status"] = {"old": user.status, "new": body.status}
        user.status = body.status
        if not user.status:
            user.session_version += 1  # 停用立即踢下线
    await audit.write(db, action=AuditAction.USER_UPDATED, user=admin, object_type="user",
                      object_id=user.id, params=changes,
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    org = None
    if user.org_id:
        org = (await db.execute(select(Org).where(Org.id == user.org_id))).scalar_one_or_none()
    return _user_ok(user, org)


@write_router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, body: ResetPasswordRequest, request: Request,
                         admin: User = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(body.newPassword)
    user.must_change_password = True
    user.failed_attempts = 0
    user.locked_until = None
    user.session_version += 1  # 重置密码后旧会话全部失效
    await audit.write(db, action=AuditAction.PASSWORD_RESET, user=admin, object_type="user",
                      object_id=user.id, params={"username": user.username},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return {"ok": True}


@write_router.post("/users/{user_id}/unlock")
async def unlock_user(user_id: int, request: Request, admin: User = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.locked_until = None
    user.failed_attempts = 0
    await audit.write(db, action=AuditAction.USER_UPDATED, user=admin, object_type="user",
                      object_id=user.id, params={"unlock": True, "username": user.username},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return {"ok": True}


# ================= 授权 =================

def _grant_ok(g: ChannelGrant, channel: Channel | None = None) -> dict:
    return {"id": g.id, "channelId": g.channel_id,
            "channelGbId": channel.channel_id if channel else None,
            "channelName": (channel.display_name or channel.name) if channel else None,
            "active": channel.active if channel else None,
            "canLive": g.can_live, "canPlayback": g.can_playback, "canDownload": g.can_download,
            "validFrom": fmt_dt(g.valid_from), "validUntil": fmt_dt(g.valid_until),
            "grantedBy": g.granted_by, "createdAt": fmt_dt(g.created_at)}


@router.get("/users/{user_id}/grants")
async def list_grants(user_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(ChannelGrant, Channel)
        .join(Channel, Channel.id == ChannelGrant.channel_id)
        .where(ChannelGrant.user_id == user_id)
        .order_by(Channel.device_id, Channel.channel_id))
    return [_grant_ok(g, ch) for g, ch in r.all()]


@write_router.put("/users/{user_id}/grants")
async def save_grants(user_id: int, body: GrantsSaveRequest, request: Request,
                      admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """全量覆盖式保存：与现有授权做 diff，逐条记审计。"""
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    r = await db.execute(select(ChannelGrant).where(ChannelGrant.user_id == user_id))
    existing: dict[int, ChannelGrant] = {g.channel_id: g for g in r.scalars().all()}

    incoming: dict[int, GrantItem] = {}
    for item in body.grants:
        ch = (await db.execute(select(Channel).where(Channel.id == item.channelId))).scalar_one_or_none()
        if ch is None:
            raise HTTPException(status_code=400, detail=f"通道 {item.channelId} 不存在")
        if not ch.active:
            raise HTTPException(status_code=400,
                                detail=f"通道「{ch.display_name or ch.name}」已失效，无法授权")
        if not (item.canLive or item.canPlayback or item.canDownload):
            continue  # 全关 = 不授权
        incoming[item.channelId] = item

    # 校验时间格式
    try:
        for item in incoming.values():
            if item.validFrom:
                parse_dt(item.validFrom)
            if item.validUntil:
                parse_dt(item.validUntil)
    except ValueError:
        raise HTTPException(status_code=400, detail="有效期格式应为 yyyy-MM-dd HH:mm:ss")

    changes = []
    for cid, item in incoming.items():
        valid_from = parse_dt(item.validFrom) if item.validFrom else None
        valid_until = parse_dt(item.validUntil) if item.validUntil else None
        ch = (await db.execute(select(Channel).where(Channel.id == cid))).scalar_one()
        old = existing.get(cid)
        new_val = {"canLive": item.canLive, "canPlayback": item.canPlayback,
                   "canDownload": item.canDownload,
                   "validFrom": item.validFrom, "validUntil": item.validUntil,
                   "channel": ch.channel_id}
        if old is None:
            db.add(ChannelGrant(user_id=user_id, channel_id=cid, can_live=item.canLive,
                                can_playback=item.canPlayback, can_download=item.canDownload,
                                valid_from=valid_from, valid_until=valid_until,
                                granted_by=admin.id))
            await audit.write(db, action=AuditAction.GRANT_ADDED, user=admin, object_type="user",
                              object_id=user_id, params={"to": user.username, **new_val},
                              ip=client_ip(request), ua=request.headers.get("user-agent"))
            changes.append({"channelId": cid, "op": "added", "value": new_val})
        else:
            old_val = {"canLive": old.can_live, "canPlayback": old.can_playback,
                       "canDownload": old.can_download, "validFrom": fmt_dt(old.valid_from),
                       "validUntil": fmt_dt(old.valid_until), "channel": ch.channel_id}
            if (old.can_live != item.canLive or old.can_playback != item.canPlayback
                    or old.can_download != item.canDownload
                    or fmt_dt(old.valid_from) != (item.validFrom or None)
                    or fmt_dt(old.valid_until) != (item.validUntil or None)):
                old.can_live = item.canLive
                old.can_playback = item.canPlayback
                old.can_download = item.canDownload
                old.valid_from = valid_from
                old.valid_until = valid_until
                old.granted_by = admin.id
                await audit.write(db, action=AuditAction.GRANT_UPDATED, user=admin,
                                  object_type="user", object_id=user_id,
                                  params={"to": user.username, "old": old_val, "new": new_val},
                                  ip=client_ip(request), ua=request.headers.get("user-agent"))
                changes.append({"channelId": cid, "op": "updated", "value": new_val})

    for cid, old in existing.items():
        if cid not in incoming:
            ch = (await db.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
            await db.delete(old)
            await audit.write(db, action=AuditAction.GRANT_REMOVED, user=admin, object_type="user",
                              object_id=user_id,
                              params={"to": user.username, "channel": ch.channel_id if ch else cid,
                                      "removed": {"canLive": old.can_live,
                                                  "canPlayback": old.can_playback,
                                                  "canDownload": old.can_download}},
                              ip=client_ip(request), ua=request.headers.get("user-agent"))
            changes.append({"channelId": cid, "op": "removed"})

    return {"ok": True, "changes": changes}


# ================= 通道台账 =================

@router.get("/channels")
async def list_channels(query: str | None = None, active: bool | None = None,
                        page: int = Query(1, ge=1), count: int = Query(50, ge=1, le=200),
                        db: AsyncSession = Depends(get_db)):
    stmt = select(Channel).order_by(Channel.device_id, Channel.channel_id)
    total_stmt = select(func.count(Channel.id))
    if query:
        like = f"%{query}%"
        cond = (Channel.name.like(like)) | (Channel.display_name.like(like)) | \
               (Channel.channel_id.like(like)) | (Channel.device_id.like(like))
        stmt = stmt.where(cond)
        total_stmt = total_stmt.where(cond)
    if active is not None:
        stmt = stmt.where(Channel.active == active)
        total_stmt = total_stmt.where(Channel.active == active)
    r = await db.execute(stmt.limit(count).offset((page - 1) * count))
    r2 = await db.execute(total_stmt)
    items = [{
        "id": c.id, "deviceId": c.device_id, "deviceName": c.device_name,
        "channelId": c.channel_id, "name": c.name, "displayName": c.display_name,
        "online": c.online, "active": c.active, "lastSyncAt": fmt_dt(c.last_sync_at),
    } for c in r.scalars().all()]
    return {"total": r2.scalar_one(), "list": items}


@write_router.put("/channels/{channel_id}")
async def update_channel(channel_id: int, body: ChannelUpdate, request: Request,
                          admin: User = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Channel).where(Channel.id == channel_id))
    ch = r.scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=404, detail="通道不存在")
    old = ch.display_name
    ch.display_name = body.displayName or None
    await audit.write(db, action=AuditAction.CHANNEL_UPDATED, user=admin, object_type="channel",
                      object_id=ch.id, params={"displayName": {"old": old, "new": new_name}},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return {"ok": True}


@write_router.post("/channels/sync")
async def trigger_sync(request: Request, admin: User = Depends(require_admin),
                       db: AsyncSession = Depends(get_db)):
    from app.services.channel_sync import sync_channels
    stats = await sync_channels(db)
    await audit.write(db, action=AuditAction.CHANNEL_SYNC, user=admin, object_type="channel",
                      params=stats, ip=client_ip(request), ua=request.headers.get("user-agent"))
    return stats


# ================= 审计 =================

def _audit_filters(*, user_id: int | None, org_id: int | None, channel: str | None,
                   action: str | None, start: str | None, end: str | None,
                   username: str | None):
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if org_id is not None:
        stmt = stmt.where(AuditLog.org_id == org_id)
    if channel:
        stmt = stmt.where(AuditLog.params.like(f"%{channel}%"))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if start:
        stmt = stmt.where(AuditLog.ts >= parse_dt(start))
    if end:
        stmt = stmt.where(AuditLog.ts <= parse_dt(end))
    if username:
        stmt = stmt.where(AuditLog.username.like(f"%{username}%"))
    return stmt


@router.get("/audit")
async def query_audit(user_id: int | None = None, org_id: int | None = None,
                      username: str | None = None, channel: str | None = None,
                      action: str | None = None, start: str | None = None,
                      end: str | None = None,
                      page: int = Query(1, ge=1), count: int = Query(50, ge=1, le=200),
                      db: AsyncSession = Depends(get_db)):
    stmt = _audit_filters(user_id=user_id, org_id=org_id, channel=channel, action=action,
                          start=start, end=end, username=username)
    r = await db.execute(stmt.order_by(AuditLog.id.desc()).limit(count).offset((page - 1) * count))
    r2 = await db.execute(select(func.count()).select_from(stmt.subquery()))
    items = [{
        "id": a.id, "ts": fmt_dt(a.ts), "userId": a.user_id, "username": a.username,
        "orgId": a.org_id, "orgName": a.org_name, "action": a.action,
        "objectType": a.object_type, "objectId": a.object_id,
        "params": a.params, "result": a.result, "ip": a.ip, "ua": a.ua,
    } for a in r.scalars().all()]
    return {"total": r2.scalar_one(), "list": items}


@router.get("/audit/export")
async def export_audit(user_id: int | None = None, org_id: int | None = None,
                       username: str | None = None, channel: str | None = None,
                       action: str | None = None, start: str | None = None,
                       end: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = _audit_filters(user_id=user_id, org_id=org_id, channel=channel, action=action,
                          start=start, end=end, username=username)
    r = await db.execute(stmt.order_by(AuditLog.id.asc()))
    logs = r.scalars().all()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "时间", "用户ID", "用户名", "机构", "动作", "对象类型",
                         "对象ID", "参数", "结果", "IP", "UA"])
        yield "\ufeff"  # BOM 便于 Excel 识别 UTF-8
        for a in logs:
            row = [a.id, fmt_dt(a.ts), a.user_id, a.username, a.org_name, a.action,
                   a.object_type, a.object_id, a.params, a.result, a.ip, a.ua]
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(generate(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit_export.csv"})


# ================= 下载任务总览 =================

@router.get("/download-tasks")
async def list_all_tasks(org_id: int | None = None, status: str | None = None,
                         user_id: int | None = None,
                         page: int = Query(1, ge=1), count: int = Query(50, ge=1, le=200),
                         db: AsyncSession = Depends(get_db)):
    stmt = select(DownloadTask).order_by(DownloadTask.id.desc())
    if status:
        stmt = stmt.where(DownloadTask.status == status)
    if user_id:
        stmt = stmt.where(DownloadTask.user_id == user_id)
    if org_id:
        stmt = stmt.join(User, User.id == DownloadTask.user_id).where(User.org_id == org_id)
    r = await db.execute(stmt.limit(count).offset((page - 1) * count))
    tasks = r.scalars().all()
    from app.api.download_tasks import _load_related
    infos = await _load_related(db, list(tasks))
    total_stmt = select(func.count(DownloadTask.id))
    if status:
        total_stmt = total_stmt.where(DownloadTask.status == status)
    if user_id:
        total_stmt = total_stmt.where(DownloadTask.user_id == user_id)
    if org_id:
        total_stmt = total_stmt.join(User, User.id == DownloadTask.user_id).where(User.org_id == org_id)
    r2 = await db.execute(total_stmt)
    return {"total": r2.scalar_one(), "list": infos}
