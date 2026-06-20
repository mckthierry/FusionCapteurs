"""Tests unitaires — Couche 2 : Graphe de provenance."""
import pytest
from pathlib import Path

from fce.lineage.graph import CrossDomainViolation, LineageNode, ProvenanceGraph
from fce.models.data_object import (
    ClassificationLevel,
    NetworkDomain,
    SensorDataPacket,
    SensorType,
)


def make_packet(
    sensor_type: str = SensorType.RADAR,
    classification: ClassificationLevel = ClassificationLevel.UNCLASSIFIED,
    domain: str = NetworkDomain.UNCLASSIFIED_NET,
    lineage: list[str] | None = None,
) -> SensorDataPacket:
    return SensorDataPacket.create(
        sensor_id=f"{sensor_type}-TEST",
        sensor_type=sensor_type,
        classification=classification,
        origin_domain=domain,
        payload=None,
        lineage=lineage or [],
    )


@pytest.fixture
def graph() -> ProvenanceGraph:
    return ProvenanceGraph()


class TestProvenanceGraphNodes:
    def test_add_packet(self, graph: ProvenanceGraph):
        pkt = make_packet()
        graph.add_packet(pkt)
        assert graph.node_count == 1

    def test_add_multiple_packets(self, graph: ProvenanceGraph):
        for _ in range(5):
            graph.add_packet(make_packet())
        assert graph.node_count == 5

    def test_add_node_directly(self, graph: ProvenanceGraph):
        import uuid
        node = LineageNode(
            record_id=str(uuid.uuid4()),
            classification=ClassificationLevel.PROTECTED_B,
            sensor_type=SensorType.SIGINT,
            origin_domain=NetworkDomain.SECRET_NET,
            node_type="ingestion",
        )
        graph.add_node(node)
        assert graph.node_count == 1


class TestProvenanceGraphEdges:
    def test_add_fusion_edge(self, graph: ProvenanceGraph):
        pkt_a = make_packet(sensor_type=SensorType.UAS)
        pkt_b = make_packet(sensor_type=SensorType.RADAR)
        graph.add_packet(pkt_a)
        graph.add_packet(pkt_b)
        graph.add_fusion_edge(pkt_a.provenance.record_id, pkt_b.provenance.record_id)
        assert graph.edge_count == 1

    def test_lineage_edges_created_automatically(self, graph: ProvenanceGraph):
        parent = make_packet(sensor_type=SensorType.UAS)
        graph.add_packet(parent)
        child = make_packet(
            sensor_type=SensorType.RADAR,
            lineage=[parent.provenance.record_id],
        )
        graph.add_packet(child)
        assert graph.edge_count == 1

    def test_cycle_detection(self, graph: ProvenanceGraph):
        """Le graphe doit refuser les cycles."""
        pkt_a = make_packet(sensor_type=SensorType.UAS)
        pkt_b = make_packet(sensor_type=SensorType.RADAR)
        graph.add_packet(pkt_a)
        graph.add_packet(pkt_b)
        graph.add_fusion_edge(pkt_a.provenance.record_id, pkt_b.provenance.record_id)

        with pytest.raises(ValueError, match="cycle"):
            graph.add_fusion_edge(
                pkt_b.provenance.record_id, pkt_a.provenance.record_id
            )

    def test_edge_unknown_source_raises(self, graph: ProvenanceGraph):
        pkt = make_packet()
        graph.add_packet(pkt)
        with pytest.raises(ValueError, match="Nœud source inconnu"):
            graph.add_fusion_edge("nonexistent-id", pkt.provenance.record_id)

    def test_edge_unknown_target_raises(self, graph: ProvenanceGraph):
        pkt = make_packet()
        graph.add_packet(pkt)
        with pytest.raises(ValueError, match="Nœud cible inconnu"):
            graph.add_fusion_edge(pkt.provenance.record_id, "nonexistent-id")


class TestClassificationDominance:
    def test_single_node_classification(self, graph: ProvenanceGraph):
        pkt = make_packet(classification=ClassificationLevel.PROTECTED_B)
        graph.add_packet(pkt)
        result = graph.compute_output_classification(pkt.provenance.record_id)
        assert result == ClassificationLevel.PROTECTED_B

    def test_dominance_principle_max(self, graph: ProvenanceGraph):
        """La classification de sortie = max des ancêtres."""
        low = make_packet(classification=ClassificationLevel.UNCLASSIFIED)
        mid = make_packet(
            classification=ClassificationLevel.PROTECTED_B,
            lineage=[low.provenance.record_id],
        )
        graph.add_packet(low)
        graph.add_packet(mid)

        result = graph.compute_output_classification(mid.provenance.record_id)
        assert result == ClassificationLevel.PROTECTED_B

    def test_dominance_three_level_chain(self, graph: ProvenanceGraph):
        """Secret dans la chaîne → sortie = Secret."""
        unclass = make_packet(classification=ClassificationLevel.UNCLASSIFIED)
        prot_b = make_packet(
            classification=ClassificationLevel.PROTECTED_B,
            lineage=[unclass.provenance.record_id],
        )
        secret = make_packet(
            sensor_type=SensorType.SIGINT,
            classification=ClassificationLevel.SECRET,
            domain=NetworkDomain.SECRET_NET,
            lineage=[unclass.provenance.record_id, prot_b.provenance.record_id],
        )
        graph.add_packet(unclass)
        graph.add_packet(prot_b)
        graph.add_packet(secret)

        result = graph.compute_output_classification(secret.provenance.record_id)
        assert result == ClassificationLevel.SECRET

    def test_unknown_node_raises(self, graph: ProvenanceGraph):
        with pytest.raises(ValueError, match="Nœud inconnu"):
            graph.compute_output_classification("nonexistent-id")

    def test_no_downgrade_possible(self, graph: ProvenanceGraph):
        """La dominance empêche toujours la sous-classification."""
        high = make_packet(
            classification=ClassificationLevel.PROTECTED_B,
            domain=NetworkDomain.SECRET_NET,
        )
        low = make_packet(
            classification=ClassificationLevel.UNCLASSIFIED,
            lineage=[high.provenance.record_id],
        )
        graph.add_packet(high)
        graph.add_packet(low)

        # La sortie ne peut jamais être inférieure à PROTECTED_B (ancêtre)
        result = graph.compute_output_classification(low.provenance.record_id)
        assert result >= ClassificationLevel.PROTECTED_B


