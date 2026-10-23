import asyncio
from app.db.base import Base
from app.db.session import get_engine, get_sessionmaker
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password
from sqlalchemy import select

async def init():
    engine = get_engine("sqlite+aiosqlite:///dev.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = get_sessionmaker(engine)
    async with maker() as session:
        res = await session.execute(select(User).where(User.email == "admin@example.com"))
        if not res.scalar_one_or_none():
            admin = User(
                email="admin@example.com",
                password_hash=hash_password("AdminPass123!"),
                display_name="Dev Administrator",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            session.add(admin)
            await session.commit()
            print("Dev admin user created: admin@example.com / AdminPass123!")
        else:
            print("Admin already exists.")

if __name__ == "__main__":
    asyncio.run(init())
