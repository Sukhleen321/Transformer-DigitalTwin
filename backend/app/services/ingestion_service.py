"""One semantic write path, with transaction-private H01 candidates."""
import logging
from collections import deque
from datetime import timedelta
from typing import Any
from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.telemetry import Telemetry
from app.ml_client.factory import get_ml_client
from app.ml_client.python_client import PythonMLTwinClient
from app.ml_client.safe import safe_analyze
from app.repositories import analytics_repo, ingestion_run_repo, telemetry_repo, transformer_repo, processing_repo
from app.schemas.analytics import AnalyticsOut
from app.schemas.ingestion import IngestionSummary, IngestResult
from app.schemas.quality import compute_data_quality_score, compute_is_missing_critical
from app.schemas.telemetry import TelemetryIn
from app.schemas.transformer import TransformerOut
from app.services import hooks, transactional_ml, ingestion_diagnostics
from app.services.quality_stats import parse_records
from app.services.semantic_payload import digest

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1000


def _conflict_receipt(session, conflict):
    """Called after rollback, only against an already durable accepted row."""
    record = conflict.record
    accepted = session.scalar(select(Telemetry).where(
        Telemetry.transformer_id == record.transformer_id, Telemetry.timestamp == record.timestamp))
    if accepted is not None:
        processing_repo.save_receipt(session, record, digest(record), accepted,
            status='CONFLICT', outcome='CONFLICT', accepted_hash=conflict.accepted_hash,
            ml_status=accepted.ml_status, reason=conflict.reason)
    session.commit()


