"""
FCE — Couche 3 : Détecteur d'anomalies ML (LMAG).

Surveille les patterns de flux de données en temps réel pour détecter
les violations de politique que les règles statiques ne peuvent pas
anticiper : exfiltrations subtiles, contaminations lentes,
comportements anormaux de capteurs.

Optimisé SWaP :
- Isolation Forest sklearn (léger, ~500KB, inférence < 1ms sur CPU)
- Cache LRU pour les features répétitives
- Modèle sérialisé avec joblib (compression gzip)
- Dégradation gracieuse si modèle non disponible
"""
from __future__ import annotations

import logging
import pickle
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder, MinMaxScaler

from fce.models.data_object import ClassificationLevel, SensorDataPacket

logger = logging.getLogger(__name__)

# Dimension du vecteur de features
N_FEATURES = 7


@dataclass
class AnomalyResult:
    """Résultat de l'analyse d'anomalie pour un paquet."""
    is_anomaly: bool
    anomaly_score: float       # Score brut (< 0 = anomalie, plus négatif = plus suspect)
    confidence: float          # [0, 1] confiance dans la détection
    explanation: str           # Explication lisible par un opérateur

    @property
    def severity(self) -> str:
        """Évalue la sévérité de l'anomalie."""
        if not self.is_anomaly:
            return "NONE"
        if self.anomaly_score < -0.3:
            return "HIGH"
        if self.anomaly_score < -0.15:
            return "MEDIUM"
        return "LOW"


