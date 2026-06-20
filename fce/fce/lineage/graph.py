"""
FCE — Couche 2 : Graphe de provenance (Lineage Graph).

Représente le parcours de chaque donnée sous forme de DAG (graphe orienté
acyclique). Propage automatiquement les niveaux de classification selon
le principe de dominance : la sortie d'une fusion hérite toujours du
niveau le plus élevé parmi tous ses ancêtres.

Détecte les violations de flux inter-domaines non autorisés avant
qu'elles n'atteignent le moteur de fusion.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import networkx as nx

from fce.models.data_object import ClassificationLevel, NetworkDomain, SensorDataPacket

logger = logging.getLogger(__name__)


@dataclass
class LineageNode:
    """Nœud dans le graphe de provenance."""
    record_id: str
    classification: ClassificationLevel
    sensor_type: str
    origin_domain: str
    node_type: str          # "ingestion" | "transform" | "fusion" | "output"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


@dataclass
class CrossDomainViolation:
    """Violation de flux inter-domaines détectée dans le graphe."""
    source_id: str
    target_id: str
    source_domain: str
    target_domain: str
    source_classification: ClassificationLevel
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "source_classification": self.source_classification.name,
            "detected_at": self.detected_at.isoformat(),
        }


class ProvenanceGraph:
    """
    Couche 2 du FCE : DAG de provenance thread-safe.

    Chaque nœud représente un paquet de données ou une opération de fusion.
    Chaque arête représente une dépendance de traitement (A → B signifie
    que B dépend de A).

    Garanties :
    - Propagation déterministe du niveau de classification maximum.
    - Détection proactive des violations inter-domaines.
    - Export complet de la piste d'audit en JSON.
    - Thread-safe via RLock (lectures concurrentes autorisées).
    """

    # Paires de domaines autorisées par défaut pour les flux inter-domaines.
    # Configurable via set_allowed_domain_pairs().
    DEFAULT_ALLOWED_PAIRS: set[tuple[str, str]] = {
        (NetworkDomain.UNCLASSIFIED_NET, NetworkDomain.PROTECTED_NET),
        (NetworkDomain.PROTECTED_NET, NetworkDomain.SECRET_NET),
    }

    def __init__(
        self,
        allowed_domain_pairs: set[tuple[str, str]] | None = None,
    ) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()
        self._lock = threading.RLock()
        self._allowed_domain_pairs = (
            allowed_domain_pairs
            if allowed_domain_pairs is not None
            else set(self.DEFAULT_ALLOWED_PAIRS)
        )

    def set_allowed_domain_pairs(
        self, pairs: set[tuple[str, str]]
    ) -> None:
        """Reconfigure les paires de domaines inter-domaines autorisées (hot-reload)."""
        with self._lock:
            self._allowed_domain_pairs = set(pairs)
        logger.info("Paires de domaines autorisées mises à jour : %d paires", len(pairs))

    def add_node(self, node: LineageNode) -> None:
        """Enregistre un nœud dans le graphe."""
        with self._lock:
            self._graph.add_node(
                node.record_id,
                classification=node.classification,
                sensor_type=node.sensor_type,
                origin_domain=node.origin_domain,
                node_type=node.node_type,
                timestamp=node.timestamp.isoformat(),
                metadata=node.metadata,
            )

    def add_packet(
        self, packet: SensorDataPacket, node_type: str = "ingestion"
    ) -> None:
        """Raccourci : crée un nœud depuis un SensorDataPacket."""
        node = LineageNode(
            record_id=packet.provenance.record_id,
            classification=packet.provenance.classification,
            sensor_type=packet.provenance.sensor_type,
            origin_domain=packet.provenance.origin_domain,
            node_type=node_type,
            timestamp=packet.provenance.ingestion_timestamp,
            metadata={
                "sensor_id": packet.provenance.sensor_id,
                "dissemination_controls": packet.provenance.dissemination_controls,
                "handling_caveats": packet.provenance.handling_caveats,
            },
        )
        self.add_node(node)

        # Enregistre les dépendances parentales
        with self._lock:
            for parent_id in packet.provenance.lineage:
                if parent_id in self._graph:
                    self._graph.add_edge(parent_id, packet.provenance.record_id)
                else:
                    logger.warning(
                        "Parent '%s' introuvable dans le graphe pour '%s'",
                        parent_id,
                        packet.provenance.record_id,
                    )

    def add_fusion_edge(self, source_id: str, target_id: str) -> None:
        """
        Enregistre une dépendance de fusion (source contribue à target).

        Raises:
            ValueError: Si l'un des nœuds n'existe pas.
            ValueError: Si l'arête crée un cycle dans le DAG.
        """
        with self._lock:
            if source_id not in self._graph:
                raise ValueError(f"Nœud source inconnu : '{source_id}'")
            if target_id not in self._graph:
                raise ValueError(f"Nœud cible inconnu : '{target_id}'")

            # Vérification d'acyclicité avant ajout
            self._graph.add_edge(source_id, target_id)
            if not nx.is_directed_acyclic_graph(self._graph):
                self._graph.remove_edge(source_id, target_id)
                raise ValueError(
                    f"L'arête {source_id} → {target_id} créerait un cycle. "
                    "Le graphe de provenance doit rester acyclique."
                )

    def compute_output_classification(
        self, node_id: str
    ) -> ClassificationLevel:
        """
        Calcule le niveau de classification de sortie pour un nœud.

        Principe de dominance : niveau = max(niveau de tous les ancêtres).
        Garantit qu'aucune fusion ne produit une sortie sous-classifiée.

        Returns:
            Niveau de classification maximum parmi tous les ancêtres.

        Raises:
            ValueError: Si le nœud n'existe pas dans le graphe.
        """
        with self._lock:
            if node_id not in self._graph:
                raise ValueError(f"Nœud inconnu : '{node_id}'")

            ancestors = nx.ancestors(self._graph, node_id)
            ancestors.add(node_id)

            max_level = ClassificationLevel.UNCLASSIFIED
            for nid in ancestors:
                level = self._graph.nodes[nid].get(
                    "classification", ClassificationLevel.UNCLASSIFIED
                )
                if level > max_level:
                    max_level = level

        return max_level

    def detect_cross_domain_violations(self) -> list[CrossDomainViolation]:
        """
        Scanne toutes les arêtes et détecte les flux inter-domaines non autorisés.

        Une violation = arête entre deux nœuds de domaines différents
        dont la paire n'est pas dans la liste des paires autorisées.

        Returns:
            Liste des violations détectées (vide si tout est conforme).
        """
        violations: list[CrossDomainViolation] = []
        with self._lock:
            edges = list(self._graph.edges)
            allowed = set(self._allowed_domain_pairs)

        for source_id, target_id in edges:
            src_domain = self._graph.nodes[source_id].get("origin_domain", "")
            tgt_domain = self._graph.nodes[target_id].get("origin_domain", "")

            if src_domain != tgt_domain:
                pair = (src_domain, tgt_domain)
                if pair not in allowed:
                    violations.append(
                        CrossDomainViolation(
                            source_id=source_id,
                            target_id=target_id,
                            source_domain=src_domain,
                            target_domain=tgt_domain,
                            source_classification=self._graph.nodes[source_id].get(
                                "classification", ClassificationLevel.UNCLASSIFIED
                            ),
                        )
                    )

        if violations:
            logger.warning(
                "%d violation(s) inter-domaines détectée(s)", len(violations)
            )

        return violations

    def get_full_lineage(self, node_id: str) -> list[str]:
        """
        Retourne la liste ordonnée de tous les ancêtres d'un nœud
        (du plus ancien au plus récent), nœud cible inclus.
        """
        with self._lock:
            if node_id not in self._graph:
                raise ValueError(f"Nœud inconnu : '{node_id}'")
            ancestors = nx.ancestors(self._graph, node_id)

        # Tri topologique pour un ordre cohérent
        subgraph = self._graph.subgraph(ancestors | {node_id})
        try:
            ordered = list(nx.topological_sort(subgraph))
        except nx.NetworkXUnfeasible:
            ordered = list(ancestors) + [node_id]

        return ordered

    def export_audit_trail(self, node_id: str) -> dict:
        """
        Exporte la piste d'audit complète d'un nœud en dictionnaire sérialisable.

        Contient :
        - Le nœud cible et son niveau de classification calculé.
        - La chaîne de lignage complète avec métadonnées.
        - Les violations inter-domaines sur la chaîne de lignage.
        """
        lineage = self.get_full_lineage(node_id)
        computed_class = self.compute_output_classification(node_id)

        with self._lock:
            lineage_chain = [
                {
                    "id": nid,
                    "classification": self._graph.nodes[nid]
                    .get("classification", ClassificationLevel.UNCLASSIFIED)
                    .name,
                    "sensor_type": self._graph.nodes[nid].get("sensor_type", ""),
                    "origin_domain": self._graph.nodes[nid].get("origin_domain", ""),
                    "node_type": self._graph.nodes[nid].get("node_type", ""),
                    "timestamp": self._graph.nodes[nid].get("timestamp", ""),
                    "metadata": self._graph.nodes[nid].get("metadata", {}),
                }
                for nid in lineage
            ]

        violations = [
            v.to_dict()
            for v in self.detect_cross_domain_violations()
            if v.source_id in lineage or v.target_id in lineage
        ]

        return {
            "target_node": node_id,
            "computed_classification": computed_class.name,
            "computed_classification_label": computed_class.label(),
            "lineage_depth": len(lineage),
            "lineage_chain": lineage_chain,
            "cross_domain_violations": violations,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def export_to_json(self, path: Path) -> None:
        """Sérialise le graphe complet en JSON (pour analyse forensique)."""
        with self._lock:
            nodes = [
                {
                    "id": nid,
                    **{
                        k: v.name if isinstance(v, ClassificationLevel) else v
                        for k, v in self._graph.nodes[nid].items()
                    },
                }
                for nid in self._graph.nodes
            ]
            edges = [
                {"source": src, "target": tgt}
                for src, tgt in self._graph.edges
            ]

        data = {
            "nodes": nodes,
            "edges": edges,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Graphe exporté : %d nœuds, %d arêtes → %s",
                    len(nodes), len(edges), path)

    @property
    def node_count(self) -> int:
        with self._lock:
            return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        with self._lock:
            return self._graph.number_of_edges()
