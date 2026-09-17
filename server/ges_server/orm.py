"""Barcha jadvallar bitta joyda (aylanma import bo'lmasligi uchun)."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    """Loyiha ichidagi rol. Admin — tizim darajasida (User.is_admin)."""

    viewer = "viewer"  # Ko'ruvchi
    operator = (
        "operator"  # Dispetcher: alarm kvitlash, buyruqlar, smena jurnali (model tahrirlamaydi)
    )
    engineer = "engineer"  # Muhandis: commit, CR ochish
    approver = "approver"  # Tasdiqlovchi: approve/reject


class VersionState(str, enum.Enum):
    wip = "wip"
    shared = "shared"
    published = "published"
    archived = "archived"


class CRStatus(str, enum.Enum):
    open = "open"
    changes_requested = "changes_requested"
    approved = "approved"
    rejected = "rejected"
    merged = "merged"


class IssueStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(256), default="")
    # SCADA/gateway o'lchovlarni yuborishi uchun kalit (X-Ingest-Key sarlavhasi)
    ingest_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Dispetcher paneli sozlamalari: {"mimic": {slot: sensor_id}, "tiles": [sensor_id...]}
    dashboard: Mapped[dict] = mapped_column(JSON, default=dict)
    # Maydon pasporti: yer/grunt/seysmiklik, ombor, to'g'on, quvur, quyi byef, inshoot belgilari
    # (ges_sim.site.SITE_FIELDS) — simulyatsiyalar shu yerdan avtomatik to'ldiriladi
    site: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    models: Mapped[list[Model]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.viewer)

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Model(Base):
    """Loyihadagi bitta model (masalan to'g'on, mashina zali)."""

    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="models")
    versions: Mapped[list[Version]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="Version.number"
    )


class Version(Base):
    """O'zgarmas versiya — har yuklash bitta yozuv. Fayl sha256 bo'yicha saqlanadi."""

    __tablename__ = "versions"
    __table_args__ = (UniqueConstraint("model_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id"), nullable=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(Text, default="")
    tag: Mapped[str] = mapped_column(String(64), default="")  # yorliq (git tag kabi), ixtiyoriy
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(256))
    file_size: Mapped[int] = mapped_column(Integer)
    state: Mapped[VersionState] = mapped_column(Enum(VersionState), default=VersionState.wip)
    # IfcOpenShell dan olingan metadata: schema, element soni, storey lar...
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    model: Mapped[Model] = relationship(back_populates="versions")
    author: Mapped[User] = relationship()


class ChangeRequest(Base):
    """GitHub PR analogi: versiyani tasdiqqa yuborish."""

    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    version_id: Mapped[int] = mapped_column(ForeignKey("versions.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[CRStatus] = mapped_column(Enum(CRStatus), default=CRStatus.open)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[Version] = relationship()
    author: Mapped[User] = relationship()
    reviews: Mapped[list[Review]] = relationship(
        back_populates="change_request", cascade="all, delete-orphan"
    )


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    change_request_id: Mapped[int] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE")
    )
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(32))  # approve | request_changes | comment
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    change_request: Mapped[ChangeRequest] = relationship(back_populates="reviews")
    reviewer: Mapped[User] = relationship()


class Issue(Base):
    """BCF uslubidagi muammo: 3D ko'rinish (kamera + tanlangan elementlar) bilan."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id"), nullable=True)
    change_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("change_requests.id"), nullable=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[IssueStatus] = mapped_column(Enum(IssueStatus), default=IssueStatus.open)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    # {"camera": {...}, "selected_guids": [...], "section": {...}}
    viewpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    # BCF almashinuvi uchun barqaror UUID
    bcf_guid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    author: Mapped[User] = relationship(foreign_keys=[author_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    comments: Mapped[list[IssueComment]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )


class IssueComment(Base):
    __tablename__ = "issue_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    viewpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class SavedView(Base):
    """Saqlangan 3D ko'rinish (kamera, tanlov, kesimlar) — model bo'yicha, hamma a'zolarga ko'rinadi."""

    __tablename__ = "saved_views"
    __table_args__ = (UniqueConstraint("model_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(64))
    viewpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User] = relationship()


class VersionDiff(Base):
    """ifcdiff natijasi keshi."""

    __tablename__ = "version_diffs"
    __table_args__ = (UniqueConstraint("from_version_id", "to_version_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_version_id: Mapped[int] = mapped_column(ForeignKey("versions.id", ondelete="CASCADE"))
    to_version_id: Mapped[int] = mapped_column(ForeignKey("versions.id", ondelete="CASCADE"))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SimStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class SimJob(Base):
    """Simulyatsiya ishi: parametrlar JSON, natija faylda (data/sim/<id>.json), xulosa JSON da."""

    __tablename__ = "sim_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id"), nullable=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32), default="hydro")  # ges_sim.catalog.kinds()
    name: Mapped[str] = mapped_column(String(256), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[SimStatus] = mapped_column(Enum(SimStatus), default=SimStatus.queued)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    author: Mapped[User] = relationship()


class DraftObject(Base):
    """Web 3D da yaratilgan qoralama element (Blender/3ds Max uslubida qo'shilgan): tur, parametrlar,
    joylashuv, Pset lar, mesh — IFC ga commit qilinguncha shu yerda turadi (model bo'yicha)."""

    __tablename__ = "draft_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128), default="")
    ifc_class: Mapped[str] = mapped_column(String(64), default="")
    params: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # geometriya parametrlari (kind bo'yicha)
    transform: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {x,y,z,rz,sx,sy,sz} IFC koordinatalar
    psets: Mapped[dict] = mapped_column(JSON, default=dict)  # {Pset_GES_*: {..}}
    mesh: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {vertices, faces} lokal IFC (commit uchun)
    # Mavjud IFC elementni tahrirlash/o'chirish: asl element GlobalId (kind "mesh" — o'rniga shu mesh,
    # GUID saqlanadi; kind "deleted" — faqat olib tashlanadi)
    source_guid: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User] = relationship()


class ImageUnderlay(Base):
    """Rasm asosi: foto/chizma/sun'iy yo'ldosh surati 3D sahnada tekislik — ustidan chizish uchun."""

    __tablename__ = "image_underlays"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(128), default="")
    file_sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(64), default="image/png")
    px_w: Mapped[int] = mapped_column(Integer, default=1)
    px_h: Mapped[int] = mapped_column(Integer, default=1)
    x: Mapped[float] = mapped_column(Float, default=0.0)  # markaz, IFC koordinatalar (m)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    z: Mapped[float] = mapped_column(Float, default=0.0)
    width_m: Mapped[float] = mapped_column(Float, default=100.0)
    rotation_deg: Mapped[float] = mapped_column(Float, default=0.0)
    opacity: Mapped[float] = mapped_column(Float, default=0.85)
    vertical: Mapped[bool] = mapped_column(Boolean, default=False)  # kesim/fasad — XZ tekisligi
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SimTemplate(Base):
    """Maxsus (foydalanuvchi) simulyatsiya shabloni: formulalar JSON (ges_sim.custom)."""

    __tablename__ = "sim_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User] = relationship()


