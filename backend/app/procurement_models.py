"""Independent purchasing proposals; never replace delegation replenishment calculations."""
from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import TimestampMixin, public_uuid

class ProcurementJob(Base, TimestampMixin):
    __tablename__='procurement_jobs'
    id:Mapped[int]=mapped_column(primary_key=True)
    public_id:Mapped[str]=mapped_column(String(36),unique=True,default=public_uuid)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    status:Mapped[str]=mapped_column(String(16),default='QUEUED',index=True)
    phase:Mapped[str]=mapped_column(String(200),default='Esperando turno')
    request:Mapped[dict]=mapped_column(JSON)
    initialized:Mapped[bool]=mapped_column(default=False)
    total_articles:Mapped[int]=mapped_column(Integer,default=0)
    processed_articles:Mapped[int]=mapped_column(Integer,default=0)
    total_batches:Mapped[int]=mapped_column(Integer,default=0)
    completed_batches:Mapped[int]=mapped_column(Integer,default=0)
    worker_token:Mapped[str|None]=mapped_column(String(36))
    summary:Mapped[dict]=mapped_column(JSON,default=dict)
    error:Mapped[str|None]=mapped_column(Text)

class ProcurementBatch(Base):
    __tablename__='procurement_batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    job_id:Mapped[int]=mapped_column(ForeignKey('procurement_jobs.id'),index=True)
    number:Mapped[int]=mapped_column(Integer)
    codes:Mapped[list]=mapped_column(JSON)
    source:Mapped[dict|None]=mapped_column(JSON)
    fingerprint:Mapped[str|None]=mapped_column(String(64))
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    __table_args__=(UniqueConstraint('job_id','number'),)

class ProcurementResult(Base):
    __tablename__='procurement_results'
    id:Mapped[int]=mapped_column(primary_key=True)
    job_id:Mapped[int]=mapped_column(ForeignKey('procurement_jobs.id'),index=True)
    sku:Mapped[str]=mapped_column(String(50),index=True)
    payload:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('job_id','sku'),)