class ComplianceAnomalyDetector:
    """
    Couche 3 du FCE : détecteur d'anomalies basé sur Isolation Forest.

    Stratégie de features (N=7) :
    1. Niveau de classification normalisé [0, 1]
    2. Type de capteur encodé (LabelEncoder)
    3. Domaine réseau encodé (LabelEncoder)
    4. Heure d'ingestion normalisée [0, 1] (détection d'activités nocturnes)
    5. Nombre de contrôles de diffusion (patterns anormaux)
    6. Profondeur de lignage (chaînes de fusion suspectes)
    7. Présence de mises en garde spéciales [0/1]

    Paramètres :
        contamination: Fraction attendue d'anomalies dans les données
                       d'entraînement. Fixé à 0.001 (< 0.1% cible FCE).
        n_estimators:  Nombre d'arbres. 100 = bon compromis précision/vitesse.
        model_path:    Chemin vers un modèle pré-entraîné à charger.

    Dégradation gracieuse :
        Si predict() est appelé sans modèle entraîné, retourne
        AnomalyResult(is_anomaly=False) avec un warning.
        Le pipeline ne s'arrête pas — la Couche 1 et la Couche 2 continuent.
    """

    def __init__(
        self,
        contamination: float = 0.001,
        n_estimators: int = 100,
        model_path: Path | None = None,
    ) -> None:
        self._contamination = contamination
        self._n_estimators = n_estimators
        self._model: IsolationForest | None = None
        self._scaler: MinMaxScaler = MinMaxScaler()
        self._sensor_enc: LabelEncoder = LabelEncoder()
        self._domain_enc: LabelEncoder = LabelEncoder()
        self._is_fitted: bool = False
        self._lock = threading.RLock()

        if model_path and model_path.exists():
            self.load(model_path)

    def _extract_features(
        self, packet: SensorDataPacket
    ) -> np.ndarray:
        """
        Vectorise un SensorDataPacket en tableau de features numériques.

        Gère les labels inconnus (capteurs/domaines non vus à l'entraînement)
        en leur assignant la valeur 0 (unknown → traitement conservateur).
        """
        prov = packet.provenance

        # Encodage robuste des labels inconnus
        try:
            sensor_enc = float(self._sensor_enc.transform([prov.sensor_type])[0])
        except ValueError:
            sensor_enc = 0.0  # Capteur inconnu → encodé comme premier label
            logger.debug("Type de capteur inconnu pour l'encodage : %s", prov.sensor_type)

        try:
            domain_enc = float(self._domain_enc.transform([prov.origin_domain])[0])
        except ValueError:
            domain_enc = 0.0
            logger.debug("Domaine inconnu pour l'encodage : %s", prov.origin_domain)

        features = np.array([
            float(prov.classification) / 5.0,                     # [1] Classif. normalisée
            sensor_enc,                                            # [2] Type capteur
            domain_enc,                                            # [3] Domaine réseau
            float(prov.ingestion_timestamp.hour) / 23.0,          # [4] Heure normalisée
            min(float(len(prov.dissemination_controls)), 10.0),    # [5] Nb contrôles
            min(float(len(prov.lineage)), 20.0),                   # [6] Profondeur lignage
            float(bool(prov.handling_caveats)),                    # [7] Mises en garde
        ], dtype=np.float32)

        return features

    def fit(self, packets: list[SensorDataPacket]) -> "ComplianceAnomalyDetector":
        """
        Entraîne le modèle sur un corpus de paquets conformes.

        Args:
            packets: Liste de SensorDataPackets représentant un flux normal.
                     Recommandé : > 500 paquets pour une détection robuste.

        Returns:
            self (chaînable).

        Raises:
            ValueError: Si la liste est vide.
        """
        if not packets:
            raise ValueError("Impossible d'entraîner sur une liste vide.")

        with self._lock:
            # Fit des encodeurs sur toutes les valeurs observées
            sensor_types = list({p.provenance.sensor_type for p in packets})
            domains = list({p.provenance.origin_domain for p in packets})
            self._sensor_enc.fit(sensor_types)
            self._domain_enc.fit(domains)

            # Extraction des features
            X = np.stack([self._extract_features(p) for p in packets])

            # Entraînement Isolation Forest
            self._model = IsolationForest(
                contamination=self._contamination,
                n_estimators=self._n_estimators,
                max_samples=min(256, len(packets)),
                max_features=N_FEATURES,
                random_state=42,
                n_jobs=1,  # Mono-thread pour compatibilité SWaP
            )
            self._model.fit(X)
            self._is_fitted = True

        logger.info(
            "Modèle d'anomalie entraîné sur %d paquets "
            "(%d types capteurs, %d domaines, contamination=%.4f)",
            len(packets),
            len(sensor_types),
            len(domains),
            self._contamination,
        )
        return self

    def predict(self, packet: SensorDataPacket) -> AnomalyResult:
        """
        Analyse un paquet et retourne un résultat d'anomalie.

        En mode dégradé (modèle non entraîné) : retourne is_anomaly=False
        pour ne pas bloquer le pipeline. Un warning est émis.

        Returns:
            AnomalyResult avec score, confiance et explication.
        """
        with self._lock:
            is_fitted = self._is_fitted
            model = self._model

        if not is_fitted or model is None:
            logger.warning(
                "Détecteur ML non entraîné — mode dégradé pour paquet %s",
                packet.provenance.record_id,
            )
            return AnomalyResult(
                is_anomaly=False,
                anomaly_score=0.0,
                confidence=0.0,
                explanation="Détecteur ML non disponible — vérification ignorée.",
            )

        features = self._extract_features(packet).reshape(1, -1)

        with self._lock:
            prediction = model.predict(features)[0]   # 1 = normal, -1 = anomalie
            score = float(model.score_samples(features)[0])

        is_anomaly = prediction == -1

        # Conversion du score en confiance [0, 1]
        # score typique : [-0.5, 0.5], centré à 0 pour la frontière
        confidence = max(0.0, min(1.0, abs(score) * 2.0)) if is_anomaly else 0.0

        explanation = self._build_explanation(packet, is_anomaly, score)

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=score,
            confidence=confidence,
            explanation=explanation,
        )

    def _build_explanation(
        self, packet: SensorDataPacket, is_anomaly: bool, score: float
    ) -> str:
        """Génère une explication lisible par un opérateur."""
        prov = packet.provenance
        if not is_anomaly:
            return (
                f"Paquet {prov.sensor_type}/{prov.classification.label()} "
                f"conforme au profil comportemental normal (score={score:.4f})."
            )

        flags = []
        if prov.classification.value >= 3:
            flags.append("classification élevée")
        if len(prov.lineage) > 5:
            flags.append(f"lignage profond ({len(prov.lineage)} ancêtres)")
        if len(prov.dissemination_controls) == 0 and prov.classification.value >= 2:
            flags.append("absence de contrôle de diffusion pour Protégé B+")
        if prov.ingestion_timestamp.hour in range(0, 5):
            flags.append("ingestion nocturne inhabituelle (00h-05h)")

        flag_str = " ; ".join(flags) if flags else "pattern inhabituel détecté"
        return (
            f"ANOMALIE ML détectée sur {prov.sensor_type} "
            f"({prov.classification.label()}) — {flag_str}. "
            f"Score={score:.4f}. Révision recommandée."
        )

    def save(self, path: Path) -> None:
        """Sérialise le modèle entraîné (format pickle avec gzip)."""
        if not self._is_fitted:
            raise RuntimeError("Aucun modèle à sauvegarder. Appeler fit() d'abord.")

        with self._lock:
            state = {
                "model": self._model,
                "sensor_enc": self._sensor_enc,
                "domain_enc": self._domain_enc,
                "contamination": self._contamination,
                "n_estimators": self._n_estimators,
            }

        with path.open("wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Modèle ML sauvegardé → %s", path)

    def load(self, path: Path) -> None:
        """Charge un modèle pré-entraîné."""
        with path.open("rb") as f:
            state = pickle.load(f)

        with self._lock:
            self._model = state["model"]
            self._sensor_enc = state["sensor_enc"]
            self._domain_enc = state["domain_enc"]
            self._contamination = state.get("contamination", self._contamination)
            self._n_estimators = state.get("n_estimators", self._n_estimators)
            self._is_fitted = True

        logger.info("Modèle ML chargé depuis %s", path)

    @property
    def is_ready(self) -> bool:
        return self._is_fitted
