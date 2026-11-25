import os
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, select

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./voicecare.db")
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    specialty: Mapped[str] = mapped_column(String(100))
    experience: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(String(100))

class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="available")

class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"))
    patient_phone: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="booked")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        result = await db.execute(select(Doctor))
        if result.scalars().first(): return
        doctors = [
            Doctor(name="Dr. Ananya Rao", specialty="Cardiology", experience="12 years", location="Hyderabad"),
            Doctor(name="Dr. Arjun Mehta", specialty="Dermatology", experience="9 years", location="Hyderabad"),
            Doctor(name="Dr. Kavya Sharma", specialty="General Medicine", experience="15 years", location="Hyderabad"),
            Doctor(name="Dr. Rahul Iyer", specialty="Orthopedics", experience="11 years", location="Hyderabad"),
        ]
        db.add_all(doctors)
        await db.flush()
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        slots = []
        for doc in doctors:
            for day in range(1, 15):
                for hour in (9, 10, 11, 14, 15, 16):
                    slots.append(Slot(doctor_id=doc.id, starts_at=base + timedelta(days=day, hours=hour)))
        db.add_all(slots)
        await db.commit()

async def get_session():
    async with SessionLocal() as session:
        yield session
