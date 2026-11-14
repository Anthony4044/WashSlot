"""A laundromat as the browse read model sees it (no aggregate behaviour yet)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Laundromat:
    id: int
    name: str
    address: str
    timezone: str
