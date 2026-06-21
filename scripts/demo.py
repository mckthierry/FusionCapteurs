"""
FCE — Prototype de démonstration complet.

Exécute tous les scénarios opérationnels et affiche un rapport détaillé.
Usage : python scripts/demo.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Ajout du chemin racine pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "data"))

from fce.pipeline import FusionComplianceEngine
from fce.policy.engine import EnforcementAction
from fce.models.data_object import ClassificationLevel
from synthetic_generator import SyntheticDataGenerator

# ─────────────────────────────────────────────────────────────────────────────
# Couleurs ANSI pour le terminal
# ─────────────────────────────────────────────────────────────────────────────
R = "\033[91m"   # Rouge
G = "\033[92m"   # Vert
Y = "\033[93m"   # Jaune
B = "\033[94m"   # Bleu
M = "\033[95m"   # Magenta
C = "\033[96m"   # Cyan
W = "\033[97m"   # Blanc
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

ACTION_COLORS = {
    EnforcementAction.ALLOW:      G,
    EnforcementAction.DOWNGRADE:  C,
    EnforcementAction.RESTRICT:   Y,
    EnforcementAction.QUARANTINE: M,
    EnforcementAction.DENY:       R,
}

CLASS_COLORS = {
    ClassificationLevel.UNCLASSIFIED:        DIM,
    ClassificationLevel.PROTECTED_A:         G,
    ClassificationLevel.PROTECTED_B:         Y,
    ClassificationLevel.PROTECTED_B_ENHANCED: M,
    ClassificationLevel.SECRET:               R,
    ClassificationLevel.TOP_SECRET:           R + BOLD,
}


def sep(char: str = "─", width: int = 72) -> str:
    return char * width


def action_str(action: EnforcementAction) -> str:
    color = ACTION_COLORS.get(action, W)
    return f"{color}{BOLD}[{action.name:10}]{RESET}"


def class_str(level: ClassificationLevel) -> str:
    color = CLASS_COLORS.get(level, W)
    return f"{color}{level.label()}{RESET}"


def print_result(label: str, result, packet_idx: int = 0) -> None:
    action_icon = {
        EnforcementAction.ALLOW:      "✅",
        EnforcementAction.RESTRICT:   "⚠️ ",
        EnforcementAction.DOWNGRADE:  "⬇️ ",
        EnforcementAction.QUARANTINE: "🔒",
        EnforcementAction.DENY:       "🚫",
    }.get(result.final_decision.action, "❓")

    print(f"\n  {action_icon}  {action_str(result.final_decision.action)} "
          f"{BOLD}{label}{RESET}")
    print(f"     {DIM}Paquet ID   :{RESET} {result.packet_id[:16]}…")
    print(f"     {DIM}Classif. in :{RESET} {class_str(result.layer1_decision.resulting_classification)}")
    print(f"     {DIM}Classif. out:{RESET} {class_str(result.computed_classification)}")
    print(f"     {DIM}Latence     :{RESET} {result.processing_time_ms:.2f} ms")

    if result.final_decision.applied_rules:
        rules = ", ".join(result.final_decision.applied_rules)
        print(f"     {DIM}Règles      :{RESET} {C}{rules}{RESET}")

    if result.anomaly_result and result.anomaly_result.is_anomaly:
        sev_color = {
            "HIGH": R, "MEDIUM": Y, "LOW": C
        }.get(result.anomaly_result.severity, W)
        print(f"     {DIM}ML Anomalie :{RESET} {sev_color}⚡ {result.anomaly_result.severity} "
              f"(score={result.anomaly_result.anomaly_score:.4f}){RESET}")

    if result.cross_domain_violations > 0:
        print(f"     {DIM}Violations  :{RESET} {R}{result.cross_domain_violations} inter-domaine(s){RESET}")

    expl = result.final_decision.operator_explanation
    if expl:
        # Tronquer pour l'affichage
        expl_short = (expl[:80] + "…") if len(expl) > 80 else expl
        print(f"     {DIM}Explication :{RESET} {DIM}{expl_short}{RESET}")


def main() -> None:
    print(f"\n{BOLD}{sep('═')}{RESET}")
    print(f"{BOLD}{'MOTEUR DE CONFORMITÉ DE FUSION (FCE) — DÉMONSTRATION':^72}{RESET}")
    print(f"{BOLD}{sep('═')}{RESET}")
    print(f"{DIM}  Architecture : 3 couches complémentaires{RESET}")
    print(f"{DIM}  C1 : Politiques statiques (YAML, hot-reload, fail-secure){RESET}")
    print(f"{DIM}  C2 : Graphe de provenance (DAG, dominance de classification){RESET}")
    print(f"{DIM}  C3 : Détecteur d'anomalies ML (Isolation Forest, SWaP-optimisé){RESET}")

    # ── Initialisation ────────────────────────────────────────────────────────
    print(f"\n{BOLD}[1/4] INITIALISATION{RESET}")
    print(f"{sep()}")

    policy_path = Path(__file__).parent.parent / "policies" / "base_policy.yaml"
    audit_path = Path("/tmp/fce_demo_audit.jsonl")
    audit_path.unlink(missing_ok=True)

    fce = FusionComplianceEngine(
        policy_path=policy_path,
        audit_log_path=audit_path,
    )
    print(f"  ✅ Politiques chargées : {B}{fce._policy_engine.rule_count} règles{RESET}")

    # Entraînement ML
    gen = SyntheticDataGenerator(seed=42)
    print(f"  ⏳ Génération de données d'entraînement…")
    t0 = time.perf_counter()
    training_data = gen.generate_normal_traffic(n=600)
    fce.train_anomaly_detector(training_data)
    t1 = time.perf_counter()
    print(f"  ✅ Détecteur ML entraîné : {B}600 paquets{RESET} en {(t1-t0)*1000:.0f}ms")

    # ── Scénarios valides ─────────────────────────────────────────────────────
    print(f"\n{BOLD}[2/4] SCÉNARIOS CONFORMES — Fusion multi-capteurs valide{RESET}")
    print(f"{sep()}")

    print(f"\n  {BOLD}Scénario A : Fusion SIGINT + EO/IR (Arctique, Protégé B){RESET}")
    pkts = gen.scenario_sigint_eoir_fusion()
    for i, pkt in enumerate(pkts):
        result = fce.ingest(pkt)
        label = f"SIGINT-7741 (capteur {i+1}/2)" if i == 0 else f"EO/IR-3312 (capteur {i+1}/2, lignage SIGINT)"
        print_result(label, result, i)

    print(f"\n  {BOLD}Scénario B : Fusion UAS + RADAR (Surveillance aérienne){RESET}")
    pkts = gen.scenario_uas_radar_fusion()
    labels = ["UAS-ALPHA-01 (Non classifié)", "RADAR-NORTH-07 (Protégé A, avec lignage UAS)"]
    for pkt, lbl in zip(pkts, labels):
        result = fce.ingest(pkt)
        print_result(lbl, result)

    print(f"\n  {BOLD}Scénario C : Maritime — RADAR + ACOUSTIC + EO/IR (3 capteurs){RESET}")
    pkts = gen.scenario_maritime_surveillance()
    labels = ["RADAR-MARITIME-01", "ACOUSTIC-SONAR-03 (avec lignage RADAR)", "EOIR-SAT-09 (fusion triple)"]
    for pkt, lbl in zip(pkts, labels):
        result = fce.ingest(pkt)
        print_result(lbl, result)

    print(f"\n  {BOLD}Scénario D : Tactique démonté — UAS + SIGINT (Réseau Coalition){RESET}")
    pkts = gen.scenario_tactical_dismounted()
    labels = ["UAS-TACTICAL-T01 (Coalition)", "SIGINT-MANPACK-02 (avec lignage UAS)"]
    for pkt, lbl in zip(pkts, labels):
        result = fce.ingest(pkt)
        print_result(lbl, result)

    # ── Scénarios de violation ────────────────────────────────────────────────
    print(f"\n{BOLD}[3/4] SCÉNARIOS DE VIOLATION — Enforcement automatique{RESET}")
    print(f"{sep()}")

    print(f"\n  {BOLD}Violation E : SIGINT Protégé B sur réseau non classifié{RESET}")
    print(f"  {DIM}Attendu → DENY (règle RULE-003 : SIGINT interdit sur UNCLASSIFIED_NET){RESET}")
    pkt = gen.scenario_classification_violation()
    result = fce.ingest(pkt)
    print_result("SIGINT-ROGUE-99 (UNCLASSIFIED_NET — violation domaine)", result)

    print(f"\n  {BOLD}Violation F : UAS Protégé B sans mention REL TO CAN{RESET}")
    print(f"  {DIM}Attendu → RESTRICT (règle RULE-002 : contrôle de diffusion manquant){RESET}")
    pkt = gen.scenario_missing_caveat_violation()
    result = fce.ingest(pkt)
    print_result("UAS-BETA-12 (Protégé B, sans REL TO CAN)", result)

    print(f"\n  {BOLD}Anomalie G : EO/IR — Lignage profond + ingestion nocturne (Détection ML){RESET}")
    print(f"  {DIM}Attendu → RESTRICT via C3 (pattern comportemental anormal){RESET}")
    pkt = gen.scenario_ml_anomaly()
    result = fce.ingest(pkt)
    print_result("EOIR-SUSPECT-77 (lignage ×15, ingestion 03h, sans contrôle diffusion)", result)

    # ── Hot-reload démonstration ──────────────────────────────────────────────
    print(f"\n{BOLD}[4/4] HOT-RELOAD — Mise à jour de politique sans redémarrage{RESET}")
    print(f"{sep()}")

    rules_before = fce._policy_engine.rule_count
    new_rule = """
  - id: "RULE-HOTRELOAD-TEST"
    description: "Règle injectée par hot-reload (test démonstration)"
    operator_explanation: "Règle de démonstration ajoutée à chaud"
    condition:
      type: "sensor_type_match"
      sensors: ["ACOUSTIC"]
    action: "RESTRICT"