def ingest_record(session: Session, record: TelemetryIn, *, run_ml=True,
                  _transformer=None, _history=None, _commit=True,
                  reanalyze_missing=False, _chunk=None) -> IngestResult:
    # reanalyze_missing is retained for call compatibility, never an implicit live replay.
    snapshot = digest(record)
    prepared_forward = False
    ingestion_diagnostics.increment('received')
    ingestion_diagnostics.increment('validated')
    try:
        transactional_ml.lock_assets(session, [record.transformer_id])
        if record.acquisition and record.acquisition.source_kind == 'REPLAYED':
            asset = transformer_repo.get(session, record.transformer_id)
            if asset is None:
                raise HTTPException(422, 'Replay destination must be a registered separate asset')
        else:
            asset = transformer_repo.ensure_transformer(session, record.transformer_id)
        transformer = _transformer or TransformerOut.model_validate(asset)
        transformer_repo.lock_for_ingestion(session, record.transformer_id)
        supplied = record.acquisition.snapshot_id if record.acquisition else None
        if supplied is not None and supplied != snapshot:
            accepted = processing_repo.receipt(session, supplied)
            if accepted is not None:
                raise telemetry_repo.SemanticConflict(record, accepted.payload_hash)
            raise HTTPException(422, 'Snapshot ID must equal the canonical semantic payload hash')
        missing = compute_is_missing_critical(record)
        telemetry, duplicate = telemetry_repo.insert_telemetry(
            session, record, schema_version=record.schema_version, is_missing_critical=missing,
            data_quality_score=compute_data_quality_score(record))
        analytics_out = None
        warnings = ['MISSING_CRITICAL'] if missing else []
        outcome = 'EXACT_RETRY' if duplicate else 'ACCEPTED'
        if duplicate:
            analytics = analytics_repo.get_for_telemetry(session, telemetry.id)
            if analytics is not None and not analytics.error_detail:
                analytics_out = AnalyticsOut.model_validate(analytics)
            if telemetry.ingestion_outcome == 'REJECTED_LATE_OBSERVATION':
                outcome = telemetry.ingestion_outcome
        else:
            telemetry.ingestion_outcome = outcome
            telemetry.ml_status = 'UNAVAILABLE'
            telemetry.ml_error = 'ML_NOT_REQUESTED'
            latest = session.scalar(select(Telemetry.timestamp).where(
                Telemetry.transformer_id == record.transformer_id,
                Telemetry.id != telemetry.id,
                or_(Telemetry.ingestion_outcome == 'ACCEPTED',
                    Telemetry.ingestion_outcome.is_(None))).order_by(Telemetry.timestamp.desc()).limit(1))
            if latest is not None and record.timestamp < latest:
                outcome = 'REJECTED_LATE_OBSERVATION'
                telemetry.ml_error = outcome
                warnings.append(outcome)
            elif run_ml:
                ml_result = None
                try:
                    client = get_ml_client()
                    if isinstance(client, PythonMLTwinClient):
                        ml_result, prepared_outcome = transactional_ml.prepare(
                            session, client, transformer, record, _history)
                        prepared_forward = prepared_outcome == 'ACCEPTED'
                        if prepared_outcome == 'CONFLICT':
                            raise telemetry_repo.SemanticConflict(record, 'checkpoint identity conflict')
                        if prepared_outcome == 'REJECTED_LATE_OBSERVATION':
                            outcome = prepared_outcome
                            telemetry.ml_error = outcome
                    elif get_settings().ml_backend == 'http':
                        telemetry.ml_error = 'REMOTE_TRANSACTIONAL_STATE_UNSUPPORTED'
                    elif record.schema_version == '1.1.0' and client.__class__.__name__ == 'StubMLTwinClient':
                        telemetry.ml_error = 'ML_STUB_NOT_OPERATIONAL'
                    else:
                        # The existing stub is stateless. A remote stateful runtime needs
                        # an explicit prepare/install protocol before it can be accepted.
                        history = _history if _history is not None else telemetry_repo.load_history(
                            session, record.transformer_id, record.timestamp, get_settings().ml_history_window)
                        ml_result = safe_analyze(client, transformer, record, history)
                except (SQLAlchemyError, telemetry_repo.SemanticConflict):
                    raise
                except Exception as exc:
                    telemetry.ml_error = ('CHECKPOINT_RESTORE_FAILED' if 'checkpoint' in str(exc).lower()
                                          else 'ML_UNAVAILABLE')
                    logger.warning('ML unavailable asset=%s error_type=%s',
                                   record.transformer_id, type(exc).__name__)
                if ml_result is not None and not ml_result.error_detail:
                    analytics, created = analytics_repo.insert_analytics(session, telemetry.id, ml_result)
                    analytics_out = AnalyticsOut.model_validate(analytics)
                    telemetry.ml_status = ('AVAILABLE' if ml_result.inference_status == 'OK'
                                           else 'INSUFFICIENT_DATA')
                    telemetry.ml_error = None
                    if created:
                        # Alert and maintenance writes share the transaction. A failed
                        # effect must roll back both SQL and the prepared ML candidate.
                        hooks.evaluate_alerts(session, telemetry, analytics)
                elif ml_result is not None:
                    telemetry.ml_error = 'ML_UNAVAILABLE'
            telemetry.ingestion_outcome = outcome
            if analytics_out is None and outcome == 'ACCEPTED':
                hooks.evaluate_alerts(session, telemetry, None)
        receipt_ml_status = telemetry.ml_status or (
            ('AVAILABLE' if analytics_out.inference_status == 'OK' else 'INSUFFICIENT_DATA')
            if analytics_out else 'UNAVAILABLE')
        if receipt_ml_status == 'UNAVAILABLE':
            warnings.append('ML_UNAVAILABLE')
        elif receipt_ml_status == 'INSUFFICIENT_DATA':
            warnings.append('INSUFFICIENT_DATA')
        if outcome != 'REJECTED_LATE_OBSERVATION':
            processing_repo.save_receipt(session, record, snapshot, telemetry,
                outcome=outcome, ml_status=receipt_ml_status)
            session.info.setdefault('h02_pending_receipts', set()).add(snapshot)
        if get_settings().physics_enabled:
            from app.services.physics_service import prepare as prepare_physics
            prepare_physics(session, telemetry, duplicate=duplicate)
        if get_settings().live_physics_demo_enabled:
            from app.services.demo_telemetry import prepare as prepare_demo
            prepare_demo(session, telemetry, duplicate=duplicate)
        result = IngestResult(telemetry_id=telemetry.id, duplicate=duplicate,
            analytics=analytics_out, warnings=warnings, snapshot_id=snapshot, ingestion_outcome=outcome)
        session.info[transactional_ml.KEY]['results'].append(result)
        if prepared_forward and analytics_out is not None:
            session.info[transactional_ml.KEY].setdefault('forward_results', {})[id(result)] = record.transformer_id
        if _commit:
            session.commit()
        return result
    except telemetry_repo.SemanticConflict as exc:
        ingestion_diagnostics.increment('conflicted')
        if not _commit:
            raise
        session.rollback()
        _conflict_receipt(session, exc)
        raise HTTPException(409, {'code': exc.reason, 'snapshot_id': snapshot,
                                  'accepted_payload_hash': exc.accepted_hash}) from exc
    except Exception:
        ingestion_diagnostics.increment('failed')
        if _commit:
            session.rollback()
        raise


