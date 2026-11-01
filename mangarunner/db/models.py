from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class JobRun(Base):
    __tablename__ = "job_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    script_id: Mapped[str] = mapped_column(String(100), nullable=False)
    script_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    script_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    
    status: Mapped[str] = mapped_column(
        String(20),
        default="queued",
        nullable=False,
    )  # queued | running | completed | failed | cancelled
    
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    queue_position: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    log_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reports_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of filenames
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_job_runs_status", "status"),
        Index("ix_job_runs_enqueued_at", "enqueued_at"),
    )

