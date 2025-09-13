from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
import uuid


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processes: Mapped[list["Process"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Process(Base):
    __tablename__ = "processes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    pid: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    session: Mapped["Session"] = relationship(back_populates="processes")
    commands: Mapped[list["Command"]] = relationship(
        back_populates="process", cascade="all, delete-orphan"
    )


class Command(Base):
    __tablename__ = "commands"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    process_id: Mapped[str] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE")
    )
    command_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    process: Mapped["Process"] = relationship(back_populates="commands")
    inputs: Mapped[list["Input"]] = relationship(
        back_populates="command", cascade="all, delete-orphan"
    )
    outputs: Mapped[list["Output"]] = relationship(
        back_populates="command", cascade="all, delete-orphan"
    )


class Input(Base):
    __tablename__ = "inputs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    command_id: Mapped[str] = mapped_column(
        ForeignKey("commands.id", ondelete="CASCADE")
    )
    input_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    command: Mapped["Command"] = relationship(back_populates="inputs")


class Output(Base):
    __tablename__ = "outputs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    command_id: Mapped[str] = mapped_column(
        ForeignKey("commands.id", ondelete="CASCADE")
    )
    output_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    command: Mapped["Command"] = relationship(back_populates="outputs")
