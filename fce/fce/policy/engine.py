"""
FCE — Couche 1 : Moteur de politiques (Policy Engine).

Charge des règles de conformité depuis YAML lisibles par machine.
Supporte le hot-reload sans redémarrage du pipeline.
Applique le principe fail-secure : en cas de conflit, la décision
la plus restrictive l'emporte toujours.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable

import yaml

from fce.models.data_object import ClassificationLevel, ProvenanceRecord, SensorDataPacket

logger = logging.getLogger(__name__)


class EnforcementAction(Enum):
    """
    Actions d'enforcement ordonnées par restrictivité croissante.
    Le pipeline applique toujours l'action la plus restrictive déclenchée.
    """
    ALLOW = auto()       # Données conformes, passage autorisé
    DOWNGRADE = auto()   # Déclassement automatique avant fusion
    RESTRICT = auto()    # Acheminement restreint, flags d'avertissement
    QUARANTINE = auto()  # Isolation, validation humaine requise
    DENY = auto()        # Rejet total, aucune fusion autorisée

    @property
    def priority(self) -> int:
        """Plus le score est bas, plus l'action est restrictive."""
        order = {
            EnforcementAction.DENY: 0,
            EnforcementAction.QUARANTINE: 1,
            EnforcementAction.RESTRICT: 2,
            EnforcementAction.DOWNGRADE: 3,
            EnforcementAction.ALLOW: 4,
        }
        return order[self]


@dataclass
class PolicyDecision:
    """Résultat de l'évaluation du moteur de politiques pour un paquet."""
    action: EnforcementAction
    reason: str
    applied_rules: list[str] = field(default_factory=list)
    resulting_classification: ClassificationLevel = ClassificationLevel.UNCLASSIFIED
    operator_explanation: str = ""  # Texte lisible par un humain

    @property
    def is_compliant(self) -> bool:
        return self.action == EnforcementAction.ALLOW

    @property
    def requires_human_review(self) -> bool:
        return self.action in (EnforcementAction.QUARANTINE, EnforcementAction.DENY)


class ConditionEvaluator:
    """
    Compile les conditions déclaratives YAML en prédicats Python.
    Chaque type de condition retourne True si la règle doit s'appliquer.
    """

    @staticmethod
    def compile(condition: dict) -> Callable[[ProvenanceRecord], bool]:
        cond_type = condition["type"]

        if cond_type == "classification_above":
            # Se déclenche si le niveau dépasse un seuil
            threshold = ClassificationLevel[condition["threshold"]]
            def check_above(prov: ProvenanceRecord) -> bool:
                return prov.classification > threshold
            return check_above

        if cond_type == "classification_mismatch":
            # Bloque si la classification n'est pas dans la liste autorisée
            allowed = {ClassificationLevel[c] for c in condition.get("allowed", [])}
            def check_mismatch(prov: ProvenanceRecord) -> bool:
                return prov.classification not in allowed
            return check_mismatch

        if cond_type == "missing_caveat":
            # Se déclenche si des mentions obligatoires sont absentes
            required = set(condition.get("required_caveats", []))
            def check_caveat(prov: ProvenanceRecord) -> bool:
                return not required.issubset(set(prov.dissemination_controls))
            return check_caveat

        if cond_type == "sensor_domain_restriction":
            # Bloque une combinaison capteur + domaine réseau
            restricted_sensors = set(condition.get("sensors", []))
            restricted_domains = set(condition.get("domains", []))
            def check_sensor_domain(prov: ProvenanceRecord) -> bool:
                return (
                    prov.sensor_type in restricted_sensors
                    and prov.origin_domain in restricted_domains
                )
            return check_sensor_domain

        if cond_type == "sensor_type_match":
            # Se déclenche pour un type de capteur spécifique
            target_sensors = set(condition.get("sensors", []))
            def check_sensor(prov: ProvenanceRecord) -> bool:
                return prov.sensor_type in target_sensors
            return check_sensor

        if cond_type == "domain_match":
            # Se déclenche pour un domaine réseau spécifique
            target_domains = set(condition.get("domains", []))
            def check_domain(prov: ProvenanceRecord) -> bool:
                return prov.origin_domain in target_domains
            return check_domain

        raise ValueError(
            f"Type de condition inconnu : '{cond_type}'. "
            f"Types supportés : classification_above, classification_mismatch, "
            f"missing_caveat, sensor_domain_restriction, sensor_type_match, domain_match"
        )


