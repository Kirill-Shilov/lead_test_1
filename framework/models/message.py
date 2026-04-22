"""
Модель сообщения Matrix (m.room.message event).
"""
from dataclasses import dataclass


@dataclass
class Message:
    """Отправленное или полученное сообщение в Matrix-комнате."""
    event_id: str      # уникальный ID события на сервере ($abc:matrix.org)
    body: str          # текст сообщения (m.text)
    sender: str        # MXID отправителя
    txn_id: str        # клиентский transaction ID (используется для идемпотентности)
    timestamp: int     # unix timestamp в миллисекундах (origin_server_ts)
    room_id: str = ""  # ID комнаты, в которой отправлено сообщение
