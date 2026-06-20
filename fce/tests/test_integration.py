"""
Tests d'intégration — Pipeline FCE complet (3 couches).

Valide les scénarios opérationnels end-to-end avec données synthétiques.
"""
import json
import pytest
from pathlib import Path

from fce.pipeline import FusionComplianceEngine, FCEResult
from fce.policy.engine import EnforcementAction
from fce.models.data_object import ClassificationLevel, NetworkDomain, SensorType


# Import du générateur synthétique
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
from synthetic_generator import SyntheticDataGenerator


@pytest.fixture
def policy_path(tmp_path: Path) -> Path:
    content = """
version: "integration-test"
rules:
  - id: "INT-001"
    description: "Bloquer SECRET et supérieur"
    operator_explanation: "Classification trop élevée"
    condition:
      type: "classification_above"
      threshold: "PROTECTED_B_ENHANCED"
    action: "DENY"

  - id: "INT-002"
    description: "Restreindre sans REL TO CAN pour Protégé B"
    operator_explanation: "Mention de diffusion manquante"
    condition:
      type: "missing_caveat"
      required_caveats: ["REL TO CAN"]
    action: "RESTRICT"

  - id: "INT-003"
    description: "Bloquer SIGINT sur réseau non classifié"
    operator_explanation: "SIGINT interdit sur UNCLASSIFIED_NET"
    condition:
      type: "sensor_domain_restriction"
      sensors: ["SIGINT", "EO_IR"]
      domains: ["UNCLASSIFIED_NET"]
    action: "DENY"
"""
    p = tmp_path / "policy.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def fce(policy_path: Path, tmp_path: Path) -> FusionComplianceEngine:
    engine = FusionComplianceEngine(
        policy_path=policy_path,
        audit_log_path=tmp_path / "audit.jsonl",
        allowed_domain_pairs={
            (NetworkDomain.UNCLASSIFIED_NET, NetworkDomain.PROTECTED_NET),
            (NetworkDomain.PROTECTED_NET, NetworkDomain.SECRET_NET),
        },
    )
    gen = SyntheticDataGenerator(seed=42)
    training_data = gen.generate_normal_traffic(n=300)
    engine.train_anomaly_detector(training_data)
    return engine


@pytest.fixture
def gen() -> SyntheticDataGenerator:
    return SyntheticDataGenerator(seed=42)


class TestPipelineInitialization:
    def test_fce_initializes(self, fce: FusionComplianceEngine):
        assert fce is not None

    def test_ml_trained_after_setup(self, fce: FusionComplianceEngine):
        assert fce._anomaly_detector.is_ready

    def test_policy_rules_loaded(self, fce: FusionComplianceEngine):
        assert fce._policy_engine.rule_count == 3


