"""Import all models to register migration metadata."""

from app.models.alert import Alert
from app.models.analytics import Analytics
from app.models.ingestion_run import IngestionRun
from app.models.maintenance_record import MaintenanceRecord
from app.models.physics import PhysicsCheckpoint, PhysicsEvent, PhysicsProfile, PhysicsRecord
from app.models.live_physics_demo import LivePhysicsDemoEvent
from app.models.telemetry import Telemetry
from app.models.transformer import Transformer
from app.models.processing import IngestionReceipt, MLCheckpoint

__all__ = ["Alert", "Analytics", "IngestionRun", "MaintenanceRecord", "Telemetry", "Transformer", "IngestionReceipt", "MLCheckpoint"]

__all__ += ["PhysicsCheckpoint", "PhysicsEvent", "PhysicsProfile", "PhysicsRecord"]
__all__ += ["LivePhysicsDemoEvent"]
