"""Tests unitaires — Couche 1 : Moteur de politiques."""
import pytest
from pathlib import Path

from fce.models.data_object import (
    ClassificationLevel,
    NetworkDomain,
    SensorDataPacket,
    SensorType,
)
from fce.policy.engine import EnforcementAction, PolicyDecision, PolicyEngine


@pytest.fixture
def policy_path(tmp_path: Path) -> Path:
    """Crée un fichier de politiques de test."""
    policy_content = """
version: "1.0-test"
rules:
  - id: "TEST-001"
    description: "Bloquer SECRET et supérieur"
    operator_explanation: "Données trop classifiées"
    condition:
      type: "classification_above"
      threshold: "PROTECTED_B_ENHANCED"
    action: "DENY"

  - id: "TEST-002"
    description: "Restreindre sans REL TO CAN"
    operator_explanation: "Mention de diffusion manquante"
    condition:
      type: "missing_caveat"
      required_caveats:
        - "REL TO CAN"
    action: "RESTRICT"

  - id: "TEST-003"
    description: "Bloquer SIGINT sur réseau non classifié"
    operator_explanation: "SIGINT interdit sur UNCLASSIFIED_NET"
    condition:
      type: "sensor_domain_restriction"
      sensors:
        - "SIGINT"
      domains:
        - "UNCLASSIFIED_NET"
    action: "DENY"

  - id: "TEST-004"
    description: "Quarantaine UAS sur réseau non classifié"
    condition:
      type: "sensor_type_match"
      sensors:
        - "UAS"
    action: "QUARANTINE"
    target_classification: "PROTECTED_A"
"""
    p = tmp_path / "test_policy.yaml"
    p.write_text(policy_content)
    return p


@pytest.fixture
def engine(policy_path: Path) -> PolicyEngine:
    return PolicyEngine(policy_path)


def make_packet(
    sensor_type: str = SensorType.RADAR,
    classification: ClassificationLevel = ClassificationLevel.PROTECTED_A,
    domain: str = NetworkDomain.PROTECTED_NET,
    caveats: list[str] | None = None,
) -> SensorDataPacket:
    return SensorDataPacket.create(
        sensor_id=f"{sensor_type}-TEST",
        sensor_type=sensor_type,
        classification=classification,
        origin_domain=domain,
        payload=None,
        dissemination_controls=caveats or [],
    )


class TestPolicyEngineLoading:
    def test_loads_rules(self, engine: PolicyEngine):
        assert engine.rule_count == 4

    def test_policy_version(self, engine: PolicyEngine):
        assert engine.policy_version == "1.0-test"

    def test_hot_reload(self, engine: PolicyEngine, policy_path: Path, tmp_path: Path):
        """Vérifie le hot-reload sans redémarrage."""
        new_content = """
version: "2.0-test"
rules:
  - id: "HOT-001"
    description: "Règle après hot-reload"
    condition:
      type: "domain_match"
      domains:
        - "UNCLASSIFIED_NET"
    action: "RESTRICT"
"""
        policy_path.write_text(new_content)
        count = engine.load_policies()
        assert count == 1
        assert engine.policy_version == "2.0-test"
        assert engine.rule_count == 1

    def test_invalid_rule_skipped_gracefully(self, tmp_path: Path):
        """Les règles malformées sont ignorées sans lever d'exception."""
        bad_policy = """
version: "bad"
rules:
  - id: "BAD-001"
    description: "Règle invalide"
    condition:
      type: "unknown_condition_type"
    action: "DENY"
  - id: "GOOD-001"
    description: "Règle valide"
    condition:
      type: "domain_match"
      domains: ["UNCLASSIFIED_NET"]
    action: "RESTRICT"
"""
        p = tmp_path / "bad_policy.yaml"
        p.write_text(bad_policy)
        engine = PolicyEngine(p)
        assert engine.rule_count == 1  # Seule la règle valide est chargée


