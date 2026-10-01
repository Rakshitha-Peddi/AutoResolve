from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.database.session import Base

class Bug(Base):
    __tablename__ = "bugs"
    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    repository = Column(String(500), nullable=False)
    reporter = Column(String(200), nullable=False)
    status = Column(String(50), default="NEW", nullable=False)
    current_iteration = Column(Integer, default=0)
    root_cause = Column(Text, default="")
    relevant_files = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    iterations = relationship("Iteration", back_populates="bug", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="bug", cascade="all, delete-orphan")
    events = relationship("AuditEvent", back_populates="bug", cascade="all, delete-orphan")

class Iteration(Base):
    __tablename__ = "iterations"
    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey("bugs.id"), nullable=False)
    iteration_number = Column(Integer, nullable=False)
    analysis = Column(Text, default="{}")
    repair_plan = Column(Text, default="[]")
    patch = Column(Text, default="")
    tests = Column(Text, default="{}")
    validation = Column(Text, default="{}")
    status = Column(String(50), default="CREATED")
    created_at = Column(DateTime, default=datetime.utcnow)
    bug = relationship("Bug", back_populates="iterations")

class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey("bugs.id"), nullable=False)
    iteration_id = Column(Integer, ForeignKey("iterations.id"), nullable=True)
    developer = Column(String(200), default="developer")
    feedback = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    bug = relationship("Bug", back_populates="feedback")

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey("bugs.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    message = Column(Text, default="")
    metadata_json = Column(Text, default="{}")
    timestamp = Column(DateTime, default=datetime.utcnow)
    bug = relationship("Bug", back_populates="events")