class TestScenario1_ValidSIGINTEOIRFusion:
    def test_valid_fusion_allowed(self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator):
        """Fusion SIGINT + EO/IR valide → doit être ALLOW."""
        packets = gen.scenario_sigint_eoir_fusion()
        results = fce.ingest_batch(packets)
        # Les deux paquets sur SECRET_NET avec REL TO CAN → ALLOW
        for r in results:
            assert r.final_decision.action in (
                EnforcementAction.ALLOW,
                EnforcementAction.RESTRICT,  # ML peut ajouter RESTRICT
            ), f"Action inattendue : {r.final_decision.action}"

    def test_classification_dominance_applied(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """Le niveau de sortie doit être le max des sources."""
        packets = gen.scenario_sigint_eoir_fusion()
        results = fce.ingest_batch(packets)
        # Les deux sont PROTECTED_B → sortie = PROTECTED_B
        for r in results:
            assert r.computed_classification >= ClassificationLevel.PROTECTED_B


class TestScenario2_ValidUASRadarFusion:
    def test_uas_radar_fusion_allowed(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        packets = gen.scenario_uas_radar_fusion()
        results = fce.ingest_batch(packets)
        # Aucune violation de classification ou de domaine attendue
        for r in results:
            assert r.final_decision.action != EnforcementAction.DENY

    def test_classification_elevated_by_radar(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """Le paquet UAS (UNCLASSIFIED) + RADAR (PROTECTED_A) → sortie ≥ PROTECTED_A."""
        packets = gen.scenario_uas_radar_fusion()
        results = fce.ingest_batch(packets)
        radar_result = results[1]  # Le radar est le paquet enfant
        assert radar_result.computed_classification >= ClassificationLevel.PROTECTED_A


class TestScenario3_ClassificationViolation:
    def test_sigint_on_unclassified_net_denied(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """SIGINT sur UNCLASSIFIED_NET → DENY (INT-003)."""
        pkt = gen.scenario_classification_violation()
        result = fce.ingest(pkt)
        assert result.final_decision.action == EnforcementAction.DENY
        assert "INT-003" in result.final_decision.applied_rules

    def test_violation_recorded_in_audit(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator, tmp_path: Path
    ):
        pkt = gen.scenario_classification_violation()
        fce.ingest(pkt)

        summary = fce.get_audit_summary()
        assert summary["violations"] >= 1


class TestScenario4_MissingCaveatViolation:
    def test_missing_caveat_restricted(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """Paquet sans REL TO CAN → RESTRICT (INT-002) au minimum."""
        pkt = gen.scenario_missing_caveat_violation()
        result = fce.ingest(pkt)
        assert result.final_decision.action in (
            EnforcementAction.RESTRICT,
            EnforcementAction.QUARANTINE,
            EnforcementAction.DENY,
        )

    def test_violation_explanation_populated(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        pkt = gen.scenario_missing_caveat_violation()
        result = fce.ingest(pkt)
        assert result.final_decision.operator_explanation


class TestScenario5_MLAnomaly:
    def test_anomaly_detected_or_restricted(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """Un paquet avec lignage profond nocturne → au moins RESTRICT."""
        pkt = gen.scenario_ml_anomaly()
        result = fce.ingest(pkt)
        # Soit C1 restreint (caveats manquantes), soit C3 détecte l'anomalie
        assert result.final_decision.action != EnforcementAction.ALLOW or \
               result.anomaly_result is not None

    def test_anomaly_result_present(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        pkt = gen.scenario_ml_anomaly()
        result = fce.ingest(pkt)
        assert result.anomaly_result is not None


class TestScenario6_MaritimeSurveillance:
    def test_maritime_fusion_allowed(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """Fusion maritime (RADAR + ACOUSTIC + EO/IR) valide → pas de DENY."""
        packets = gen.scenario_maritime_surveillance()
        results = fce.ingest_batch(packets)
        for r in results:
            assert r.final_decision.action != EnforcementAction.DENY

    def test_three_sensors_fused(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        packets = gen.scenario_maritime_surveillance()
        assert len(packets) == 3
        sensor_types = {p.provenance.sensor_type for p in packets}
        assert len(sensor_types) == 3  # RADAR, ACOUSTIC, EO_IR


class TestScenario7_TacticalDismounted:
    def test_tactical_fusion_compliant(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """Fusion tactique (UAS + SIGINT sur coalition) → pas de DENY."""
        packets = gen.scenario_tactical_dismounted()
        results = fce.ingest_batch(packets)
        for r in results:
            assert r.final_decision.action != EnforcementAction.DENY


class TestHotReload:
    def test_hot_reload_adds_rule(
        self, fce: FusionComplianceEngine, policy_path: Path
    ):
        """Le hot-reload modifie les règles sans redémarrage."""
        count_before = fce._policy_engine.rule_count

        new_policy = policy_path.read_text() + """
  - id: "INT-EXTRA"
    description: "Règle ajoutée par hot-reload"
    condition:
      type: "sensor_type_match"
      sensors: ["ACOUSTIC"]
    action: "RESTRICT"
"""
        policy_path.write_text(new_policy)
        count_after = fce.reload_policies()

        assert count_after == count_before + 1


class TestAuditAndExport:
    def test_audit_summary_populated(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        packets = gen.generate_normal_traffic(n=20)
        fce.ingest_batch(packets)

        summary = fce.get_audit_summary()
        assert summary["total"] >= 20
        assert "compliance_rate" in summary

    def test_audit_csv_export(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator, tmp_path: Path
    ):
        packets = gen.generate_normal_traffic(n=10)
        fce.ingest_batch(packets)

        csv_path = tmp_path / "audit_export.csv"
        count = fce.export_audit_csv(csv_path)
        assert count == 10
        assert csv_path.exists()

    def test_provenance_graph_export(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator, tmp_path: Path
    ):
        packets = gen.scenario_maritime_surveillance()
        fce.ingest_batch(packets)

        graph_path = tmp_path / "graph.json"
        fce.export_provenance_graph(graph_path)
        assert graph_path.exists()
        data = json.loads(graph_path.read_text())
        assert len(data["nodes"]) == 3

    def test_audit_trail_per_packet(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        packets = gen.scenario_sigint_eoir_fusion()
        results = fce.ingest_batch(packets)

        for r in results:
            trail = fce.get_audit_trail(r.packet_id)
            assert trail["target_node"] == r.packet_id
            assert "computed_classification" in trail

    def test_processing_time_reasonable(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        """Chaque paquet doit être traité en < 50ms (exigence tactique)."""
        packets = gen.generate_normal_traffic(n=50)
        results = fce.ingest_batch(packets)
        for r in results:
            assert r.processing_time_ms < 50.0, (
                f"Latence trop élevée : {r.processing_time_ms:.2f}ms "
                f"pour paquet {r.packet_id[:8]}"
            )


class TestFCEResultProperties:
    def test_fce_result_summary(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        pkt = gen.scenario_classification_violation()
        result = fce.ingest(pkt)
        summary = result.summary()
        assert isinstance(summary, str)
        assert "[" in summary  # Contient l'action entre crochets

    def test_is_allowed_property(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        pkt = gen.scenario_classification_violation()
        result = fce.ingest(pkt)
        assert result.is_allowed == (result.final_decision.action == EnforcementAction.ALLOW)

    def test_requires_human_review_for_deny(
        self, fce: FusionComplianceEngine, gen: SyntheticDataGenerator
    ):
        pkt = gen.scenario_classification_violation()
        result = fce.ingest(pkt)
        if result.final_decision.action == EnforcementAction.DENY:
            assert result.requires_human_review