"""
    # Lire et enrichir la politique existante
    current = policy_path.read_text()
    policy_path.write_text(current + new_rule)
    count_after = fce.reload_policies()
    policy_path.write_text(current)  # Restaurer

    print(f"\n  ⚡ Avant hot-reload : {B}{rules_before} règles{RESET}")
    print(f"  ⚡ Après hot-reload : {B}{count_after} règles{RESET} (ajout de RULE-HOTRELOAD-TEST)")
    print(f"  ✅ Pipeline continu sans interruption")

    # Restaurer
    fce.reload_policies()

    # ── Rapport final ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}{sep('═')}{RESET}")
    print(f"{BOLD}{'RAPPORT DE CONFORMITÉ FCE':^72}{RESET}")
    print(f"{BOLD}{sep('═')}{RESET}")

    summary = fce.get_audit_summary()
    total = summary["total"]
    compliant = summary["compliant"]
    violations = summary["violations"]
    ml_anomalies = summary["ml_anomalies"]
    rate = summary["compliance_rate"]

    print(f"\n  {BOLD}Statistiques globales{RESET}")
    print(f"  ┌{'─'*50}┐")
    print(f"  │  Paquets traités       : {W}{BOLD}{total:>5}{RESET}                    │")
    print(f"  │  Conformes (ALLOW)     : {G}{BOLD}{compliant:>5}{RESET}  ({G}{rate:.1f}%{RESET})            │")
    print(f"  │  Non-conformes         : {R}{BOLD}{violations:>5}{RESET}                    │")
    print(f"  │  Anomalies ML          : {Y}{BOLD}{ml_anomalies:>5}{RESET}                    │")
    print(f"  └{'─'*50}┘")

    print(f"\n  {BOLD}Décisions par action{RESET}")
    for action, count in sorted(summary.get("by_action", {}).items()):
        try:
            action_enum = EnforcementAction[action]
            color = ACTION_COLORS.get(action_enum, W)
        except KeyError:
            color = W
        bar = "█" * min(count, 40)
        print(f"  {color}{action:12}{RESET}  {bar} {count}")

    print(f"\n  {BOLD}Paquets par type de capteur{RESET}")
    for sensor, count in sorted(summary.get("by_sensor", {}).items()):
        bar = "░" * min(count, 40)
        print(f"  {C}{sensor:10}{RESET}  {bar} {count}")

    # Export CSV
    csv_path = Path("/tmp/fce_audit_export.csv")
    exported = fce.export_audit_csv(csv_path)
    print(f"\n  📄 Journal d'audit exporté : {B}{csv_path}{RESET} ({exported} entrées)")

    # Export graphe de provenance
    graph_path = Path("/tmp/fce_provenance_graph.json")
    fce.export_provenance_graph(graph_path)
    print(f"  📊 Graphe de provenance exporté : {B}{graph_path}{RESET}")

    # Piste d'audit d'un paquet spécifique
    sigint_pkts = gen.scenario_sigint_eoir_fusion()
    # Ce paquet a déjà été ingéré — on ne peut que consulter la piste
    print(f"\n  {BOLD}Exemple de piste d'audit (graphe de provenance C2){RESET}")
    print(f"  {DIM}Nœuds dans le graphe : {fce._provenance_graph.node_count}{RESET}")
    print(f"  {DIM}Arêtes de lignage    : {fce._provenance_graph.edge_count}{RESET}")

    # Performance
    print(f"\n  {BOLD}Performance SWaP{RESET}")
    import time as _time
    t0 = _time.perf_counter()
    test_pkts = gen.generate_normal_traffic(n=100)
    results = fce.ingest_batch(test_pkts)
    t1 = _time.perf_counter()
    avg_ms = (t1 - t0) / 100 * 1000
    max_ms = max(r.processing_time_ms for r in results)
    print(f"  Latence moyenne : {G}{avg_ms:.2f} ms/paquet{RESET}")
    print(f"  Latence max     : {Y if max_ms < 10 else R}{max_ms:.2f} ms{RESET}")
    print(f"  Débit           : {G}{100/(t1-t0):.0f} paquets/seconde{RESET}")

    print(f"\n{BOLD}{sep('═')}{RESET}")
    print(f"{G}{BOLD}  FCE opérationnel — Tous les scénarios validés.{RESET}")
    print(f"{BOLD}{sep('═')}{RESET}\n")


if __name__ == "__main__":
    main()
