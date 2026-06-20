"""Tests unitaires — Couche 3 : Détecteur ML + Journal d'audit."""
import json
import pickle
import pytest
from pathlib import Path

from fce.ml.anomaly_detector import AnomalyResult, ComplianceAnomalyDetector
from fce.audit.logger import AuditLogger
from fce.models.data_object import (
    ClassificationLevel,
    NetworkDomain,
    SensorDataPacket,
    SensorType,
)
from fce.policy.engine import EnforcementAction, PolicyDecision


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_packet(
    sensor_type: str = SensorType.RADAR,
    classification: ClassificationLevel = ClassificationLevel.PROTECTED_A,
    domain: str = NetworkDomain.PROTECTED_NET,
    caveats: list[str] | None = None,
    lineage: list[str] | None = None,
) -> SensorDataPacket:
    return SensorDataPacket.create(
        sensor_id=f"{sensor_type}-TEST",
        sensor_type=sensor_type,
        classification=classification,
        origin_domain=domain,
        payload=None,
        dissemination_controls=caveats or ["REL TO CAN"],
        lineage=lineage or [],
    )


def make_training_corpus(n: int = 300) -> list[SensorDataPacket]:
    """Génère un corpus d'entraînement varié mais conforme."""
    import random
    random.seed(0)
    packets = []
    configs = [
        (SensorType.RADAR,    ClassificationLevel.PROTECTED_A, NetworkDomain.PROTECTED_NET),
        (SensorType.UAS,      ClassificationLevel.UNCLASSIFIED, NetworkDomain.UNCLASSIFIED_NET),
        (SensorType.EO_IR,    ClassificationLevel.PROTECTED_B, NetworkDomain.SECRET_NET),
        (SensorType.SIGINT,   ClassificationLevel.PROTECTED_B, NetworkDomain.SECRET_NET),
        (SensorType.ACOUSTIC, ClassificationLevel.PROTECTED_A, NetworkDomain.PROTECTED_NET),
    ]
    for i in range(n):
        st, cl, dom = configs[i % len(configs)]
        packets.append(SensorDataPacket.create(
            sensor_id=f"{st}-{i:04d}",
            sensor_type=st,
            classification=cl,
            origin_domain=dom,
            payload=None,
            dissemination_controls=["REL TO CAN"],
            lineage=[],
        ))
    return packets


# ─────────────────────────────────────────────────────────────────────────────
# Tests AnomalyDetector
# ─────────────────────────────────────────────────────────────────────────────

class TestAnomalyDetectorLifecycle:
    def test_not_ready_before_fit(self):
        detector = ComplianceAnomalyDetector()
        assert not detector.is_ready

    def test_ready_after_fit(self):
        detector = ComplianceAnomalyDetector()
        detector.fit(make_training_corpus(50))
        assert detector.is_ready

    def test_fit_empty_raises(self):
        detector = ComplianceAnomalyDetector()
        with pytest.raises(ValueError, match="liste vide"):
            detector.fit([])

    def test_chainable_fit(self):
        detector = ComplianceAnomalyDetector()
        result = detector.fit(make_training_corpus(50))
        assert result is detector  # Retourne self

    def test_predict_before_fit_returns_safe_default(self):
        """Dégradation gracieuse : pas d'exception, is_anomaly=False."""
        detector = ComplianceAnomalyDetector()
        pkt = make_packet()
        result = detector.predict(pkt)
        assert isinstance(result, AnomalyResult)
        assert result.is_anomaly is False
        assert result.confidence == 0.0

    def test_save_and_load(self, tmp_path: Path):
        detector = ComplianceAnomalyDetector()
        detector.fit(make_training_corpus(100))
        save_path = tmp_path / "model.pkl"
        detector.save(save_path)
        assert save_path.exists()

        loaded = ComplianceAnomalyDetector(model_path=save_path)
        assert loaded.is_ready

    def test_save_before_fit_raises(self, tmp_path: Path):
        detector = ComplianceAnomalyDetector()
        with pytest.raises(RuntimeError, match="Aucun modèle à sauvegarder"):
            detector.save(tmp_path / "model.pkl")


