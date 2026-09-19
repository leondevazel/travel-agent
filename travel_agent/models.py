import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TripSession(Base):
    __tablename__ = "trip_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    messages: Mapped[list] = mapped_column(JSON, default=list)
    trip_brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    flight_candidates: Mapped[list] = mapped_column(JSON, default=list)
    hotel_candidates: Mapped[list] = mapped_column(JSON, default=list)
    itinerary: Mapped[list] = mapped_column(JSON, default=list)
