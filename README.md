# FCE — Moteur de Conformité de Fusion

> Architecture tri-couche d'enforcement automatique de conformité pour la fusion multi-sensorielle et multi-domaines  
> Défi : Fusion Capteurs — FusionCapteurs/sprint/fce-analyse-v1  
> **Sprint courant : sprint/fce-analyse-v1 — en cours**

---

## À propos

Ce dépôt contient l'analyse, le prototype et les livrables du **Moteur de Conformité de Fusion (FCE)**
pour la fusion de données multi-capteurs (UAS, SIGINT, EO/IR, RADAR, ACOUSTIC) avec enforcement
automatique de conformité, classification et traçabilité complète.

Le FCE applique les règles de classification, les contraintes juridiques et le respect des
politiques en temps réel lors de l'agrégation et de l'analyse des données, sans validation
humaine pour les conditions de politique prédéfinies.

Architecture fondée sur trois couches complémentaires : moteur de politiques YAML fail-secure,
graphe de provenance DAG avec propagation de dominance, et détecteur d'anomalies ML léger
optimisé pour les contraintes SWaP de déploiement périphérique.

---

## Workflow

Ce repo opère selon un cycle à trois nœuds :

```
Claude Code Web  ←──────→  GitHub  ←──────→  Humain
(analyse/code)             (vérité)          (décision/supervision)
```

Chaque session commence par la lecture de `STATUS.md` puis du dernier `brainstorm/BR-FCE-*.md`
depuis la branche active. Elle se termine par un commit structuré. L'humain supervise sur GitHub.

**Modèles utilisés par tâche :**

| Tâche | Modèle | Rôle |
|---|---|---|
| Analyse architecture, gap analysis | claude-opus-4-6 + extended thinking | session directe |
| Développement Python, tests | claude-sonnet-4-6 | `dev` |
| Vérification couverture, métriques | claude-haiku-4-5 | `verificateur` |
| Audit sprint (REV-SX) | claude-opus-4-6 + extended thinking | `analyste` |
| Revue adversariale | claude-sonnet-4-6 × 4 | `persona-[a/b/c/d]` |

---

## Structure du dépôt

```
FusionCapteurs/
│
├── README.md               ← ce fichier
├── STATUS.md               ← état courant, mis à jour chaque session
├── GLOSSAIRE.md            ← vocabulaire unifié FCE
│
├── fce/                    ← code source Python du moteur FCE
│   ├── models/
│   │   └── data_object.py  ← ClassificationLevel, ProvenanceRecord, SensorDataPacket
│   ├── policy/
│   │   └── engine.py       ← Couche 1 : PolicyEngine (YAML, hot-reload, fail-secure)
│   ├── lineage/
│   │   └── graph.py        ← Couche 2 : ProvenanceGraph (DAG, dominance classification)
│   ├── ml/
│   │   └── anomaly_detector.py  ← Couche 3 : IsolationForest (SWaP-optimisé)
│   ├── audit/
│   │   └── logger.py       ← Journal JSONL append-only, export CSV
│   └── pipeline.py         ← Orchestrateur FCEResult
│
├── tests/                  ← 95 tests unitaires et d'intégration (pytest)
│   ├── test_models.py
│   ├── test_policy_engine.py
│   ├── test_lineage_graph.py
│   ├── test_ml_and_audit.py
│   └── test_integration.py
│
├── policies/
│   └── base_policy.yaml    ← 5 règles de conformité lisibles par machine
│
├── data/
│   └── synthetic_generator.py  ← 7 scénarios opérationnels synthétiques
│
├── scripts/
│   └── demo.py             ← Prototype de démonstration complet
│
├── brainstorm/             ← archives de session BR-FCE-*.md
│   └── BR-FCE-001.md
│
└── reviews/                ← audits sprint REV-SX.md
    └── REV-S1.md
```

---

## Plan de sprints

