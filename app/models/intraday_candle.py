from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class IntradayCandle(Base):
    __tablename__ = "intraday_candles"

    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "resolution",
            "timestamp",
            name="uq_stock_intraday_candle_time",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    resolution: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="1m",
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    open: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    high: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    low: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    close: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    volume: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    stock = relationship(
        "Stock",
    )
