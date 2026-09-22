"""Barcha jadvallar bitta joyda (aylanma import bo'lmasligi uchun)."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
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
    text,
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
    # L1: ketma-ket noto'g'ri urinishlar → vaqtincha bloklash (DB da — replikalar orasida umumiy)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # L1: TOTP (RFC 6238); secret o'rnatilgan, lekin enabled=False — sozlash kutilmoqda
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # oxirgi qabul qilingan TOTP hisoblagichi — bir kodni ikki marta ishlatishni rad etish
    mfa_last_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # L2: token versiyasi — parol/rol o'zgarsa yoki hamma sessiya bekor qilinsa oshadi; JWT `ver` mos kelishi shart
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # L2: admin bergan/boshlang'ich parol — birinchi kirishda almashtirish shart (boshqa endpointlar 403)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    """Kirish sessiyasi (L2): refresh token `jti` bilan; aylantirilganda eski `prev_jti` da qoladi
    (takror ishlatilsa — o'g'irlangan token belgisi)."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(48), unique=True)
    prev_jti: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    client: Mapped[str] = mapped_column(String(16), default="web")  # web | desktop | gateway
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str] = mapped_column(String(32), default="")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(256), default="")
    # G2: IDS tekshiruvi yiqilgan versiya tasdiqlanmaydi/merge qilinmaydi (default: faqat ogohlantirish)
    ids_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # G4 (ISO 19650): konteyner nomlash shabloni ({project}-{originator}-{volume}-{level}-{type}-{role}-{number});
    # naming_required — mos kelmasa yuklash rad etiladi (aks holda ogohlantirish)
    naming_template: Mapped[str] = mapped_column(String(128), default="", server_default="")
    naming_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # G3: georeferensiya — EPSG (UTM 326xx/327xx, Pulkovo GK 284xx), lokal (0,0,0) ning global joyi, X o'qi burilishi
    epsg_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin_e: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_n: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    crs_rotation_deg: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    # SCADA/gateway o'lchovlarni yuborishi uchun kalit (X-Ingest-Key sarlavhasi) — faqat POST /readings
    ingest_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingest_key_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingest_key_last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Buyruq kanali kaliti (X-Command-Key): /commands/claim, /ack, /readback — alohida rotatsiya/audit (B3)
    command_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    command_key_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    command_key_last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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