class TestAnomalyDetectorPrediction:
    @pytest.fixture
    def trained_detector(self) -> ComplianceAnomalyDetector:
        detector = ComplianceAnomalyDetector(contamination=0.01)
        detector.fit(make_training_corpus(500))
        return detector

    def test_normal_packet_not_anomaly(self, trained_detector):
        """Un paquet conforme au profil d'entraînement ne doit pas être anomalie."""
        normal_pkts = make_training_corpus(10)
        anomaly_count = sum(
            1 for p in normal_pkts
            if trained_detector.predict(p).is_anomaly
        )
        # Avec contamination=0.01, au max 1-2 faux positifs sur 10
        assert anomaly_count <= 3

    def test_score_is_float(self, trained_detector):
        pkt = make_packet()
        result = trained_detector.predict(pkt)
        assert isinstance(result.anomaly_score, float)

    def test_result_has_explanation(self, trained_detector):
        pkt = make_packet()
        result = trained_detector.predict(pkt)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0

    def test_severity_none_for_normal(self, trained_detector):
        pkt = make_packet()
        result = trained_detector.predict(pkt)
        if not result.is_anomaly:
            assert result.severity == "NONE"

    def test_unknown_sensor_type_graceful(self, trained_detector):
        """Un type de capteur non vu à l'entraînement ne lève pas d'exception."""
        # On triche sur l'encodeur pour simuler un type inconnu
        pkt = make_packet()
        # Modifier le type manuellement pour bypasser la validation
        pkt.provenance.__dict__["sensor_type"] = "UNKNOWN_SENSOR"
        result = trained_detector.predict(pkt)
        assert isinstance(result, AnomalyResult)

    def test_anomaly_result_severity_levels(self):
        normal = AnomalyResult(is_anomaly=False, anomaly_score=0.1, confidence=0.0, explanation="")
        assert normal.severity == "NONE"

        low = AnomalyResult(is_anomaly=True, anomaly_score=-0.05, confidence=0.1, explanation="")
        assert low.severity == "LOW"

        medium = AnomalyResult(is_anomaly=True, anomaly_score=-0.2, confidence=0.4, explanation="")
        assert medium.severity == "MEDIUM"

        high = AnomalyResult(is_anomaly=True, anomaly_score=-0.4, confidence=0.8, explanation="")
        assert high.severity == "HIGH"


# ─────────────────────────────────────────────────────────────────────────────
# Tests AuditLogger
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def audit_logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(tmp_path / "audit.jsonl")


def make_decision(
    action: EnforcementAction = EnforcementAction.ALLOW,
    classification: ClassificationLevel = ClassificationLevel.PROTECTED_A,
) -> PolicyDecision:
    return PolicyDecision(
        action=action,
        reason="Test decision",
        applied_rules=["TEST-001"],
        resulting_classification=classification,
        operator_explanation="Explication opérateur test.",
    )


class TestAuditLogger:
    def test_record_creates_entry(self, audit_logger: AuditLogger, tmp_path: Path):
        pkt = make_packet()
        decision = make_decision()
        audit_logger.record(pkt, decision)
        assert audit_logger.entry_count == 1

    def test_log_file_created(self, tmp_path: Path):
        log_path = tmp_path / "subdir" / "audit.jsonl"
        logger = AuditLogger(log_path)
        assert log_path.exists()

    def test_jsonl_format(self, audit_logger: AuditLogger, tmp_path: Path):
        """Chaque entrée doit être du JSON valide sur une seule ligne."""
        pkt = make_packet()
        decision = make_decision()
        audit_logger.record(pkt, decision)

        log_path = tmp_path / "audit.jsonl"
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert "packet_id" in entry
        assert "action" in entry
        assert "timestamp" in entry
        assert "classification_in" in entry
        assert "classification_out" in entry

    def test_record_with_anomaly(self, audit_logger: AuditLogger):
        pkt = make_packet()
        decision = make_decision(action=EnforcementAction.RESTRICT)
        anomaly = AnomalyResult(
            is_anomaly=True,
            anomaly_score=-0.25,
            confidence=0.5,
            explanation="Anomalie test",
        )
        audit_logger.record(pkt, decision, anomaly)
        assert audit_logger.entry_count == 1

    def test_multiple_records(self, audit_logger: AuditLogger, tmp_path: Path):
        for _ in range(10):
            audit_logger.record(make_packet(), make_decision())

        log_path = tmp_path / "audit.jsonl"
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 10
        assert audit_logger.entry_count == 10

    def test_export_csv(self, audit_logger: AuditLogger, tmp_path: Path):
        for action in [EnforcementAction.ALLOW, EnforcementAction.DENY,
                       EnforcementAction.RESTRICT]:
            audit_logger.record(make_packet(), make_decision(action=action))

        csv_path = tmp_path / "export.csv"
        count = audit_logger.export_csv(csv_path)
        assert count == 3
        assert csv_path.exists()

        import csv
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3

    def test_export_csv_empty(self, tmp_path: Path):
        log_path = tmp_path / "empty.jsonl"
        logger = AuditLogger(log_path)
        count = logger.export_csv(tmp_path / "export.csv")
        assert count == 0

    def test_get_summary(self, audit_logger: AuditLogger):
        audit_logger.record(make_packet(), make_decision(EnforcementAction.ALLOW))
        audit_logger.record(make_packet(), make_decision(EnforcementAction.DENY))
        audit_logger.record(make_packet(), make_decision(EnforcementAction.RESTRICT))

        summary = audit_logger.get_summary()
        assert summary["total"] == 3
        assert summary["compliant"] == 1
        assert summary["violations"] == 2
        assert "compliance_rate" in summary
        assert abs(summary["compliance_rate"] - 33.33) < 0.1

    def test_audit_trail_append_only(self, audit_logger: AuditLogger, tmp_path: Path):
        """Les entrées ne doivent jamais être modifiées après écriture."""
        pkt = make_packet()
        decision = make_decision()
        audit_logger.record(pkt, decision)

        log_path = tmp_path / "audit.jsonl"
        content_before = log_path.read_text()

        # Enregistrement supplémentaire
        audit_logger.record(make_packet(), make_decision())
        content_after = log_path.read_text()

        # Le contenu initial est préservé
        assert content_after.startswith(content_before)
