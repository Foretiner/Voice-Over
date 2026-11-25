from pydantic import BaseModel, Field
from datetime import date as Date

class BookRequest(BaseModel):
    doctor_id: int
    slot_id: int
    phone: str = Field(min_length=7, max_length=20)

class CancelRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=20)
    appointment_id: int | None = None

class AvailabilityRequest(BaseModel):
    doctor_id: int | None = None
    specialty: str | None = None
    date: Date | None = None
