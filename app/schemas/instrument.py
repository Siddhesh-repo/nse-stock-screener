from dataclasses import dataclass


@dataclass
class Instrument:
    token: str
    name: str
    isin: str | None
    symbol: str
    display_symbol: str
    exchange: str
    segment: str