import asyncio
import csv
import io
import json
import logging
import random
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Literal
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import asc, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from .auth import current_user, hashing, require, token_for
from .db import Session, engine, get_db
from .models import AuditLog, Record, User
from .schemas import Login, RecordIn, RecordOut, RecordUpdate, Register, RoleChange, UserOut
from .settings import settings
import jwt

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('monitor')
clients: set[WebSocket] = set()

async def audit(db: AsyncSession, user: User | None, action: str, detail: str):
    db.add(AuditLog(actor_id=user.id if user else None, action=action, detail=detail))

async def generator():
    pending = []
    try:
        while True:
            now = datetime.now(timezone.utc)
            value = round(random.uniform(10, 100), 2)
            event = {'title': 'Simulated sensor', 'value': value, 'category': random.choice(['temperature', 'throughput']), 'timestamp': now.isoformat(), 'alert': value > settings.alert_threshold}
            pending.append(Record(title=event['title'], value=value, category=event['category'], timestamp=now))
            for client in tuple(clients):
                try:
                    await client.send_json(event)
                except Exception:
                    clients.discard(client)
            if len(pending) >= max(1, settings.batch_size):
                try:
                    async with Session() as db:
                        db.add_all(pending)
                        await db.commit()
                    pending.clear()
                except Exception:
                    log.exception('Failed to persist real-time batch; retrying on next cycle')
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        if pending:
            async with Session() as db:
                db.add_all(pending)
                await db.commit()
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(settings.jwt_secret) < 32:
        raise RuntimeError('JWT_SECRET must have at least 32 characters')
    async with Session() as db:
        user = await db.scalar(select(User).where(User.email == settings.admin_email))
        if not user:
            db.add(User(email=settings.admin_email, password_hash=hashing.hash(settings.admin_password), role='admin'))
            await db.commit()
    task = asyncio.create_task(generator()) if settings.realtime_enabled else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    await engine.dispose()

app = FastAPI(title='Real-time Analytics and Monitoring', lifespan=lifespan)

@app.get('/api/health', tags=['system'])
async def public_health():
    """Lightweight liveness endpoint for containers and load balancers."""
    return {'status': 'ok'}

@app.post('/api/auth/register', response_model=UserOut, status_code=201)
async def register(payload: Register, db: AsyncSession = Depends(get_db)):
    user = User(email=payload.email.lower(), password_hash=hashing.hash(payload.password), role='viewer')
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Email already registered')
    await db.refresh(user)
    return user