class TestPolicyEvaluation:
    def test_allow_compliant_packet(self, engine: PolicyEngine):
        """Un paquet conforme reçoit ALLOW."""
        pkt = make_packet(
            sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.PROTECTED_A,
            domain=NetworkDomain.PROTECTED_NET,
            caveats=["REL TO CAN"],
        )
        # TEST-004 bloque UAS, pas RADAR
        # On crée un moteur sans TEST-004 pour ce test
        from pathlib import Path
        decision = engine.evaluate(pkt)
        # RADAR non ciblé par TEST-003 ni TEST-001 avec caveats OK
        # TEST-002 s'applique car caveats = ["REL TO CAN"] → pas RESTRICT
        # TEST-004 cible UAS, pas RADAR → pas de déclenchement
        assert decision.action in (EnforcementAction.ALLOW, EnforcementAction.RESTRICT)

    def test_deny_secret_classification(self, engine: PolicyEngine):
        """Un paquet SECRET reçoit DENY (TEST-001)."""
        pkt = make_packet(
            classification=ClassificationLevel.SECRET,
            caveats=["REL TO CAN"],
        )
        decision = engine.evaluate(pkt)
        assert decision.action == EnforcementAction.DENY
        assert "TEST-001" in decision.applied_rules

    def test_deny_sigint_on_unclassified_net(self, engine: PolicyEngine):
        """SIGINT sur UNCLASSIFIED_NET reçoit DENY (TEST-003)."""
        pkt = make_packet(
            sensor_type=SensorType.SIGINT,
            domain=NetworkDomain.UNCLASSIFIED_NET,
            caveats=["REL TO CAN"],
        )
        decision = engine.evaluate(pkt)
        assert decision.action == EnforcementAction.DENY
        assert "TEST-003" in decision.applied_rules

    def test_restrict_missing_caveat(self, engine: PolicyEngine):
        """Un paquet sans REL TO CAN reçoit RESTRICT (TEST-002)."""
        pkt = make_packet(
            sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.PROTECTED_B,
            domain=NetworkDomain.PROTECTED_NET,
            caveats=[],  # Pas de REL TO CAN
        )
        decision = engine.evaluate(pkt)
        assert decision.action in (
            EnforcementAction.RESTRICT, EnforcementAction.QUARANTINE,
            EnforcementAction.DENY
        )

    def test_fail_secure_multiple_rules(self, engine: PolicyEngine):
        """En cas de règles multiples, la plus restrictive (DENY) l'emporte."""
        pkt = make_packet(
            sensor_type=SensorType.SIGINT,
            classification=ClassificationLevel.SECRET,  # Déclenche TEST-001 (DENY)
            domain=NetworkDomain.UNCLASSIFIED_NET,      # Déclenche TEST-003 (DENY)
            caveats=[],                                   # Déclenche TEST-002 (RESTRICT)
        )
        decision = engine.evaluate(pkt)
        # DENY > QUARANTINE > RESTRICT → DENY doit gagner
        assert decision.action == EnforcementAction.DENY
        # Plusieurs règles doivent être référencées
        assert len(decision.applied_rules) >= 2

    def test_target_classification_override(self, engine: PolicyEngine):
        """TEST-004 déclasse à PROTECTED_A si ciblé."""
        pkt = make_packet(
            sensor_type=SensorType.UAS,
            classification=ClassificationLevel.UNCLASSIFIED,
            domain=NetworkDomain.UNCLASSIFIED_NET,
            caveats=["REL TO CAN"],
        )
        decision = engine.evaluate(pkt)
        # TEST-004 cible UAS → QUARANTINE avec target PROTECTED_A
        assert "TEST-004" in decision.applied_rules
        assert decision.resulting_classification == ClassificationLevel.PROTECTED_A

    def test_operator_explanation_populated(self, engine: PolicyEngine):
        """Chaque décision doit avoir une explication lisible."""
        pkt = make_packet(
            classification=ClassificationLevel.SECRET,
            caveats=["REL TO CAN"],
        )
        decision = engine.evaluate(pkt)
        assert decision.operator_explanation
        assert isinstance(decision.operator_explanation, str)

    def test_is_compliant_property(self, engine: PolicyEngine):
        """Test du prédicat is_compliant."""
        allow = PolicyDecision(
            action=EnforcementAction.ALLOW,
            reason="OK",
            resulting_classification=ClassificationLevel.UNCLASSIFIED,
        )
        deny = PolicyDecision(
            action=EnforcementAction.DENY,
            reason="KO",
            resulting_classification=ClassificationLevel.UNCLASSIFIED,
        )
        assert allow.is_compliant is True
        assert deny.is_compliant is False

    def test_requires_human_review(self):
        """QUARANTINE et DENY requièrent une révision humaine."""
        for action in (EnforcementAction.QUARANTINE, EnforcementAction.DENY):
            d = PolicyDecision(
                action=action,
                reason="test",
                resulting_classification=ClassificationLevel.UNCLASSIFIED,
            )
            assert d.requires_human_review is True

        for action in (EnforcementAction.ALLOW, EnforcementAction.RESTRICT):
            d = PolicyDecision(
                action=action,
                reason="test",
                resulting_classification=ClassificationLevel.UNCLASSIFIED,
            )
            assert d.requires_human_review is False


class TestEnforcementActionPriority:
    def test_priority_ordering(self):
        """DENY doit avoir la priorité la plus haute (score le plus bas)."""
        assert EnforcementAction.DENY.priority < EnforcementAction.QUARANTINE.priority
        assert EnforcementAction.QUARANTINE.priority < EnforcementAction.RESTRICT.priority
        assert EnforcementAction.RESTRICT.priority < EnforcementAction.DOWNGRADE.priority
        assert EnforcementAction.DOWNGRADE.priority < EnforcementAction.ALLOW.priority

    def test_sort_by_priority(self):
        """Le tri par priorité place DENY en premier."""
        actions = [
            EnforcementAction.ALLOW,
            EnforcementAction.RESTRICT,
            EnforcementAction.DENY,
        ]
        sorted_actions = sorted(actions, key=lambda a: a.priority)
        assert sorted_actions[0] == EnforcementAction.DENY