class PolicyRule:
    """
    Règle de conformité compilée depuis une définition YAML.

    Une règle = une condition + une action + une explication opérateur.
    """

    def __init__(self, rule_def: dict) -> None:
        self.rule_id: str = rule_def["id"]
        self.description: str = rule_def.get("description", "")
        self.operator_explanation: str = rule_def.get(
            "operator_explanation", self.description
        )
        self._condition = ConditionEvaluator.compile(rule_def["condition"])
        self._action = EnforcementAction[rule_def["action"].upper()]
        self._target_classification: ClassificationLevel | None = (
            ClassificationLevel[rule_def["target_classification"]]
            if "target_classification" in rule_def
            else None
        )

    def evaluate(self, provenance: ProvenanceRecord) -> PolicyDecision | None:
        """
        Évalue la règle sur une provenance.
        Retourne une PolicyDecision si la règle se déclenche, None sinon.
        """
        if not self._condition(provenance):
            return None

        resulting_class = (
            self._target_classification
            if self._target_classification is not None
            else provenance.classification
        )
        return PolicyDecision(
            action=self._action,
            reason=self.description,
            applied_rules=[self.rule_id],
            resulting_classification=resulting_class,
            operator_explanation=self.operator_explanation,
        )


class PolicyEngine:
    """
    Couche 1 du FCE : moteur de politiques thread-safe avec hot-reload.

    Évalue toutes les règles actives sur chaque paquet entrant.
    En cas de règles multiples déclenchées, retourne la décision
    la plus restrictive (fail-secure).

    Thread-safety : le verrou RLock protège le remplacement atomique
    de la liste de règles pendant le hot-reload.
    """

    def __init__(self, policy_path: Path) -> None:
        self._policy_path = policy_path
        self._rules: list[PolicyRule] = []
        self._lock = threading.RLock()
        self._policy_version: str = "unknown"
        self.load_policies()

    def load_policies(self) -> int:
        """
        Charge ou recharge les règles depuis le fichier YAML.
        Opération atomique : les nouvelles règles remplacent les anciennes
        en un seul swap, sans fenêtre d'inconsistance.

        Returns:
            Nombre de règles chargées.
        """
        with self._policy_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        new_rules = []
        errors = []
        for rule_def in raw.get("rules", []):
            try:
                new_rules.append(PolicyRule(rule_def))
            except (KeyError, ValueError) as exc:
                errors.append(f"Règle '{rule_def.get('id', '?')}' : {exc}")

        if errors:
            logger.warning(
                "Erreurs lors du chargement des politiques :\n%s",
                "\n".join(errors),
            )

        with self._lock:
            self._rules = new_rules
            self._policy_version = raw.get("version", "unknown")

        logger.info(
            "Politiques v%s rechargées : %d règles actives",
            self._policy_version,
            len(new_rules),
        )
        return len(new_rules)

    @property
    def rule_count(self) -> int:
        with self._lock:
            return len(self._rules)

    @property
    def policy_version(self) -> str:
        return self._policy_version

    def evaluate(self, packet: SensorDataPacket) -> PolicyDecision:
        """
        Évalue toutes les règles actives sur un paquet.

        Algorithme fail-secure :
        1. Évalue chaque règle indépendamment.
        2. Collecte toutes les décisions déclenchées.
        3. Retourne la décision la plus restrictive (priorité la plus basse).
        4. Agrège les IDs de toutes les règles déclenchées.
        5. Si aucune règle ne se déclenche → ALLOW.

        Returns:
            PolicyDecision avec l'action la plus restrictive applicable.
        """
        with self._lock:
            active_rules = list(self._rules)

        triggered: list[PolicyDecision] = []
        for rule in active_rules:
            decision = rule.evaluate(packet.provenance)
            if decision is not None:
                triggered.append(decision)

        if not triggered:
            return PolicyDecision(
                action=EnforcementAction.ALLOW,
                reason="Aucune règle de restriction applicable",
                applied_rules=[],
                resulting_classification=packet.provenance.classification,
                operator_explanation=(
                    f"Données de {packet.provenance.sensor_type} "
                    f"({packet.provenance.classification.label()}) conformes à toutes "
                    f"les politiques actives."
                ),
            )

        # Tri par priorité (fail-secure : plus restrictif d'abord)
        triggered.sort(key=lambda d: d.action.priority)
        final = triggered[0]

        # Agrège tous les IDs de règles déclenchées pour l'audit
        all_rule_ids = [rid for d in triggered for rid in d.applied_rules]
        final.applied_rules = all_rule_ids

        return final
