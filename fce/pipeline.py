"""
FCE — Pipeline orchestrateur principal.

Orchestre les 3 couches complémentaires en séquence :
  Couche 1 (PolicyEngine)           → règles statiques fail-secure
  Couche 2 (ProvenanceGraph)        → propagation de classification + DAG
  Couche 3 (AnomalyDetector)        → surveillance comportementale ML

Architecture de décision :
  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
  │  Couche 1   │───►│  Couche 2   │───►│  Couche 3   │
  │  Politiques │    │  Provenance  │    │  ML Anomalie │
  │  (YAML)     │    │  (DAG)       │    │  (IForest)   │
  └──────┬──────┘    └──────┬───────┘    └──────┬───────┘
         │                  │                    │
         └──────────────────┴────────────────────┘
                            │
                     ┌──────▼──────┐
                     │   AuditLog  │
                     │   (JSONL)   │
                     └─────────────┘

Règle de fusion des décisions (fail-secure) :
  La décision finale = max(restriction) entre C1 et C3.
  C2 enrichit la décision (classification calculée) sans la remplacer.
  Si C3 détecte une anomalie et que C1 = ALLOW → décision dégradée à RESTRICT.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fce.audit.logger import AuditLogger
from fce.lineage.graph import LineageNode, ProvenanceGraph
from fce.ml.anomaly_detector import AnomalyResult, ComplianceAnomalyDetector
from fce.models.data_object import ClassificationLevel, SensorDataPacket
from fce.policy.engine import EnforcementAction, PolicyDecision, PolicyEngine

logger = logging.getLogger(__name__)


@dataclass
class FCEResult:
    """Résultat complet d'un passage dans le pipeline FCE."""
    packet_id: str
    final_decision: PolicyDecision
    layer1_decision: PolicyDecision
    anomaly_result: AnomalyResult | None
    computed_classification: ClassificationLevel
    processing_time_ms: float
    cross_domain_violations: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_allowed(self) -> bool:
        return self.final_decision.action == EnforcementAction.ALLOW

    @property
    def requires_human_review(self) -> bool:
        return self.final_decision.requires_human_review

    def summary(self) -> str:
        """Résumé compact pour logging et affichage."""
        anomaly_flag = ""
        if self.anomaly_result and self.anomaly_result.is_anomaly:
            anomaly_flag = f" [ML:{self.anomaly_result.severity}]"

        return (
            f"[{self.final_decision.action.name}]{anomaly_flag} "
            f"Paquet={self.packet_id[:8]}… "
            f"Classif.={self.computed_classification.label()} "
            f"Règles={self.final_decision.applied_rules} "
            f"({self.processing_time_ms:.2f}ms)"
        )