class Federation(Base):
    """Model federatsiyasi (G5): loyihaning bir necha model versiyasi bitta koordinata fazosida —
    members: [{model_id, version_id|null, dx, dy, dz, rot_deg}] (lokal metr; CRS loyihaniki)."""

    __tablename__ = "federations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    members: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectDocument(Base):
    """ISO 19650 hujjatlari (G4): EIR, BEP, TIDP/MIDP va boshqalar — loyihaga biriktirilgan fayllar."""

    __tablename__ = "project_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="other")  # eir | bep | tidp | midp | other
    title: Mapped[str] = mapped_column(String(256))
    file_name: Mapped[str] = mapped_column(String(256))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)
    ext: Mapped[str] = mapped_column(String(16), default="")
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    uploader: Mapped[User] = relationship()


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
    # G2: IDS tekshiruvi — pass | fail | error | None (hali tekshirilmagan); to'liq natija (talablar, yiqilgan elementlar)
    ids_status: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ids_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # G4 (ISO 19650): yaroqlilik kodi (S0–S7, A1–An, B1–Bn, CR, PR) va reviziya (P01…/C01…) — `tag` dan ajratilgan
    suitability_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    revision_code: Mapped[str | None] = mapped_column(String(6), nullable=True)

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
    # L3: navbat ijarasi — atomik claim, ijara muddati, urinishlar; idempotentlik kaliti (muallif bo'yicha)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    author: Mapped[User] = relationship()

    __table_args__ = (UniqueConstraint("author_id", "idempotency_key", name="uq_sim_jobs_idem"),)


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Job(Base):
    """Hosilaviy ish navbati (L3): fragments/geometriya konvertatsiyasi va boshqa fon ishlar — restartda
    yo'qolmaydi, ijara bilan claim qilinadi, `idempotency_key` takrorni oldini oladi (masalan `fragments:<sha>`)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, length=16), default=JobStatus.queued, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


# O'lchov sifati (OPC UA StatusCode / IEC 61850 quality ga mos soddalashtirilgan to'plam):
# good — haqiqiy o'lchov; uncertain — shubhali (aloqa/diapazon); bad — yaroqsiz (alarm baholanmaydi,
# last_value yangilanmaydi); substituted — o'rnini bosuvchi (hisoblangan/oldingi); manual — qo'lda kiritilgan
QUALITIES = ("good", "uncertain", "bad", "substituted", "manual")


# O'lchov sifati (OPC UA StatusCode / IEC 61850 quality ga mos soddalashtirilgan to'plam):
# good — haqiqiy o'lchov; uncertain — shubhali (aloqa/diapazon); bad — yaroqsiz (alarm baholanmaydi,
# last_value yangilanmaydi); substituted — o'rnini bosuvchi (hisoblangan/oldingi); manual — qo'lda kiritilgan
QUALITIES = ("good", "uncertain", "bad", "substituted", "manual")


# O'lchov sifati (OPC UA StatusCode / IEC 61850 quality ga mos soddalashtirilgan to'plam):
# good — haqiqiy o'lchov; uncertain — shubhali (aloqa/diapazon); bad — yaroqsiz (alarm baholanmaydi,
# last_value yangilanmaydi); substituted — o'rnini bosuvchi (hisoblangan/oldingi); manual — qo'lda kiritilgan
QUALITIES = ("good", "uncertain", "bad", "substituted", "manual")


class AlarmState(str, enum.Enum):
    """Sensor alarm holati (ISA-18.2 chegara alarmlari, C1): L/H, LL/HH, o'zgarish tezligi, og'ish."""

    ok = "ok"
    low = "low"  # L
    high = "high"  # H
    stale = "stale"  # ma'lumot kelmayapti — faqat AlarmEvent da (Sensor.stale bayrog'i alohida, F4)
    lowlow = "lowlow"  # LL
    highhigh = "highhigh"  # HH
    roc = "roc"  # rate-of-change: |dv/dt| > roc_limit_per_min
    deviation = "deviation"  # egizak/model bilan og'ish (kind="deviation" sensorlar)


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
    # H1: o'lchov nuqtasining KKS kodi (masalan 1MKA10 CT001) — O&M hujjatlari, chizmalar bilan bir xil
    kks_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    # Chegaralar (C1): low_alarm = L, high_alarm = H; ll_alarm = LL, hh_alarm = HH
    low_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ll_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    hh_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    # O'lik zona (sensor birligida): alarmdan qaytish uchun chegaradan shuncha ichkariga kirishi kerak
    deadband: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    # Kechikishlar: chegaradan chiqish on_delay_s davomida saqlansa alarm; qaytish off_delay_s dan keyin
    on_delay_s: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    off_delay_s: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # O'zgarish tezligi alarmi (birlik/daqiqa), None — o'chiq
    roc_limit_per_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Arxiv siqishi (D2): oxirgi yozilgan qiymatdan o'zgarish shundan kichik bo'lsa xom qator yozilmaydi
    # (holat/alarm baribir yangilanadi); archive_max_interval_s dan keyin majburiy yozuv. None — o'chiq.
    archive_deadband: Mapped[float | None] = mapped_column(Float, nullable=True)
    archive_max_interval_s: Mapped[int] = mapped_column(Integer, default=3600, server_default="3600")
    last_archived_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_archived_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Kechikish holat mashinasi: kutilayotgan holat va qachondan beri
    alarm_pending: Mapped[str | None] = mapped_column(String(16), nullable=True)
    alarm_pending_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ISA-18.2 alarm rejimi (C2): normal | shelved (muddatli, operator) | out_of_service (muhandis).
    # Rejim normal bo'lmasa hodisa jurnalga `suppressed` belgisi bilan yoziladi, bildirishnoma yo'q.
    alarm_mode: Mapped[str] = mapped_column(String(24), default="normal", server_default="normal")
    alarm_mode_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alarm_mode_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    alarm_mode_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    alarm_mode_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Suppression-by-design: shart ifodasi (interlock sintaksisi, masalan `AGG1_RUN == 0`) rost bo'lsa
    # alarm bostiriladi; natija `suppressed` da (ingest da baholanadi)
    suppress_condition: Mapped[str] = mapped_column(Text, default="", server_default="")
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Ratsionalizatsiya (ISA-18.2 §10, C3): sabab, harakatsizlik oqibati, tuzatuvchi harakat, javob vaqti,
    # ustuvorlik asosi; kim/qachon tasdiqlagan. Chegara o'zgarsa qayta ko'rib chiqiladi (rationalized_at=None).
    cause: Mapped[str] = mapped_column(Text, default="", server_default="")
    consequence: Mapped[str] = mapped_column(Text, default="", server_default="")
    corrective_action: Mapped[str] = mapped_column(Text, default="", server_default="")
    response_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_basis: Mapped[str] = mapped_column(Text, default="", server_default="")
    rationalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rationalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Fizik (o'lchov) diapazoni: tashqaridagi qiymat quality=bad bilan saqlanadi, holatga ta'sir qilmaydi
    min_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    stale_after_s: Mapped[int] = mapped_column(Integer, default=600)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Alarm ustuvorligi: low|medium|high|critical (critical/high — ovoz + email)
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    # Boshqaruv nuqtasi (setpoint/rele): dispetcher buyruq yuboradi, gateway SCADA ga yozadi
    writable: Mapped[bool] = mapped_column(Boolean, default=False)
    # Buyruq xavfsizlik konverti (B1): ruxsat etilgan diapazon, o'zgarish tezligi, ikki kishi tasdig'i, TTL
    min_setpoint: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_setpoint: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_rate_per_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_dual_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    command_ttl_s: Mapped[int] = mapped_column(Integer, default=300, server_default="300")
    # Readback: gateway yozgandan keyin o'qigan qiymat buyruqdan shu nisbiy chegaradan ko'p farq qilsa mismatch
    readback_tolerance: Mapped[float] = mapped_column(Float, default=0.01, server_default="0.01")
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # oxirgi qabul qilingan (bad bo'lmagan) qiymatning sifati — QUALITIES
    last_quality: Mapped[str] = mapped_column(String(16), default="good", server_default="good")
    # Jarayon alarm holati (F4: aloqa holatidan ajratilgan — aloqa uzilsa ham faol alarm yashirinmaydi)
    alarm: Mapped[AlarmState] = mapped_column(Enum(AlarmState, length=16), default=AlarmState.ok)
    # Aloqa yo'q / eskirgan: stale_after_s dan beri ma'lumot kelmagan (fon tekshiruvi); yangi sensor — stale
    stale: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def has_alarm_limits(self) -> bool:
        """Sensor alarm ta'rifi bormi (ratsionalizatsiya talab qilinadi)."""
        return any(
            v is not None
            for v in (self.low_alarm, self.high_alarm, self.ll_alarm, self.hh_alarm, self.roc_limit_per_min)
        )


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_sensor_ts", "sensor_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[float] = mapped_column(Float)
    # QUALITIES; bad qiymat tarixda qoladi, lekin agregat/alarm/egizak uni ishlatmaydi
    quality: Mapped[str] = mapped_column(String(16), default="good", server_default="good")
    # manbadagi vaqt tamg'asi (OPC UA SourceTimestamp, gateway o'qish vaqti); yo'q bo'lsa ts
    src_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlarmEvent(Base):
    """Alarm jurnali: sensor holati ok dan chiqqanda ochiladi, ok ga qaytganda yopiladi;
    dispetcher kvitlaydi (ack)."""

    __tablename__ = "alarm_events"
    __table_args__ = (
        Index("ix_alarm_events_project_started", "project_id", "started_at"),
        # har alarm o'tishida ochiq hodisa qidiriladi (live.transition)
        Index("ix_alarm_events_sensor_open", "sensor_id", "ended_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    state: Mapped[AlarmState] = mapped_column(Enum(AlarmState, length=16))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    # Ochilganda sensor rejimi normal bo'lmagan: shelved | out_of_service | suppressed_by_design.
    # Jurnalda qoladi (KPI alohida hisoblaydi), lekin ko'rsatilmaydi/bildirilmaydi.
    suppressed: Mapped[str | None] = mapped_column(String(24), nullable=True)

    sensor: Mapped[Sensor] = relationship()

    @property
    def alarm_state(self) -> str:
        """ISA-18.2 alarm holati: unack → acked → (rtn_unack) → normal."""
        if self.suppressed:
            return self.suppressed
        if self.ended_at is None:
            return "unack" if self.acked_at is None else "acked"
        return "rtn_unack" if self.acked_at is None else "normal"


class CommandStatus(str, enum.Enum):
    pending = "pending"  # gateway hali olmagan
    sent = "sent"  # gateway oldi, SCADA ga yozmoqda
    acked = "acked"  # bajarildi
    failed = "failed"  # gateway xatosi yoki watchdog (sent da javob kelmadi)
    cancelled = "cancelled"
    expired = "expired"  # gateway olmasdan TTL o'tdi
    pending_approval = "pending_approval"  # ikki kishi tasdig'i kutilmoqda (B2)
    mismatch = "mismatch"  # readback: PLC dagi qiymat buyruqqa mos kelmadi (B2)


class Command(Base):
    """Supervisory control: dispetcher buyrug'i (setpoint/rele) → gateway → SCADA. Har qadam audit."""

    __tablename__ = "commands"
    __table_args__ = (
        Index("ix_commands_project_status", "project_id", "status"),
        # Bitta sensorga bir vaqtda faqat bitta ochiq (pending/sent) buyruq — TOCTOU DB darajasida yopiladi
        Index(
            "uq_commands_sensor_open",
            "sensor_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'sent')"),
            postgresql_where=text("status IN ('pending', 'sent')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    value: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(String(200), default="")
    # TTL: shu vaqtgacha gateway olmasa → expired (eskirgan setpoint bajarilmasin); sent_at — watchdog uchun
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # B2: ikki kishi tasdig'i va readback
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    readback_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    readback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CommandStatus] = mapped_column(
        Enum(CommandStatus), default=CommandStatus.pending
    )
    result: Mapped[str] = mapped_column(String(400), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sensor: Mapped[Sensor] = relationship()
    author: Mapped[User] = relationship(foreign_keys=[created_by])
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by])


class Interlock(Base):
    """Texnologik blokirovka (B4): boshqariladigan sensor uchun shart ifodasi (ges_sim.custom, faqat
    sensor qiymatlari ustida). Shart False → buyruq 409; chetlab o'tish faqat tasdiqlovchi, audit + alarm."""

    __tablename__ = "interlocks"
    __table_args__ = (Index("ix_interlocks_sensor", "sensor_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    # masalan: "AGG1_RUN == 0 and RES_H > 890" (sensor kalitlari identifikatorga keltirilgan, `value` — buyruq)
    condition: Mapped[str] = mapped_column(String(1000))
    message: Mapped[str] = mapped_column(String(300), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sensor: Mapped[Sensor] = relationship()


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
    """Aktiv (agregat, transformator…): IFC element + quvvat sensori, texnik xizmat rejimi; H1: ierarxiya (KKS)."""

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("project_id", "kks_code", name="uq_assets_kks"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    element_guid: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # H1: ierarxiya va kodlash — ota aktiv, KKS/RDS-PP kodi (loyihada unikal), ISO 14224 taksonomiya darajasi
    # (plant → system → equipment → component → part), funksional joylashuv (matn)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    kks_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    taxonomy_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    function_location: Mapped[str] = mapped_column(String(128), default="", server_default="")
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


class AssetDocument(Base):
    """Aktiv hujjatlari (G6): qo'llanma, pasport, zavod sinov protokoli, ishga tushirish akti."""

    __tablename__ = "asset_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="other")  # manual | passport | test | commissioning | other
    title: Mapped[str] = mapped_column(String(256))
    file_name: Mapped[str] = mapped_column(String(256))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)
    ext: Mapped[str] = mapped_column(String(16), default="")
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    uploader: Mapped[User] = relationship()


class ReadingAgg(Base):
    """Oraliq qatlamlar (D2): 1 daqiqa (`1m`) va 10 daqiqa (`10m`) agregatlari — raw o'chirilgach ham
    avariyadan keyingi tahlil uchun; har qatlamning o'z saqlash muddati (config)."""

    __tablename__ = "readings_agg"
    __table_args__ = (
        UniqueConstraint("sensor_id", "tier", "bucket"),
        Index("ix_readings_agg_tier_bucket", "tier", "bucket"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    tier: Mapped[str] = mapped_column(String(4))  # 1m | 10m
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    n: Mapped[int] = mapped_column(Integer)
    avg: Mapped[float] = mapped_column(Float)
    min: Mapped[float] = mapped_column(Float)
    max: Mapped[float] = mapped_column(Float)
    pct_good: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    n_bad: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


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
    # soat ichida good ulushi (0..1) va bad soni — n ga faqat bad bo'lmaganlar kiradi
    pct_good: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    n_bad: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    n_bad: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


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
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # Hash zanjiri (audit.py): prev_hash — oldingi qatorning row_hash i ("" birinchisi uchun)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ShiftHandover(Base):
    """Smena topshirish varaqasi (F9): avtomatik tuzilgan mazmun (summary JSON), izohlar, topshiruvchi va qabul
    qiluvchining imzosi (vaqt + audit). status: handed (topshirildi, qabul kutilmoqda) | received."""

    __tablename__ = "shift_handovers"
    __table_args__ = (Index("ix_shift_project_id", "project_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="handed")
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # smena boshi
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    handed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    handed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receive_notes: Mapped[str] = mapped_column(Text, default="")

    hander: Mapped[User] = relationship(foreign_keys=[handed_by])
    receiver: Mapped[User | None] = relationship(foreign_keys=[received_by])


class SequenceEvent(Base):
    """SOE — hodisalar ketma-ketligi (D3): millisekundli diskret hodisalar (trip, uzgich, zatvor STUCK);
    agregat qilinmaydi, o'z saqlash muddati (GES_SOE_RETENTION_DAYS). Takror — unikal kalit bilan tashlanadi."""

    __tablename__ = "soe_events"
    __table_args__ = (
        UniqueConstraint("project_id", "source", "point", "ts_ms", "state", name="uq_soe_event"),
        Index("ix_soe_project_ts", "project_id", "ts_ms"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(32), default="gateway")  # gateway | iec104 | sim | manual
    point: Mapped[str] = mapped_column(String(64))  # AGG1.PROT, AGG1.CB, GATE1 …
    state: Mapped[str] = mapped_column(String(32))  # TRIP, OPEN, CLOSE, STUCK, 1/0 …
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ts_ms: Mapped[int] = mapped_column(BigInteger)  # epoch ms — tartib va aniqlik
    quality: Mapped[str] = mapped_column(String(16), default="good")
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemState(Base):
    """Fon vazifalar holati (C5): restartdan keyin ham saqlanadi — masalan oxirgi soatlik/kunlik ish
    vaqti (`bg.last_hour`), kunlik hisobot crash-loop da qayta yuborilmasin."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
