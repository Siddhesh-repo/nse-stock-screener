from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ScreenedStock(Base):
    __tablename__ = "screened_stocks"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    trading_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    trigger_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    ltp: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    percentage_change: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    stock = relationship(
        "Stock",
        back_populates="screened_stocks",
    )