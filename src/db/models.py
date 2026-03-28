"""SQLAlchemy models."""

import enum
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


def _utcnow() -> datetime:
    """UTC-aware now, compatible with SQLAlchemy default/onupdate."""
    return datetime.now(UTC)

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Boolean,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.db.session import Base
from src.db.credential_type import EncryptedStr


# --- Enums ---
class ConditionEnum(str, enum.Enum):
    new = "new"
    used = "used"
    zero_km = "zero_km"


class StatusEnum(str, enum.Enum):
    available = "available"
    in_transit = "in_transit"
    preorder = "preorder"
    sold = "sold"
    reserved = "reserved"


class MessageDirectionEnum(str, enum.Enum):
    inbound = "in"
    outbound = "out"


class ChannelEnum(str, enum.Enum):
    whatsapp = "whatsapp"
    mercadolibre = "mercadolibre"
    web = "web"
    admin_test = "admin_test"


class ConversationModeEnum(str, enum.Enum):
    bot = "bot"
    manager = "manager"


class LeadIntentEnum(str, enum.Enum):
    visit = "visit"
    info = "info"
    financing = "financing"
    trade_in = "trade_in"


class LeadStatusEnum(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    handed_off = "handed_off"
    closed = "closed"


class LeadSourceEnum(str, enum.Enum):
    whatsapp = "whatsapp"
    mercadolibre = "mercadolibre"
    web = "web"
    admin = "admin"


# --- Models ---
class Dealership(Base):
    __tablename__ = "dealerships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    timezone = Column(String(64), default="America/Argentina/Buenos_Aires")
    default_language = Column(String(8), default="es-AR")
    address = Column(Text)
    phone = Column(String(64))
    business_hours = Column(Text)
    whatsapp_phone_number_id = Column(String(64))
    whatsapp_verify_token = Column(EncryptedStr(256))
    ml_user_id = Column(String(64))
    whatsapp_access_token = Column(EncryptedStr(768), nullable=True)
    admin_username = Column(String(128), nullable=True)
    admin_password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    subscription_status = Column(String(32), nullable=True)
    subscription_id = Column(String(128), nullable=True)
    ls_customer_id = Column(String(128), nullable=True)
    plan = Column(String(64), nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)
    grace_period_ends_at = Column(DateTime, nullable=True)
    whatsapp_webhook_secret = Column(EncryptedStr(256), nullable=True)
    ml_access_token = Column(EncryptedStr(768), nullable=True)
    ml_refresh_token = Column(EncryptedStr(768), nullable=True)
    ml_app_id = Column(String(64), nullable=True)
    ml_client_secret = Column(EncryptedStr(256), nullable=True)
    ml_last_sync_at = Column(DateTime, nullable=True)
    ml_last_sync_added = Column(Integer, nullable=True)
    ml_last_sync_updated = Column(Integer, nullable=True)
    ml_last_sync_sold = Column(Integer, nullable=True)

    inventory_items = relationship("InventoryItem", back_populates="dealership")
    conversations = relationship("Conversation", back_populates="dealership")
    leads = relationship("Lead", back_populates="dealership")
    events = relationship("Event", back_populates="dealership")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dealership_id = Column(Integer, ForeignKey("dealerships.id"), nullable=False)

    brand = Column(String(128), nullable=False)
    model = Column(String(128), nullable=False)
    trim = Column(String(128))
    year = Column(Integer, nullable=False)
    condition = Column(Enum(ConditionEnum), nullable=False)
    km = Column(Integer)
    price = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(8), default="ARS")
    status = Column(Enum(StatusEnum), default=StatusEnum.available)

    title = Column(String(255))
    description = Column(Text)
    photos = Column(JSONB, default=list)
    tags = Column(JSONB, default=list)
    ml_item_id = Column(String(128))

    location = Column(Text)
    vin = Column(String(64))
    external_id = Column(String(128))
    source = Column(String(32), default="manual")

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    dealership = relationship("Dealership", back_populates="inventory_items")

    __table_args__ = (
        Index("ix_inv_dealer_status", "dealership_id", "status"),
        Index("ix_inv_dealer_brand_model", "dealership_id", "brand", "model"),
        Index("ix_inv_external_id", "dealership_id", "external_id", unique=True),
    )

    @property
    def display_title(self):
        if self.title:
            return self.title
        parts = [self.brand, self.model]
        if self.trim:
            parts.append(self.trim)
        parts.append(str(self.year))
        return " ".join(parts)

    @property
    def photo_count(self):
        return len(self.photos) if self.photos else 0


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dealership_id = Column(Integer, ForeignKey("dealerships.id"), nullable=False)
    channel = Column(String(32), default="whatsapp")
    user_phone = Column(String(32), nullable=False)
    state = Column(JSONB, default=dict)
    mode = Column(String(16), default="bot")
    handoff_reason = Column(String(64))
    last_handoff_at = Column(DateTime)
    last_message_at = Column(DateTime, default=_utcnow)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    dealership = relationship("Dealership", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")

    __table_args__ = (
        Index("ix_conv_dealer_phone", "dealership_id", "user_phone", unique=True),
    )

    @property
    def is_bot_active(self):
        return self.mode == "bot"

    @property
    def mode_label(self):
        return "BOT ACTIVE" if self.mode == "bot" else "MANAGER ACTIVE"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    direction = Column(Enum(MessageDirectionEnum, values_callable=lambda x: [e.value for e in x]), nullable=False)
    text = Column(Text)
    raw = Column(JSONB)
    channel = Column(String(32))
    wamid = Column(String(128), nullable=True)
    attachments = Column(JSONB, default=list)
    created_at = Column(DateTime, default=_utcnow)

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index(
            "ix_msg_conv_wamid",
            "conversation_id",
            "wamid",
            unique=True,
            postgresql_where=sql_text("wamid IS NOT NULL"),
        ),
    )


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dealership_id = Column(Integer, ForeignKey("dealerships.id"), nullable=False)

    name = Column(String(255))
    phone = Column(String(32), nullable=False)
    intent = Column(Enum(LeadIntentEnum), default=LeadIntentEnum.visit)
    preferred_brand = Column(String(128))
    preferred_model = Column(String(128))
    budget_min = Column(Numeric(14, 2))
    budget_max = Column(Numeric(14, 2))
    status = Column(Enum(LeadStatusEnum), default=LeadStatusEnum.new)
    notes = Column(Text)

    source = Column(String(32))
    language = Column(String(8))
    last_car_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    preferred_time = Column(String(128))
    handoff_reason = Column(String(64))
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=_utcnow)

    dealership = relationship("Dealership", back_populates="leads")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dealership_id = Column(Integer, ForeignKey("dealerships.id"), nullable=False)
    type = Column(String(64), nullable=False)
    payload = Column(JSONB, default=dict)
    conversation_id = Column(Integer, nullable=True)
    lead_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    dealership = relationship("Dealership", back_populates="events")

    __table_args__ = (Index("ix_events_dealer_type_created", "dealership_id", "type", "created_at"),)
