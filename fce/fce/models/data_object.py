"""
FCE — Modèles de données fondamentaux.

Chaque donnée ingérée est immédiatement encapsulée dans un SensorDataPacket
portant sa ProvenanceRecord. Ces objets sont immuables après création pour
garantir l'intégrité de la piste d'audit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any
import uuid


class ClassificationLevel(IntEnum):
    """
    Niveaux de classification ordonnés.
    Le principe de dominance s'applique : la sortie d'une fusion
    hérite toujours du niveau le plus élevé parmi ses sources.
    """
    UNCLASSIFIED = 0
    PROTECTED_A = 1
    PROTECTED_B = 2
    PROTECTED_B_ENHANCED = 3
    SECRET = 4
    TOP_SECRET = 5

    def label(self) -> str:
        labels = {
            0: "Non classifié",
            1: "Protégé A",
            2: "Protégé B",
            3: "Protégé B Amélioré",
            4: "Secret",
            5: "Très Secret",
        }
        return labels[self.value]


class SensorType:
    """Constantes pour les types de capteurs supportés."""
    UAS = "UAS"
    SIGINT = "SIGINT"
    EO_IR = "EO_IR"
    RADAR = "RADAR"
    ACOUSTIC = "ACOUSTIC"

    ALL = [UAS, SIGINT, EO_IR, RADAR, ACOUSTIC]


class NetworkDomain:
    """Domaines réseau reconnus par le FCE."""
    UNCLASSIFIED_NET = "UNCLASSIFIED_NET"
    PROTECTED_NET = "PROTECTED_NET"
    SECRET_NET = "SECRET_NET"
    COALITION_NET = "COALITION_NET"

    ALL = [UNCLASSIFIED_NET, PROTECTED_NET, SECRET_NET, COALITION_NET]


@dataclass
class ProvenanceRecord:
    """
    Enregistrement de provenance immuable.
    Attaché à chaque donnée dès l'ingestion, jamais modifié ensuite.

    Attributes:
        record_id: Identifiant unique UUID4.
        sensor_id: Identifiant physique du capteur source.
        sensor_type: Type de capteur (UAS, SIGINT, EO_IR, RADAR, ACOUSTIC).
        classification: Niveau de classification au moment de l'ingestion.
        origin_domain: Domaine réseau d'origine.
        ingestion_timestamp: Horodatage UTC d'ingestion.
        dissemination_controls: Contrôles de diffusion (ex: REL TO CAN, NOFORN).
        handling_caveats: Mentions de manipulation spéciales.
        lineage: IDs des paquets parents (pour la traçabilité de fusion).
    """
    sensor_id: str
    sensor_type: str
    classification: ClassificationLevel
    origin_domain: str
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ingestion_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    dissemination_controls: list[str] = field(default_factory=list)
    handling_caveats: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.sensor_type not in SensorType.ALL:
            raise ValueError(
                f"Type de capteur invalide : '{self.sensor_type}'. "
                f"Valeurs acceptées : {SensorType.ALL}"
            )
        if not self.sensor_id.strip():
            raise ValueError("sensor_id ne peut pas être vide.")
        if self.origin_domain not in NetworkDomain.ALL:
            raise ValueError(
                f"Domaine réseau invalide : '{self.origin_domain}'. "
                f"Valeurs acceptées : {NetworkDomain.ALL}"
            )


@dataclass
class SensorDataPacket:
    """
    Unité atomique du pipeline FCE.

    Encapsule une donnée brute de capteur avec sa provenance complète.
    Tout paquet traversant le FCE doit avoir été créé via ce dataclass.

    Attributes:
        provenance: Métadonnées de provenance immuables.
        payload: Données brutes du capteur (opaque pour le FCE).
        fused_from: IDs des paquets sources si ce paquet est le résultat
                    d'une opération de fusion.
    """
    provenance: ProvenanceRecord
    payload: Any
    fused_from: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        sensor_id: str,
        sensor_type: str,
        classification: ClassificationLevel,
        origin_domain: str,
        payload: Any,
        dissemination_controls: list[str] | None = None,
        handling_caveats: list[str] | None = None,
        lineage: list[str] | None = None,
    ) -> "SensorDataPacket":
        """Constructeur de convenance avec valeurs par défaut."""
        prov = ProvenanceRecord(
            sensor_id=sensor_id,
            sensor_type=sensor_type,
            classification=classification,
            origin_domain=origin_domain,
            dissemination_controls=dissemination_controls or [],
            handling_caveats=handling_caveats or [],
            lineage=lineage or [],
        )
        return cls(provenance=prov, payload=payload)