def ingest_batch(session: Session, rows: list[dict[str, Any]], *,
                 run_ml=True, source_name='api') -> IngestionSummary:
    settings = get_settings()
    if len(rows) > settings.max_batch_size:
        raise ValueError('Batch exceeds MAX_BATCH_SIZE')
    records, stats = parse_records(rows, source_name)
    records.sort(key=lambda row: (row.transformer_id, row.timestamp))
    run = ingestion_run_repo.create_run(session, source_name, settings.schema_version, len(rows))
    run_id = run.id
    session.commit()
    committed_inserted = committed_duplicates = 0
    try:
        for start in range(0, len(records), CHUNK_SIZE):
            chunk = records[start:start + CHUNK_SIZE]
            transactional_ml.lock_assets(session, [row.transformer_id for row in chunk])
            histories = {}
            if run_ml:
                for asset in sorted({row.transformer_id for row in chunk}):
                    samples = [row for row in chunk if row.transformer_id == asset]
                    histories[asset] = (deque(), deque(telemetry_repo.load_batch_history(
                        session, asset, samples[0].timestamp, samples[-1].timestamp,
                        settings.ml_history_window)))
            for record in chunk:
                history = []
                if run_ml:
                    window, stored = histories[record.transformer_id]
                    while stored and stored[0].timestamp < record.timestamp:
                        row = stored.popleft()
                        if not window or window[-1].timestamp < row.timestamp:
                            window.append(row)
                    cutoff = record.timestamp - timedelta(hours=1)
                    while len(window) > 1 and window[1].timestamp < cutoff:
                        window.popleft()
                    while len(window) > settings.ml_history_window:
                        window.popleft()
                    history = list(window)
                result = ingest_record(session, record, run_ml=run_ml, _commit=False, _history=history)
                if result.duplicate:
                    stats.duplicate_count += 1
                else:
                    stats.inserted_count += 1
                    if run_ml and result.ingestion_outcome == 'ACCEPTED':
                        window.append(record)
            ingestion_run_repo.update_run(session, run_id, stats.values(), 'RUNNING')
            session.commit()
            committed_inserted, committed_duplicates = stats.inserted_count, stats.duplicate_count
        ingestion_run_repo.update_run(session, run_id, stats.values(), 'COMPLETED')
        session.commit()
        return stats.summary(run_id)
    except Exception as exc:
        session.rollback()
        stats.inserted_count, stats.duplicate_count = committed_inserted, committed_duplicates
        ingestion_run_repo.update_run(session, run_id, stats.values(), 'FAILED')
        session.commit()
        if isinstance(exc, telemetry_repo.SemanticConflict):
            _conflict_receipt(session, exc)
            raise HTTPException(409, {'code': exc.reason, 'snapshot_id': digest(exc.record)}) from exc
        raise