class FusionComplianceEngine:
    """
    Point d'entrée principal du FCE.

    Exemple d'utilisation :
        fce = FusionComplianceEngine(
            policy_path=Path("policies/base_policy.yaml"),
            audit_log_path=Path("logs/audit.jsonl"),
        )
        fce.train_anomaly_detector(training_packets)

        result = fce.ingest(packet)
        if not result.is_allowed:
            print(result.final_decision.operator_explanation)

    Hot-reload des politiques :
        fce.reload_policies()  # Sans redémarrage du pipeline

    Export d'audit :
        fce.export_audit_csv(Path("audit_export.csv"))
        fce.export_provenance_graph(Path("graph.json"))
    """

    def __init__(
        self,
        policy_path: Path,
        audit_log_path: Path,
        anomaly_model_path: Path | None = None,
        allowed_domain_pairs: set[tuple[str, str]] | None = None,
        ml_contamination: float = 0.001,
    ) -> None:
        logger.info("Initialisation du Moteur de Conformité de Fusion (FCE)...")

        # Couche 1 : Moteur de politiques
        self._policy_engine = PolicyEngine(policy_path)

        # Couche 2 : Graphe de provenance
        self._provenance_graph = ProvenanceGraph(
            allowed_domain_pairs=allowed_domain_pairs
        )

        # Couche 3 : Détecteur d'anomalies ML
        self._anomaly_detector = ComplianceAnomalyDetector(
            contamination=ml_contamination,
            model_path=anomaly_model_path,
        )

        # Journal d'audit
        self._audit_logger = AuditLogger(audit_log_path)

        # Statistiques internes
        self._total_processed: int = 0
        self._total_violations: int = 0

        logger.info(
            "FCE initialisé — Politiques: %d règles, ML: %s",
            self._policy_engine.rule_count,
            "prêt" if self._anomaly_detector.is_ready else "non entraîné",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Méthode principale
    # ──────────────────────────────────────────────────────────────────────────

    def ingest(self, packet: SensorDataPacket) -> FCEResult:
        """
        Ingère un paquet dans le pipeline FCE tri-couche.

        Séquence :
        1. Couche 1 : évaluation des politiques statiques.
        2. Couche 2 : enregistrement dans le graphe de provenance,
                      calcul de la classification de sortie dominante.
        3. Couche 3 : analyse d'anomalie ML.
        4. Fusion des décisions (fail-secure).
        5. Enregistrement dans le journal d'audit.

        Args:
            packet: SensorDataPacket à analyser.

        Returns:
            FCEResult avec toutes les décisions et métadonnées.
        """
        t_start = time.perf_counter()

        # ── Couche 1 : Politiques statiques ──────────────────────────────────
        layer1_decision = self._policy_engine.evaluate(packet)

        # ── Couche 2 : Graphe de provenance ──────────────────────────────────
        self._provenance_graph.add_packet(packet, node_type="ingestion")

        # Calcul de la classification dominante (principe de dominance)
        computed_classification = self._provenance_graph.compute_output_classification(
            packet.provenance.record_id
        )

        # Mise à jour de la classification de sortie dans la décision C1
        if computed_classification > layer1_decision.resulting_classification:
            layer1_decision.resulting_classification = computed_classification
            layer1_decision.applied_rules.append("C2-CLASSIFICATION-DOMINANCE")

        # Détection des violations inter-domaines
        violations = self._provenance_graph.detect_cross_domain_violations()
        cross_domain_count = len(violations)
        if violations and layer1_decision.action == EnforcementAction.ALLOW:
            layer1_decision.action = EnforcementAction.RESTRICT
            layer1_decision.reason += (
                f" | {cross_domain_count} violation(s) inter-domaines détectée(s) "
                f"par C2 (graphe de provenance)."
            )
            layer1_decision.applied_rules.append("C2-CROSS-DOMAIN-VIOLATION")

        # ── Couche 3 : Anomalie ML ────────────────────────────────────────────
        anomaly_result = self._anomaly_detector.predict(packet)

        # Fusion des décisions C1 + C3 (fail-secure)
        final_decision = self._merge_decisions(
            layer1_decision, anomaly_result
        )

        # ── Journal d'audit ───────────────────────────────────────────────────
        self._audit_logger.record(packet, final_decision, anomaly_result)

        # ── Statistiques ──────────────────────────────────────────────────────
        self._total_processed += 1
        if not final_decision.is_compliant:
            self._total_violations += 1

        t_end = time.perf_counter()
        processing_ms = (t_end - t_start) * 1000

        result = FCEResult(
            packet_id=packet.provenance.record_id,
            final_decision=final_decision,
            layer1_decision=layer1_decision,
            anomaly_result=anomaly_result,
            computed_classification=computed_classification,
            processing_time_ms=processing_ms,
            cross_domain_violations=cross_domain_count,
        )

        log_fn = logger.warning if not result.is_allowed else logger.debug
        log_fn("FCE: %s", result.summary())

        return result

    def ingest_batch(
        self, packets: list[SensorDataPacket]
    ) -> list[FCEResult]:
        """Ingère une liste de paquets et retourne tous les résultats."""
        return [self.ingest(p) for p in packets]

    # ──────────────────────────────────────────────────────────────────────────
    # Entraînement ML
    # ──────────────────────────────────────────────────────────────────────────

    def train_anomaly_detector(
        self,
        training_packets: list[SensorDataPacket],
        model_save_path: Path | None = None,
    ) -> None:
        """
        Entraîne le détecteur d'anomalies ML (Couche 3).

        Args:
            training_packets: Flux de paquets représentatifs d'un comportement normal.
            model_save_path:  Si fourni, sauvegarde le modèle après entraînement.
        """
        self._anomaly_detector.fit(training_packets)
        if model_save_path:
            self._anomaly_detector.save(model_save_path)
        logger.info("Détecteur ML entraîné sur %d paquets.", len(training_packets))

    # ──────────────────────────────────────────────────────────────────────────
    # Hot-reload & configuration
    # ──────────────────────────────────────────────────────────────────────────

    def reload_policies(self) -> int:
        """
        Recharge les règles de politique depuis le fichier YAML sans redémarrage.

        Returns:
            Nombre de règles chargées.
        """
        count = self._policy_engine.load_policies()
        logger.info("Hot-reload politiques : %d règles actives.", count)
        return count

    def update_allowed_domain_pairs(
        self, pairs: set[tuple[str, str]]
    ) -> None:
        """Met à jour les paires de domaines autorisées (Couche 2)."""
        self._provenance_graph.set_allowed_domain_pairs(pairs)

    # ──────────────────────────────────────────────────────────────────────────
    # Export & audit
    # ──────────────────────────────────────────────────────────────────────────

    def export_audit_csv(self, output_path: Path) -> int:
        """Exporte le journal d'audit en CSV."""
        return self._audit_logger.export_csv(output_path)

    def export_provenance_graph(self, output_path: Path) -> None:
        """Exporte le graphe de provenance complet en JSON."""
        self._provenance_graph.export_to_json(output_path)

    def get_audit_trail(self, packet_id: str) -> dict:
        """Retourne la piste d'audit complète d'un paquet (Couche 2)."""
        return self._provenance_graph.export_audit_trail(packet_id)

    def get_audit_summary(self) -> dict:
        """Retourne le résumé statistique du journal d'audit."""
        summary = self._audit_logger.get_summary()
        summary["total_processed"] = self._total_processed
        summary["total_violations"] = self._total_violations
        return summary

    # ──────────────────────────────────────────────────────────────────────────
    # Méthodes internes
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_decisions(
        layer1: PolicyDecision,
        anomaly: AnomalyResult | None,
    ) -> PolicyDecision:
        """
        Fusionne les décisions C1 et C3 selon le principe fail-secure.

        Règle :
        - Si C3 détecte une anomalie ET que C1 = ALLOW → dégrader à RESTRICT.
        - Si C3 détecte une anomalie HAUTE ET C1 = ALLOW → dégrader à QUARANTINE.
        - Sinon, C1 l'emporte (il est déjà fail-secure en lui-même).
        """
        if anomaly is None or not anomaly.is_anomaly:
            return layer1

        # Anomalie ML détectée : possible escalade
        if layer1.action == EnforcementAction.ALLOW:
            escalated_action = (
                EnforcementAction.QUARANTINE
                if anomaly.severity == "HIGH"
                else EnforcementAction.RESTRICT
            )
            layer1.action = escalated_action
            layer1.reason += f" | {anomaly.explanation}"
            layer1.applied_rules.append(
                f"C3-ML-ANOMALY-{anomaly.severity}"
            )
            layer1.operator_explanation = anomaly.explanation

        return layer1
