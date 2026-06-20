"""
FCE — Générateur de données synthétiques.

Génère des flux de données capteurs réalistes pour :
- Entraîner le détecteur d'anomalies ML (Couche 3)
- Tester le pipeline complet
- Démontrer les scénarios opérationnels FCE

Scénarios inclus :
  NORMAL    : flux conformes (entraînement ML)
  SIGINT_B  : données SIGINT Protégé B depuis réseau protégé (valide)
  FUSION    : fusion multi-capteurs UAS + EO/IR (valide)
  VIOLATION : tentative de fusion SIGINT SECRET sur réseau non classifié (bloquée)
  ANOMALY   : pattern de comportement inhabituels (détection ML)
  MARITIME  : maîtrise du domaine maritime
  TACTICAL  : milieu tactique démonté (edge computing)
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from fce.models.data_object import (
    ClassificationLevel,
    NetworkDomain,
    SensorDataPacket,
    SensorType,
)


class SyntheticPayload(NamedTuple):
    """Payload synthétique représentant une observation capteur."""
    scenario: str
    latitude: float
    longitude: float
    value: float
    unit: str
    confidence: float


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de génération
# ─────────────────────────────────────────────────────────────────────────────

def _random_coords(arctic: bool = False) -> tuple[float, float]:
    """Génère des coordonnées réalistes (Arctique canadien ou zones opérationnelles)."""
    if arctic:
        return (
            round(random.uniform(65.0, 83.0), 4),
            round(random.uniform(-140.0, -60.0), 4),
        )
    return (
        round(random.uniform(45.0, 70.0), 4),
        round(random.uniform(-130.0, -55.0), 4),
    )


def _timestamp_now(offset_hours: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=offset_hours)


# ─────────────────────────────────────────────────────────────────────────────
# Générateur principal
# ─────────────────────────────────────────────────────────────────────────────

class SyntheticDataGenerator:
    """
    Générateur de paquets synthétiques pour tous les scénarios FCE.

    Usage :
        gen = SyntheticDataGenerator(seed=42)
        normal_packets = gen.generate_normal_traffic(n=500)
        scenario = gen.scenario_sigint_protected_b()
    """

    def __init__(self, seed: int = 42) -> None:
        random.seed(seed)

    # ── Flux normaux (entraînement ML) ───────────────────────────────────────

    def generate_normal_traffic(
        self, n: int = 500
    ) -> list[SensorDataPacket]:
        """
        Génère n paquets représentant un flux opérationnel normal.
        Utilisé pour entraîner le détecteur d'anomalies ML (Couche 3).
        """
        packets = []
        normal_configs = [
            # (sensor_type, classification, domain, caveats)
            (SensorType.UAS,      ClassificationLevel.UNCLASSIFIED,  NetworkDomain.UNCLASSIFIED_NET, []),
            (SensorType.RADAR,    ClassificationLevel.PROTECTED_A,   NetworkDomain.PROTECTED_NET,    ["REL TO CAN"]),
            (SensorType.EO_IR,    ClassificationLevel.PROTECTED_B,   NetworkDomain.PROTECTED_NET,    ["REL TO CAN", "EYES ONLY"]),
            (SensorType.SIGINT,   ClassificationLevel.PROTECTED_B,   NetworkDomain.SECRET_NET,       ["REL TO CAN", "NOFORN"]),
            (SensorType.ACOUSTIC, ClassificationLevel.PROTECTED_A,   NetworkDomain.PROTECTED_NET,    ["REL TO CAN"]),
        ]

        for i in range(n):
            cfg = random.choice(normal_configs)
            sensor_type, classification, domain, caveats = cfg
            lat, lon = _random_coords()

            packets.append(SensorDataPacket.create(
                sensor_id=f"{sensor_type}-{random.randint(1000, 9999)}",
                sensor_type=sensor_type,
                classification=classification,
                origin_domain=domain,
                payload=SyntheticPayload(
                    scenario="NORMAL",
                    latitude=lat,
                    longitude=lon,
                    value=round(random.uniform(0.1, 100.0), 2),
                    unit=random.choice(["dB", "m/s", "°C", "W/m²"]),
                    confidence=round(random.uniform(0.7, 0.99), 3),
                ),
                dissemination_controls=caveats,
            ))
        return packets

    # ── Scénario 1 : Fusion SIGINT + EO/IR (valide) ──────────────────────────

    def scenario_sigint_eoir_fusion(self) -> list[SensorDataPacket]:
        """
        Fusion valide : SIGINT Protégé B + EO/IR Protégé B sur réseau sécurisé.
        Attendu : ALLOW avec classification de sortie = PROTECTED_B.
        """
        lat, lon = _random_coords(arctic=True)

        sigint_pkt = SensorDataPacket.create(
            sensor_id="SIGINT-7741",
            sensor_type=SensorType.SIGINT,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.SECRET_NET,
            payload=SyntheticPayload(
                scenario="SIGINT_FUSION",
                latitude=lat, longitude=lon,
                value=2.4e9,  # Fréquence GHz
                unit="Hz", confidence=0.95,
            ),
            dissemination_controls=["REL TO CAN", "NOFORN"],
            handling_caveats=["SIGINT"],
        )

        eoir_pkt = SensorDataPacket.create(
            sensor_id="EOIR-3312",
            sensor_type=SensorType.EO_IR,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.SECRET_NET,
            payload=SyntheticPayload(
                scenario="EOIR_FUSION",
                latitude=lat + 0.001, longitude=lon + 0.001,
                value=310.5,  # Température IR en Kelvin
                unit="K", confidence=0.88,
            ),
            dissemination_controls=["REL TO CAN", "EYES ONLY"],
            lineage=[sigint_pkt.provenance.record_id],
        )

        return [sigint_pkt, eoir_pkt]

    # ── Scénario 2 : Fusion UAS + RADAR (valide) ─────────────────────────────

    def scenario_uas_radar_fusion(self) -> list[SensorDataPacket]:
        """
        Fusion valide : UAS non classifié + Radar Protégé A.
        Attendu : ALLOW, classification de sortie = PROTECTED_A (dominance C2).
        """
        lat, lon = _random_coords()

        uas_pkt = SensorDataPacket.create(
            sensor_id="UAS-ALPHA-01",
            sensor_type=SensorType.UAS,
            classification=ClassificationLevel.UNCLASSIFIED,
            origin_domain=NetworkDomain.UNCLASSIFIED_NET,
            payload=SyntheticPayload(
                scenario="UAS_TRACK",
                latitude=lat, longitude=lon,
                value=120.0,  # Altitude mètres
                unit="m", confidence=0.92,
            ),
        )

        radar_pkt = SensorDataPacket.create(
            sensor_id="RADAR-NORTH-07",
            sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.PROTECTED_A,
            origin_domain=NetworkDomain.PROTECTED_NET,
            payload=SyntheticPayload(
                scenario="RADAR_CORR",
                latitude=lat + 0.002, longitude=lon + 0.002,
                value=850.0,  # Vitesse km/h
                unit="km/h", confidence=0.97,
            ),
            dissemination_controls=["REL TO CAN"],
            lineage=[uas_pkt.provenance.record_id],
        )

        return [uas_pkt, radar_pkt]

    # ── Scénario 3 : VIOLATION — SIGINT SECRET sur réseau non classifié ───────

    def scenario_classification_violation(self) -> SensorDataPacket:
        """
        Violation : données SIGINT Protégé B sur réseau non classifié (UNCLASSIFIED_NET).
        Attendu : DENY (règle RULE-003).
        """
        lat, lon = _random_coords(arctic=True)
        return SensorDataPacket.create(
            sensor_id="SIGINT-ROGUE-99",
            sensor_type=SensorType.SIGINT,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.UNCLASSIFIED_NET,  # ← VIOLATION
            payload=SyntheticPayload(
                scenario="VIOLATION_SIGINT_UNCLASS",
                latitude=lat, longitude=lon,
                value=1.2e9,
                unit="Hz", confidence=0.99,
            ),
            dissemination_controls=[],  # Absence de contrôle de diffusion
        )

    # ── Scénario 4 : VIOLATION — UAS sans contrôle de diffusion ──────────────

    def scenario_missing_caveat_violation(self) -> SensorDataPacket:
        """
        Violation : UAS Protégé B sans mention REL TO CAN requise.
        Attendu : RESTRICT (règle RULE-002).
        """
        lat, lon = _random_coords()
        return SensorDataPacket.create(
            sensor_id="UAS-BETA-12",
            sensor_type=SensorType.UAS,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.PROTECTED_NET,
            payload=SyntheticPayload(
                scenario="VIOLATION_MISSING_CAVEAT",
                latitude=lat, longitude=lon,
                value=250.0,
                unit="m", confidence=0.85,
            ),
            dissemination_controls=[],  # ← MANQUE "REL TO CAN"
        )

    # ── Scénario 5 : ANOMALIE ML — Pattern comportemental inhabituel ──────────

    def scenario_ml_anomaly(self) -> SensorDataPacket:
        """
        Anomalie comportementale : EO/IR avec lignage très profond et
        ingestion à 03h00 (heure nocturne inhabituelle).
        Attendu : RESTRICT (C3 détecte l'anomalie).
        """
        fake_lineage = [f"fake-parent-{i:04d}" for i in range(15)]  # Lignage suspect
        lat, lon = _random_coords(arctic=True)

        pkt = SensorDataPacket.create(
            sensor_id="EOIR-SUSPECT-77",
            sensor_type=SensorType.EO_IR,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.PROTECTED_NET,
            payload=SyntheticPayload(
                scenario="ML_ANOMALY",
                latitude=lat, longitude=lon,
                value=315.0,
                unit="K", confidence=0.61,
            ),
            dissemination_controls=[],  # Absence suspecte pour PROTECTED_B
            lineage=fake_lineage,       # Lignage anormalement profond
        )
        # Simuler une ingestion nocturne
        pkt.provenance.__dict__["ingestion_timestamp"] = _timestamp_now(
            offset_hours=-random.uniform(20.0, 22.0)  # ~02h-04h UTC
        )
        return pkt

    # ── Scénario 6 : Maritime — Multi-capteurs ────────────────────────────────

    def scenario_maritime_surveillance(self) -> list[SensorDataPacket]:
        """
        Maîtrise du domaine maritime : fusion RADAR + ACOUSTIC + EO/IR.
        Simule la détection d'une anomalie maritime (sous-marin suspect).
        Attendu : ALLOW avec classification dominante = PROTECTED_B.
        """
        lat, lon = 70.1234, -83.4567  # Arctique canadien

        radar_pkt = SensorDataPacket.create(
            sensor_id="RADAR-MARITIME-01",
            sensor_type=SensorType.RADAR,
            classification=ClassificationLevel.PROTECTED_A,
            origin_domain=NetworkDomain.PROTECTED_NET,
            payload=SyntheticPayload(
                scenario="MARITIME_RADAR",
                latitude=lat, longitude=lon,
                value=12.5,  # Vitesse nœuds
                unit="kts", confidence=0.91,
            ),
            dissemination_controls=["REL TO CAN"],
        )

        acoustic_pkt = SensorDataPacket.create(
            sensor_id="ACOUSTIC-SONAR-03",
            sensor_type=SensorType.ACOUSTIC,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.SECRET_NET,
            payload=SyntheticPayload(
                scenario="MARITIME_ACOUSTIC",
                latitude=lat + 0.01, longitude=lon + 0.01,
                value=127.0,  # dB SPL
                unit="dB", confidence=0.78,
            ),
            dissemination_controls=["REL TO CAN", "EYES ONLY"],
            lineage=[radar_pkt.provenance.record_id],
        )

        eoir_pkt = SensorDataPacket.create(
            sensor_id="EOIR-SAT-09",
            sensor_type=SensorType.EO_IR,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.SECRET_NET,
            payload=SyntheticPayload(
                scenario="MARITIME_EOIR",
                latitude=lat - 0.005, longitude=lon + 0.005,
                value=271.0,  # Température de surface eau
                unit="K", confidence=0.94,
            ),
            dissemination_controls=["REL TO CAN", "NOFORN"],
            lineage=[
                radar_pkt.provenance.record_id,
                acoustic_pkt.provenance.record_id,
            ],
        )

        return [radar_pkt, acoustic_pkt, eoir_pkt]

    # ── Scénario 7 : Tactique — Laptop renforcé (SWaP minimal) ───────────────

    def scenario_tactical_dismounted(self) -> list[SensorDataPacket]:
        """
        Milieu tactique démonté : capteurs portables sur réseau de coalition.
        Fusion UAS + SIGINT en environnement hostile.
        Attendu : ALLOW (données conformes en contexte de coalition).
        """
        lat, lon = _random_coords(arctic=True)

        uas_pkt = SensorDataPacket.create(
            sensor_id="UAS-TACTICAL-T01",
            sensor_type=SensorType.UAS,
            classification=ClassificationLevel.PROTECTED_A,
            origin_domain=NetworkDomain.COALITION_NET,
            payload=SyntheticPayload(
                scenario="TACTICAL_UAS",
                latitude=lat, longitude=lon,
                value=300.0,  # Altitude mètres
                unit="m", confidence=0.89,
            ),
            dissemination_controls=["REL TO CAN", "REL TO FVY"],
        )

        sigint_pkt = SensorDataPacket.create(
            sensor_id="SIGINT-MANPACK-02",
            sensor_type=SensorType.SIGINT,
            classification=ClassificationLevel.PROTECTED_B,
            origin_domain=NetworkDomain.SECRET_NET,
            payload=SyntheticPayload(
                scenario="TACTICAL_SIGINT",
                latitude=lat + 0.003, longitude=lon - 0.002,
                value=450.0e6,  # Fréquence MHz
                unit="Hz", confidence=0.96,
            ),
            dissemination_controls=["REL TO CAN", "NOFORN"],
            handling_caveats=["SIGINT", "COMINT"],
            lineage=[uas_pkt.provenance.record_id],
        )

        return [uas_pkt, sigint_pkt]

    def get_all_test_scenarios(self) -> dict[str, list[SensorDataPacket]]:
        """Retourne tous les scénarios de test organisés par nom."""
        return {
            "sigint_eoir_fusion": self.scenario_sigint_eoir_fusion(),
            "uas_radar_fusion": self.scenario_uas_radar_fusion(),
            "classification_violation": [self.scenario_classification_violation()],
            "missing_caveat_violation": [self.scenario_missing_caveat_violation()],
            "ml_anomaly": [self.scenario_ml_anomaly()],
            "maritime_surveillance": self.scenario_maritime_surveillance(),
            "tactical_dismounted": self.scenario_tactical_dismounted(),
        }
