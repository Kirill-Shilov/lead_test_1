"""
Модель Matrix-комнаты.
"""
from dataclasses import dataclass


@dataclass
class Room:
    """Matrix-комната (приватная или публичная)."""
    room_id: str            # внутренний ID вида !abc:matrix.org
    name: str = ""          # отображаемое имя комнаты
    alias: str = ""         # человекочитаемый псевдоним (#name:matrix.org)
    is_encrypted: bool = False  # включено ли E2EE-шифрование в комнате