| Sprint | Périmètre | Livrable principal |
|---|---|---|
| S1 — Analyse & prototype | Architecture 3 couches, code Python, 95 tests | fce/, tests/, demo.py, REV-S1.md |
| S2 — Validation scénarios | Scénarios opérationnels, données synthétiques | data/, policies/, BR-FCE-002.md |
| S3 — Hardening SWaP | Optimisation périphérie, benchmarks latence | benchmarks/, REV-S2.md |
| S4 — Documentation | Spécification formelle, guide opérateur | docs/, GLOSSAIRE.md complet |

---

## Démarrage rapide

### Prérequis

```bash
python >= 3.11
pip install networkx scikit-learn numpy pyyaml pytest pytest-cov
```

### Installation

```bash
git clone https://github.com/mckthierry/FusionCapteurs.git
cd FusionCapteurs
git checkout sprint/fce-analyse-v1
pip install -e .
```

### Lancer les tests

```bash
pytest tests/ -v --tb=short
# 95 passed — couverture 93%
```

### Lancer la démonstration

```bash
python scripts/demo.py
```

---

## Règles opérationnelles

| Règle | Contrainte |
|---|---|
| R-FAIL-01 | Le FCE opère toujours en mode fail-secure — en cas de conflit de règles, la décision la plus restrictive l'emporte |
| R-CLASS-01 | La classification de sortie d'une fusion est toujours ≥ max(classification de toutes les sources) |
| R-AUDIT-01 | Chaque paquet ingéré produit exactement une entrée dans le journal d'audit JSONL, jamais modifiée après écriture |
| R-LATENCY-01 | Latence cible ≤ 50 ms par paquet sur CPU embarqué (déploiement périphérique SWaP) |
| R-POLICY-01 | Les politiques YAML sont rechargées à chaud sans redémarrage du pipeline |
| R-ML-01 | Le détecteur ML (Couche 3) se dégrade gracieusement si non entraîné — le pipeline ne s'arrête jamais |

---

## Architecture des 3 couches

```
[Capteurs : UAS · SIGINT · EO/IR · RADAR · ACOUSTIC]
                        │
                [Ingestion — ProvenanceRecord]
                        │
        ┌───────────────┼───────────────────┐
        │               │                   │
  [C1 : Policy    [C2 : Provenance    [C3 : ML Anomaly
   Engine]         Graph (DAG)]        Detector]
  YAML fail-secure  Dominance classif.  IsolationForest
  hot-reload        Cross-domain check  SWaP < 1ms
        │               │                   │
        └───────────────┴───────────────────┘
                        │
              [Fusion décision fail-secure]
                        │
           [Journal Audit JSONL — append-only]
                        │
        ┌───────────────┼───────────────────┐
   [Données        [Graphe             [Export CSV
    labellisées]    provenance JSON]    accréditation]
```

---

## Convention de commits

```
[S1] description              ← livrables Sprint 1
[CORR-S1-M1] description      ← correction post-REV manquement M1
[POLICY] description          ← modification policies/base_policy.yaml
[TEST] description            ← ajout ou correction tests
[STATUS] description          ← mise à jour STATUS.md uniquement
```

---

## Critères de succès

| Critère | Seuil | Statut |
|---|---|---|
| Couverture tests | ≥ 90% | SATISFAIT — 93% Sprint 1 |
| Latence pipeline | ≤ 50 ms/paquet | SATISFAIT — 13 ms moyen Sprint 1 |
| Probabilité violation | < 0,1% | EN COURS — à valider sur corpus étendu |
| Capteurs couverts | ≥ 2 types | SATISFAIT — 5 types (UAS, SIGINT, EO/IR, RADAR, ACOUSTIC) |
| Niveaux classification | ≥ Protégé B | SATISFAIT — 6 niveaux (NC à Très Secret) |
| Hot-reload politiques | sans redémarrage | SATISFAIT — validé Sprint 1 |
| Piste d'audit exportable | CSV + JSON | SATISFAIT — validé Sprint 1 |

---

*README.md v1.0 — Sprint 1 — FCE FusionCapteurs — 2026-06-20*
*Architecture : 3 couches complémentaires, 95 tests, couverture 93%*