class AlarmState(str, enum.Enum):
    ok = "ok"
    low = "low"
    high = "high"
    stale = "stale"  # ma'lumot kelmayapti


class Sensor(Base):
    """Datchik: SCADA/MQTT/HTTP dan keladigan o'lchov nuqtasi, IFC elementga bog'lanadi."""

    __tablename__ = "sensors"
    __table_args__ = (UniqueConstraint("project_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    key: Mapped[str] = mapped_column(String(64))  # SCADA teg nomi, masalan "AGG1.P"
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(
        String(32), default="value"
    )  # level|flow|power|pressure|temperature|vibration|status|position (darvoza ochilishi, %)|value
    unit: Mapped[str] = mapped_column(String(16), default="")
    element_guid: Mapped[str | None] = mapped_column(String(32), nullable=True)
    protocol: Mapped[str] = mapped_column(String(16), default="http")  # http|csv|mqtt|opcua|modbus
    address: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # protokolga xos: topic, node_id, register...
    low_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    stale_after_s: Mapped[int] = mapped_column(Integer, default=600)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Alarm ustuvorligi: low|medium|high|critical (critical/high — ovoz + email)
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    # Boshqaruv nuqtasi (setpoint/rele): dispetcher buyruq yuboradi, gateway SCADA ga yozadi
    writable: Mapped[bool] = mapped_column(Boolean, default=False)
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alarm: Mapped[AlarmState] = mapped_column(Enum(AlarmState), default=AlarmState.stale)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_sensor_ts", "sensor_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[float] = mapped_column(Float)


class AlarmEvent(Base):
    """Alarm jurnali: sensor holati ok dan chiqqanda ochiladi, ok ga qaytganda yopiladi;
    dispetcher kvitlaydi (ack)."""

    __tablename__ = "alarm_events"
    __table_args__ = (Index("ix_alarm_events_project_started", "project_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    state: Mapped[AlarmState] = mapped_column(Enum(AlarmState))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")

    sensor: Mapped[Sensor] = relationship()


class CommandStatus(str, enum.Enum):
    pending = "pending"  # gateway hali olmagan
    sent = "sent"  # gateway oldi, SCADA ga yozmoqda
    acked = "acked"  # bajarildi
    failed = "failed"
    cancelled = "cancelled"


class Command(Base):
    """Supervisory control: dispetcher buyrug'i (setpoint/rele) → gateway → SCADA. Har qadam audit."""

    __tablename__ = "commands"
    __table_args__ = (Index("ix_commands_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    value: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[CommandStatus] = mapped_column(
        Enum(CommandStatus), default=CommandStatus.pending
    )
    result: Mapped[str] = mapped_column(String(400), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sensor: Mapped[Sensor] = relationship()
    author: Mapped[User] = relationship()


class JournalEntry(Base):
    """Smena (dispetcher) jurnali: qo'lda yozuvlar, smena qabul/topshirish, hodisalar."""

    __tablename__ = "journal_entries"
    __table_args__ = (Index("ix_journal_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(
        String(16), default="note"
    )  # note|shift_start|shift_end|event
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User] = relationship()


class WorkOrderStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class WorkOrder(Base):
    """Ish buyrug'i (CMMS): texnik xizmat / ta'mirlash vazifasi — aktivga bog'langan, manba: qo'lda,
    sog'liq indeksi, alarm, texnik xizmat muddati. MTTR/MTBF KPI lari shu yerdan."""

    __tablename__ = "work_orders"
    __table_args__ = (Index("ix_wo_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium")  # low|medium|high|critical
    source: Mapped[str] = mapped_column(
        String(16), default="manual"
    )  # manual|health|alarm|maintenance
    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus), default=WorkOrderStatus.open
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    downtime_hours: Mapped[float] = mapped_column(Float, default=0.0)  # agregat to'xtab turgan soat
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    resolution: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User] = relationship(foreign_keys=[created_by])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    asset: Mapped[Asset | None] = relationship()


class SparePart(Base):
    """Ehtiyot qismlar ombori: nomi, kodi, miqdor, minimal zaxira (ogohlantirish), joylashuv, narx."""

    __tablename__ = "spare_parts"
    __table_args__ = (Index("ix_parts_project", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(64), default="")
    unit: Mapped[str] = mapped_column(String(16), default="dona")
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    min_qty: Mapped[float] = mapped_column(Float, default=0.0)
    location: Mapped[str] = mapped_column(String(120), default="")
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PartMovement(Base):
    """Ombor harakati: kirim (+) / sarf (−), ish buyrug'iga bog'lanishi mumkin."""

    __tablename__ = "part_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("spare_parts.id", ondelete="CASCADE"))
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    qty: Mapped[float] = mapped_column(Float)  # + kirim, − sarf
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    part: Mapped[SparePart] = relationship()
    author: Mapped[User] = relationship()


class UnitDayStats(Base):
    """Agregat (quvvat sensori) kunlik statistikasi: ish soatlari, ishga tushishlar, energiya."""

    __tablename__ = "unit_day_stats"
    __table_args__ = (UniqueConstraint("sensor_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_hours: Mapped[float] = mapped_column(Float, default=0.0)
    starts: Mapped[int] = mapped_column(Integer, default=0)
    energy_mwh: Mapped[float] = mapped_column(Float, default=0.0)


class Asset(Base):
    """Aktiv (agregat, transformator…): IFC element + quvvat sensori, texnik xizmat rejimi."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    element_guid: Mapped[str | None] = mapped_column(String(32), nullable=True)
    power_sensor_id: Mapped[int | None] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True
    )
    base_run_hours: Mapped[float] = mapped_column(Float, default=0.0)  # tizimgacha to'plangan
    maintenance_interval_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_maintenance_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    run_hours_at_maintenance: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Holat monitoringi sozlamalari: {vibration_sensor_id, bearing_temp_sensor_id, machine_group (1–4),
    # temp_warn, temp_alarm, rated_speed_rpm, runner_elev_m, turbine_type}
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReadingHourly(Base):
    """Tarix agregati (historian): har sensor uchun soatlik o'rtacha/min/max. Uzoq davr grafiklari
    va hisobotlar shu jadvaldan; xom o'lchovlar retention muddatidan keyin o'chiriladi."""

    __tablename__ = "readings_hourly"
    __table_args__ = (UniqueConstraint("sensor_id", "hour"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    n: Mapped[int] = mapped_column(Integer)
    avg: Mapped[float] = mapped_column(Float)
    min: Mapped[float] = mapped_column(Float)
    max: Mapped[float] = mapped_column(Float)


class Notification(Base):
    """Ilova ichidagi bildirishnoma (qo'ng'iroq): tasdiqlash, issue, alarm, tizim."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # review|issue|alarm|system
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
