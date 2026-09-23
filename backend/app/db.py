from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from .settings import settings

engine_options = {'pool_pre_ping': True}
if not settings.database_url.startswith('sqlite'):
    engine_options.update(pool_size=5, max_overflow=10, pool_recycle=1800)
engine = create_async_engine(settings.database_url, **engine_options)
Session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncIterator[AsyncSession]:
    async with Session() as session:
        yield session