@app.post('/api/auth/login')
async def login(payload: Login, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not hashing.verify(payload.password, user.password_hash):
        raise HTTPException(401, 'Invalid credentials')
    return {'access_token': token_for(user), 'token_type': 'bearer', 'role': user.role}

@app.get('/api/auth/me', response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user

@app.get('/api/records', response_model=list[RecordOut])
async def list_records(page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500), category: str | None = None, start: datetime | None = None, end: datetime | None = None, sort: Literal['timestamp', 'value', 'id'] = 'timestamp', order: Literal['asc', 'desc'] = 'desc', db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Record)
    if category: stmt = stmt.where(Record.category == category)
    if start: stmt = stmt.where(Record.timestamp >= start)
    if end: stmt = stmt.where(Record.timestamp <= end)
    column = getattr(Record, sort)
    return (await db.scalars(stmt.order_by(asc(column) if order == 'asc' else desc(column)).offset((page-1)*size).limit(size))).all()

@app.post('/api/records', response_model=RecordOut, status_code=201)
async def create_record(payload: RecordIn, db: AsyncSession = Depends(get_db), user: User = Depends(require('admin', 'user'))):
    record = Record(**payload.model_dump(exclude_none=True), creator_id=user.id)
    db.add(record)
    await db.flush()
    await audit(db, user, 'create', f'record {record.id}')
    await db.commit()
    await db.refresh(record)
    return record

@app.get('/api/records/{record_id}', response_model=RecordOut)
async def get_record(record_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    record = await db.get(Record, record_id)
    if not record: raise HTTPException(404, 'Record not found')
    return record

async def owned(record_id: int, db: AsyncSession, user: User) -> Record:
    record = await db.get(Record, record_id)
    if not record: raise HTTPException(404, 'Record not found')
    if user.role != 'admin' and record.creator_id != user.id: raise HTTPException(403, 'Creator or admin required')
    return record

@app.patch('/api/records/{record_id}', response_model=RecordOut)
async def update_record(record_id: int, payload: RecordUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require('admin', 'user'))):
    record = await owned(record_id, db, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None: setattr(record, key, value)
    await audit(db, user, 'update', f'record {record.id}')
    await db.commit()
    await db.refresh(record)
    return record

@app.delete('/api/records/{record_id}', status_code=204)
async def delete_record(record_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require('admin', 'user'))):
    record = await owned(record_id, db, user)
    await db.delete(record)
    await audit(db, user, 'delete', f'record {record_id}')
    await db.commit()

@app.post('/api/records/import')
async def import_records(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(require('admin', 'user'))):
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000: raise HTTPException(413, 'File exceeds 2 MB')
    try:
        if file.filename and file.filename.lower().endswith('.csv'):
            rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        elif file.filename and file.filename.lower().endswith('.json'):
            rows = json.loads(raw)
        else: raise HTTPException(415, 'Upload .csv or .json')
        if not isinstance(rows, list) or len(rows) > 5000: raise HTTPException(400, 'Expected an array of up to 5000 records')
        parsed = [RecordIn.model_validate(row) for row in rows]
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise HTTPException(422, f'Invalid import: {exc}')
    db.add_all([Record(**item.model_dump(exclude_none=True), creator_id=user.id) for item in parsed])
    await audit(db, user, 'import', f'{len(parsed)} records')
    await db.commit()
    return {'imported': len(parsed)}

@app.get('/api/analytics/summary')
async def summary(start: datetime | None = None, end: datetime | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Record.category, func.count(Record.id), func.avg(Record.value), func.min(Record.value), func.max(Record.value), func.sum(Record.value)).group_by(Record.category)
    if start: stmt = stmt.where(Record.timestamp >= start)
    if end: stmt = stmt.where(Record.timestamp <= end)
    rows = (await db.execute(stmt)).all()
    categories = [{'category': r[0], 'count': r[1], 'average': r[2], 'min': r[3], 'max': r[4], 'total': r[5]} for r in rows]
    totals = select(func.count(Record.id), func.sum(Record.value), func.avg(Record.value), func.min(Record.value), func.max(Record.value))
    if start: totals = totals.where(Record.timestamp >= start)
    if end: totals = totals.where(Record.timestamp <= end)
    count, total, average, minimum, maximum = (await db.execute(totals)).one()
    return {'count': count, 'total': total or 0, 'average': average, 'min': minimum, 'max': maximum, 'categories': categories}

@app.get('/api/analytics/export')
async def export(start: datetime | None = None, end: datetime | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Record).order_by(Record.timestamp.desc()).limit(10000)
    if start: stmt = stmt.where(Record.timestamp >= start)
    if end: stmt = stmt.where(Record.timestamp <= end)
    records = (await db.scalars(stmt)).all()
    book = Workbook(write_only=True)
    sheet = book.create_sheet('Records')
    sheet.append(['id', 'title', 'value', 'category', 'timestamp', 'creator_id'])
    for r in records: sheet.append([r.id, r.title, r.value, r.category, r.timestamp.replace(tzinfo=None), r.creator_id])
    output = io.BytesIO()
    book.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=records.xlsx'})

@app.get('/api/admin/users', response_model=list[UserOut])
async def users(db: AsyncSession = Depends(get_db), user: User = Depends(require('admin'))):
    return (await db.scalars(select(User).order_by(User.id))).all()

@app.patch('/api/admin/users/{user_id}/role', response_model=UserOut)
async def change_role(user_id: int, payload: RoleChange, db: AsyncSession = Depends(get_db), actor: User = Depends(require('admin'))):
    user = await db.get(User, user_id)
    if not user: raise HTTPException(404, 'User not found')
    if user.id == actor.id and payload.role != 'admin': raise HTTPException(400, 'Cannot demote yourself')
    user.role = payload.role
    await audit(db, actor, 'role_change', f'user {user_id}: {payload.role}')
    await db.commit()
    await db.refresh(user)
    return user

@app.get('/api/admin/logs')
async def logs(db: AsyncSession = Depends(get_db), user: User = Depends(require('admin'))):
    rows = (await db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200))).all()
    return [{'id': r.id, 'actor_id': r.actor_id, 'action': r.action, 'detail': r.detail, 'timestamp': r.timestamp} for r in rows]

@app.get('/api/admin/health')
async def health(db: AsyncSession = Depends(get_db), user: User = Depends(require('admin'))):
    count = await db.scalar(select(func.count(Record.id)))
    return {'database': 'connected', 'record_count': count, 'websocket_clients': len(clients)}

@app.websocket('/ws/live')
async def live(websocket: WebSocket):
    token = websocket.query_params.get('token')
    try:
        data = jwt.decode(token or '', settings.jwt_secret, algorithms=['HS256'])
        async with Session() as db:
            if not await db.get(User, int(data['sub'])): raise ValueError('Unknown user')
    except (jwt.PyJWTError, KeyError, ValueError):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    clients.add(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)
