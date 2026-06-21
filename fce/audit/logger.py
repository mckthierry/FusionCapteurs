"""
FCE — Journal d'audit structuré.

Enregistre chaque décision de conformité en format JSONL append-only.
Exportable en CSV pour accréditation, analyse forensique ou contrôle
de conformité externe.

Format JSONL : une entrée JSON par ligne, jamais modifiée après écriture
(garantie d'intégrité de la piste d'audit).
"""
from __future__ import annotations

import csv
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from fce.models.data_object import SensorDataPacket


class _FCEJSONEncoder(json.JSONEncoder):
    """Encodeur JSON tolérant aux types numpy (bool_, integer, floating)."""
    def default(self, obj):
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)
from fce.policy.engine import PolicyDecision, EnforcementAction
from fce.ml.anomaly_detector import AnomalyResult

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Journal d'audit thread-safe en format JSONL append-only.

    Chaque entrée contient :
    - Identifiants du paquet et du capteur source
    - Classification d'entrée et de sortie
    - Action d'enforcement et règles déclenchées
    - Résultat de l'analyse ML (si disponible)
    - Explication lisible par un opérateur
    - Horodatage UTC

    Thread-safety : verrou fichier pour les écritures concurrentes.
    """

    FIELDNAMES = [
        "timestamp",
        "packet_id",
        "sensor_id",
        "sensor_type",
        "origin_domain",
        "classification_in",
        "classification_out",
        "action",
        "is_compliant",
        "rules_applied",
        "ml_anomaly",
        "ml_score",
        "ml_severity",
        "operator_explanation",
        "lineage_depth",
        "dissemination_controls",
    ]

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self._lock = threading.Lock()
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._entry_count = 0

        # Initialise le fichier si inexistant
        if not self._log_path.exists():
            self._log_path.touch()
            logger.info("Journal d'audit initialisé : %s", self._log_path)

    def record(
        self,
        packet: SensorDataPacket,
        decision: PolicyDecision,
        anomaly_result: AnomalyResult | None = None,
    ) -> None:
        """
        Enregistre une décision de conformité dans le journal.

        Cette opération est atomique : soit l'entrée est entièrement écrite,
        soit elle n'est pas écrite (garantie par le verrou + flush).
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "packet_id": packet.provenance.record_id,
            "sensor_id": packet.provenance.sensor_id,
            "sensor_type": packet.provenance.sensor_type,
            "origin_domain": packet.provenance.origin_domain,
            "classification_in": packet.provenance.classification.name,
            "classification_out": decision.resulting_classification.name,
            "action": decision.action.name,
            "is_compliant": decision.is_compliant,
            "rules_applied": decision.applied_rules,
            "ml_anomaly": anomaly_result.is_anomaly if anomaly_result else None,
            "ml_score": round(anomaly_result.anomaly_score, 6) if anomaly_result else None,
            "ml_severity": anomaly_result.severity if anomaly_result else None,
            "operator_explanation": (
                anomaly_result.explanation
                if anomaly_result and anomaly_result.is_anomaly
                else decision.operator_explanation
            ),
            "lineage_depth": len(packet.provenance.lineage),
            "dissemination_controls": packet.provenance.dissemination_controls,
        }

        with self._lock:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, cls=_FCEJSONEncoder) + "\n")
                f.flush()
            self._entry_count += 1

    def export_csv(self, output_path: Path) -> int:
        """
        Exporte le journal JSONL en CSV pour audit externe.

        Returns:
            Nombre d'entrées exportées.
        """
        with self._lock:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()

        entries = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    # Sérialise les listes en chaînes pour CSV
                    entry["rules_applied"] = "|".join(entry.get("rules_applied", []))
                    entry["dissemination_controls"] = "|".join(
                        entry.get("dissemination_controls", [])
                    )
                    entries.append(entry)
                except json.JSONDecodeError as exc:
                    logger.warning("Entrée de journal corrompue ignorée : %s", exc)

        if not entries:
            logger.warning("Journal vide — rien à exporter.")
            return 0

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=self.FIELDNAMES,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(entries)

        logger.info("Journal exporté : %d entrées → %s", len(entries), output_path)
        return len(entries)

    def get_summary(self) -> dict:
        """Retourne un résumé statistique du journal pour supervision."""
        with self._lock:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()

        entries = [json.loads(l) for l in lines if l.strip()]
        if not entries:
            return {"total": 0}

        action_counts: dict[str, int] = {}
        sensor_counts: dict[str, int] = {}
        anomaly_count = 0

        for e in entries:
            action = e.get("action", "UNKNOWN")
            action_counts[action] = action_counts.get(action, 0) + 1
            sensor = e.get("sensor_type", "UNKNOWN")
            sensor_counts[sensor] = sensor_counts.get(sensor, 0) + 1
            if e.get("ml_anomaly"):
                anomaly_count += 1

        return {
            "total": len(entries),
            "compliant": action_counts.get("ALLOW", 0),
            "violations": len(entries) - action_counts.get("ALLOW", 0),
            "ml_anomalies": anomaly_count,
            "by_action": action_counts,
            "by_sensor": sensor_counts,
            "compliance_rate": round(
                action_counts.get("ALLOW", 0) / len(entries) * 100, 2
            ),
        }

    @property
    def entry_count(self) -> int:
        return self._entry_count
