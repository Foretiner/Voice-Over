import re
from datetime import datetime, date, time
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from .db import Doctor, Slot, Appointment

def normalize_phone(phone: str) -> str:
    value = re.sub(r"[^0-9+]", "", phone.strip())
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError("Please provide a valid phone number with 7 to 15 digits.")
    return value

async def list_doctors(db: AsyncSession):
    rows = (await db.execute(select(Doctor).order_by(Doctor.name))).scalars().all()
    return [dict(id=d.id, name=d.name, specialty=d.specialty, experience=d.experience, location=d.location) for d in rows]

async def availability(db: AsyncSession, doctor_id=None, specialty=None, on_date: date | None=None):
    stmt = select(Slot, Doctor).join(Doctor, Doctor.id == Slot.doctor_id).where(Slot.status == "available", Slot.starts_at >= datetime.now())
    if doctor_id: stmt = stmt.where(Doctor.id == doctor_id)
    if specialty: stmt = stmt.where(Doctor.specialty.ilike(f"%{specialty}%"))
    if on_date:
        stmt = stmt.where(Slot.starts_at >= datetime.combine(on_date, time.min), Slot.starts_at < datetime.combine(on_date, time.max))
    rows = (await db.execute(stmt.order_by(Slot.starts_at).limit(100))).all()
    return [dict(slot_id=s.id, doctor_id=d.id, doctor_name=d.name, specialty=d.specialty, starts_at=s.starts_at.isoformat()) for s,d in rows]

async def book(db: AsyncSession, doctor_id: int, slot_id: int, phone: str):
    phone = normalize_phone(phone)
    slot = await db.get(Slot, slot_id)
    if not slot or slot.doctor_id != doctor_id or slot.status != "available" or slot.starts_at <= datetime.now():
        raise ValueError("That slot is no longer available. Please check availability again.")
    doctor = await db.get(Doctor, doctor_id)
    slot.status = "booked"
    appt = Appointment(doctor_id=doctor_id, slot_id=slot_id, patient_phone=phone)
    db.add(appt)
    await db.commit()
    await db.refresh(appt)
    return dict(id=appt.id, doctor_name=doctor.name, starts_at=slot.starts_at.isoformat(), phone=phone, status=appt.status)

async def cancel(db: AsyncSession, phone: str, appointment_id: int | None=None):
    phone = normalize_phone(phone)
    stmt = select(Appointment).where(Appointment.patient_phone == phone, Appointment.status == "booked")
    if appointment_id: stmt = stmt.where(Appointment.id == appointment_id)
    appt = (await db.execute(stmt.order_by(Appointment.created_at.desc()))).scalars().first()
    if not appt: raise ValueError("I couldn't find an active appointment for that phone number.")
    appt.status = "cancelled"
    slot = await db.get(Slot, appt.slot_id)
    if slot: slot.status = "available"
    await db.commit()
    doctor = await db.get(Doctor, appt.doctor_id)
    return dict(id=appt.id, doctor_name=doctor.name, starts_at=slot.starts_at.isoformat() if slot else None, phone=phone, status=appt.status)

async def appointments(db: AsyncSession):
    rows = (await db.execute(select(Appointment, Doctor, Slot).join(Doctor, Doctor.id == Appointment.doctor_id).join(Slot, Slot.id == Appointment.slot_id).order_by(Appointment.created_at.desc()))).all()
    return [dict(id=a.id, doctor_name=d.name, specialty=d.specialty, starts_at=s.starts_at.isoformat(), phone=a.patient_phone, status=a.status) for a,d,s in rows]
