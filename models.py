from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, func
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, PyEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    SALES = "sales"
    FABRIC_HEAD = "fabric_head"
    RAZDACHA_HEAD = "razdacha_head"
    RAZDACHA_HELPER = "razdacha_helper"
    SEWER = "sewer"
    CUTTER = "cutter"
    NAITEL = "naitel"
    IRONER = "ironer"
    PACKER = "packer"
    QC = "qc"


class OrderStatus(str, PyEnum):
    OPEN = "open"
    FABRIC_ASSIGNED = "fabric_assigned"
    CUTTING = "cutting"
    SEWING = "sewing"
    QC = "qc"
    PACKING = "packing"
    READY = "ready"
    CLOSED = "closed"


class TransactionType(str, PyEnum):
    EARN = "earn"
    BONUS = "bonus"
    PENALTY = "penalty"
    WITHDRAWAL = "withdrawal"


class InventoryAction(str, PyEnum):
    IN = "in"
    OUT = "out"
    ADJUST = "adjust"


class TransferStatus(str, PyEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=True)
    role = Column(Enum(UserRole), nullable=True)
    worker_type = Column(String(50), nullable=True)
    balance = Column(Numeric(12, 2), default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    transactions = relationship("Transaction", back_populates="user",
                                foreign_keys="Transaction.user_id")
    inventory_logs = relationship("InventoryLog", back_populates="performer")
    sent_transfers = relationship("Transfer", back_populates="from_user",
                                  foreign_keys="Transfer.from_user_id")
    received_transfers = relationship("Transfer", back_populates="to_user",
                                      foreign_keys="Transfer.to_user_id")
    qc_results = relationship("QCResult", back_populates="inspector")

    def __repr__(self):
        return f"<User {self.full_name} [{self.role}]>"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_code = Column(String(20), unique=True, nullable=False)
    model_name = Column(String(100), nullable=False)
    fabric_type = Column(String(100), nullable=True)
    total_qty = Column(Integer, nullable=False)
    completed_qty = Column(Integer, default=0)
    deadline = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.OPEN)
    client_name = Column(String(100), nullable=True)
    price_per_unit = Column(Numeric(10, 2), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by = relationship("User", foreign_keys=[created_by_id])
    transactions = relationship("Transaction", back_populates="order")
    inventory_logs = relationship("InventoryLog", back_populates="order")
    transfers = relationship("Transfer", back_populates="order")
    qc_results = relationship("QCResult", back_populates="order")

    @property
    def remaining_qty(self):
        return self.total_qty - self.completed_qty

    @property
    def progress_percent(self):
        if self.total_qty == 0:
            return 0
        return round(self.completed_qty / self.total_qty * 100, 1)

    def __repr__(self):
        return f"<Order {self.order_code} [{self.status}]>"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    qty = Column(Integer, nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="transactions",
                        foreign_keys=[user_id])
    order = relationship("Order", back_populates="transactions")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    item_name = Column(String(100), nullable=False)
    unit = Column(String(20), default="metr")
    qty_on_hand = Column(Numeric(12, 3), default=0)
    last_updated = Column(DateTime(timezone=True), onupdate=func.now(),
                          server_default=func.now())

    logs = relationship("InventoryLog", back_populates="inventory")


class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id = Column(Integer, primary_key=True)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    action = Column(Enum(InventoryAction), nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    performed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    inventory = relationship("Inventory", back_populates="logs")
    order = relationship("Order", back_populates="inventory_logs")
    performer = relationship("User", back_populates="inventory_logs")


class Transfer(Base):
    __tablename__ = "transfers"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    batch_code = Column(String(50), nullable=True)
    status = Column(Enum(TransferStatus), default=TransferStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    order = relationship("Order", back_populates="transfers")
    from_user = relationship("User", back_populates="sent_transfers",
                             foreign_keys=[from_user_id])
    to_user = relationship("User", back_populates="received_transfers",
                           foreign_keys=[to_user_id])


class QCResult(Base):
    __tablename__ = "qc_results"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    inspector_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    accepted_qty = Column(Integer, default=0)
    rejected_qty = Column(Integer, default=0)
    reject_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="qc_results")
    inspector = relationship("User", back_populates="qc_results")