class TestCrossDomainViolations:
    def test_no_violations_same_domain(self, graph: ProvenanceGraph):
        pkt_a = make_packet(domain=NetworkDomain.PROTECTED_NET)
        pkt_b = make_packet(
            domain=NetworkDomain.PROTECTED_NET,
            lineage=[pkt_a.provenance.record_id],
        )
        graph.add_packet(pkt_a)
        graph.add_packet(pkt_b)
        violations = graph.detect_cross_domain_violations()
        assert violations == []

    def test_violation_unauth_cross_domain(self):
        """Un flux de SECRET_NET vers UNCLASSIFIED_NET non autorisé → violation."""
        graph = ProvenanceGraph(allowed_domain_pairs=set())  # Aucune paire autorisée
        pkt_a = make_packet(
            classification=ClassificationLevel.SECRET,
            domain=NetworkDomain.SECRET_NET,
        )
        pkt_b = make_packet(
            domain=NetworkDomain.UNCLASSIFIED_NET,
            lineage=[pkt_a.provenance.record_id],
        )
        graph.add_packet(pkt_a)
        graph.add_packet(pkt_b)
        violations = graph.detect_cross_domain_violations()
        assert len(violations) == 1
        assert violations[0].source_domain == NetworkDomain.SECRET_NET
        assert violations[0].target_domain == NetworkDomain.UNCLASSIFIED_NET

    def test_authorized_cross_domain_no_violation(self):
        """Paire de domaines explicitement autorisée → pas de violation."""
        allowed = {(NetworkDomain.PROTECTED_NET, NetworkDomain.SECRET_NET)}
        graph = ProvenanceGraph(allowed_domain_pairs=allowed)
        pkt_a = make_packet(domain=NetworkDomain.PROTECTED_NET)
        pkt_b = make_packet(
            domain=NetworkDomain.SECRET_NET,
            lineage=[pkt_a.provenance.record_id],
        )
        graph.add_packet(pkt_a)
        graph.add_packet(pkt_b)
        violations = graph.detect_cross_domain_violations()
        assert violations == []

    def test_hot_reload_domain_pairs(self, graph: ProvenanceGraph):
        """Mise à jour dynamique des paires autorisées."""
        graph.set_allowed_domain_pairs(set())  # Aucune paire autorisée

        pkt_a = make_packet(domain=NetworkDomain.PROTECTED_NET)
        pkt_b = make_packet(
            domain=NetworkDomain.SECRET_NET,
            lineage=[pkt_a.provenance.record_id],
        )
        graph.add_packet(pkt_a)
        graph.add_packet(pkt_b)

        # Avant hot-reload → violation
        violations_before = graph.detect_cross_domain_violations()
        assert len(violations_before) == 1

        # Après hot-reload → autorisé
        graph.set_allowed_domain_pairs(
            {(NetworkDomain.PROTECTED_NET, NetworkDomain.SECRET_NET)}
        )
        violations_after = graph.detect_cross_domain_violations()
        assert len(violations_after) == 0


class TestAuditTrailExport:
    def test_export_audit_trail(self, graph: ProvenanceGraph):
        pkt = make_packet(classification=ClassificationLevel.PROTECTED_B)
        graph.add_packet(pkt)
        trail = graph.export_audit_trail(pkt.provenance.record_id)
        assert trail["target_node"] == pkt.provenance.record_id
        assert trail["computed_classification"] == "PROTECTED_B"
        assert len(trail["lineage_chain"]) >= 1
        assert "exported_at" in trail

    def test_export_to_json(self, graph: ProvenanceGraph, tmp_path: Path):
        pkt = make_packet()
        graph.add_packet(pkt)
        out = tmp_path / "graph.json"
        graph.export_to_json(out)
        assert out.exists()
        import json
        data = json.loads(out.read_text())
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 1

    def test_full_lineage_order(self, graph: ProvenanceGraph):
        """La chaîne de lignage retourne les nœuds dans l'ordre topologique."""
        grandparent = make_packet(sensor_type=SensorType.UAS)
        parent = make_packet(
            sensor_type=SensorType.RADAR,
            lineage=[grandparent.provenance.record_id],
        )
        child = make_packet(
            sensor_type=SensorType.EO_IR,
            domain=NetworkDomain.PROTECTED_NET,
            lineage=[parent.provenance.record_id],
        )
        graph.add_packet(grandparent)
        graph.add_packet(parent)
        graph.add_packet(child)

        lineage = graph.get_full_lineage(child.provenance.record_id)
        assert lineage[-1] == child.provenance.record_id
        assert grandparent.provenance.record_id in lineage
        assert parent.provenance.record_id in lineage
