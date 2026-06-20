"""Tests unitaires — Modèles de données (Couche 0)."""
import pytest
from datetime import timezone

from fce.models.data_object import (
    ClassificationLevel,
    NetworkDomain,
    ProvenanceRecord,
    SensorDataPacket,
    SensorType,
)


class TestClassificationLevel:
    def test_ordering(self):
        assert ClassificationLevel.UNCLASSIFIED < ClassificationLevel.PROTECTED_A
        assert ClassificationLevel.PROTECTED_A < ClassificationLevel.PROTECTED_B
        assert ClassificationLevel.PROTECTED_B < ClassificationLevel.SECRET
        assert ClassificationLevel.SECRET < ClassificationLevel.TOP_SECRET

    def test_dominance_principle(self):
        levels = [
            ClassificationLevel.PROTECTED_B,
            ClassificationLevel.UNCLASSIFIED,
            ClassificationLevel.SECRET,
            ClassificationLevel.PROTECTED_A,
        ]
        assert max(levels) == ClassificationLevel.SECRET

    def test_label(self):
        assert ClassificationLevel.PROTECTED_B.label() == "Protégé B"
        assert ClassificationLevel.UNCLASSIFIED.label() == "Non classifié"

    def test_all_levels_have_labels(self):
        for level in ClassificationLevel:
            assert isinstance(level.label(), str)
            assert len(level.label()) > 0


class TestProvenanceRecord:
    def test_valid_creation(self):
        prov = ProvenanceRecord(
            sensor_id="UAS-001",
            sensor_type=SensorType.UAS,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.PROTECTED_NET,
        )
        assert prov.sensor_id == "UAS-001"
        assert prov.sensor_type == SensorType.UAS
        assert prov.record_id  # UUID auto-généré
        assert prov.ingestion_timestamp.tzinfo == timezone.utc

    def test_unique_record_ids(self):
        prov1 = ProvenanceRecord(
            sensor_id="S1", sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.UNCLASSIFIED,
            origin_domain=NetworkDomain.UNCLASSIFIED_NET,
        )
        prov2 = ProvenanceRecord(
            sensor_id="S2", sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.UNCLASSIFIED,
            origin_domain=NetworkDomain.UNCLASSIFIED_NET,
        )
        assert prov1.record_id != prov2.record_id

    def test_invalid_sensor_type(self):
        with pytest.raises(ValueError, match="Type de capteur invalide"):
            ProvenanceRecord(
                sensor_id="X1",
                sensor_type="INVALID_SENSOR",
                classification=ClassificationLevel.UNCLASSIFIED,
                origin_domain=NetworkDomain.UNCLASSIFIED_NET,
            )

    def test_empty_sensor_id(self):
        with pytest.raises(ValueError, match="sensor_id ne peut pas être vide"):
            ProvenanceRecord(
                sensor_id="   ",
                sensor_type=SensorType.UAS,
                classification=ClassificationLevel.UNCLASSIFIED,
                origin_domain=NetworkDomain.UNCLASSIFIED_NET,
            )

    def test_invalid_domain(self):
        with pytest.raises(ValueError, match="Domaine réseau invalide"):
            ProvenanceRecord(
                sensor_id="S1",
                sensor_type=SensorType.UAS,
                classification=ClassificationLevel.UNCLASSIFIED,
                origin_domain="INVALID_DOMAIN",
            )

    def test_default_empty_lists(self):
        prov = ProvenanceRecord(
            sensor_id="S1", sensor_type=SensorType.UAS,
            classification=ClassificationLevel.UNCLASSIFIED,
            origin_domain=NetworkDomain.UNCLASSIFIED_NET,
        )
        assert prov.dissemination_controls == []
        assert prov.handling_caveats == []
        assert prov.lineage == []


class TestSensorDataPacket:
    def test_create_factory(self):
        pkt = SensorDataPacket.create(
            sensor_id="RADAR-001",
            sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.PROTECTED_A,
            origin_domain=NetworkDomain.PROTECTED_NET,
            payload={"value": 42},
            dissemination_controls=["REL TO CAN"],
        )
        assert pkt.provenance.sensor_id == "RADAR-001"
        assert pkt.payload == {"value": 42}
        assert pkt.provenance.dissemination_controls == ["REL TO CAN"]

    def test_lineage_tracking(self):
        parent = SensorDataPacket.create(
            sensor_id="P1", sensor_type=SensorType.UAS,
            classification=ClassificationLevel.UNCLASSIFIED,
            origin_domain=NetworkDomain.UNCLASSIFIED_NET,
            payload=None,
        )
        child = SensorDataPacket.create(
            sensor_id="C1", sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.PROTECTED_A,
            origin_domain=NetworkDomain.PROTECTED_NET,
            payload=None,
            lineage=[parent.provenance.record_id],
        )
        assert parent.provenance.record_id in child.provenance.lineage

    def test_all_sensor_types(self):
        for sensor_type in SensorType.ALL:
            pkt = SensorDataPacket.create(
                sensor_id=f"{sensor_type}-TEST",
                sensor_type=sensor_type,
                classification=ClassificationLevel.UNCLASSIFIED,
                origin_domain=NetworkDomain.UNCLASSIFIED_NET,
                payload=None,
            )
            assert pkt.provenance.sensor_type == sensor_type
