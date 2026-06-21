# STATUS.md — État courant FCE FusionCapteurs

**Mise à jour** : 2026-06-20
**Sprint courant** : Sprint 1 — TERMINÉ (95 tests passés, couverture 93%, latence 13 ms)
**Prochain sprint** : Sprint 2 — Validation scénarios opérationnels étendus
**Branche active** : sprint/fce-analyse-v1

---

## 1. Sprints

| Sprint | Périmètre | Statut | Livrable principal |
|--------|-----------|--------|--------------------|
| S1 | Architecture 3 couches · code Python · 95 tests · prototype démo | TERMINÉ 2026-06-20 | fce/ · tests/ · policies/ · data/ · scripts/demo.py · BR-FCE-001.md · REV-S1.md |
| S2 | Validation scénarios opérationnels · corpus synthétique étendu · benchmarks SWaP | À VENIR | data/extended_scenarios.py · benchmarks/ · BR-FCE-002.md |
| S3 | Hardening périphérie · quantisation modèle ML · profiling latence edge | À VENIR | benchmarks/ · docs/swapguide.md · REV-S2.md |
| S4 | Documentation formelle · guide opérateur · GLOSSAIRE.md complet | À VENIR | docs/ · GLOSSAIRE.md v2.0 |

---

## 2. Modules FCE

| Module | Fichier | Tests | Couverture | Statut |
|--------|---------|-------|------------|--------|
| Modèles de données | fce/models/data_object.py | 13 | 100% | VALIDÉ S1 |
| Couche 1 — Policy Engine | fce/policy/engine.py | 22 | 96% | VALIDÉ S1 |
| Couche 2 — Provenance Graph | fce/lineage/graph.py | 18 | 97% | VALIDÉ S1 |
| Couche 3 — ML Anomaly Detector | fce/ml/anomaly_detector.py | 14 | 91% | VALIDÉ S1 |
| Journal d'audit | fce/audit/logger.py | 9 | 87% | VALIDÉ S1 |
| Pipeline orchestrateur | fce/pipeline.py | 19 | 88% | VALIDÉ S1 |
| **TOTAL** | — | **95** | **93%** | **GO S1** |

---

## 3. Scénarios opérationnels validés

| ID | Scénario | Capteurs | Résultat attendu | Résultat obtenu | Statut |
|----|----------|----------|-----------------|-----------------|--------|
| SC-01 | Fusion SIGINT + EO/IR Protégé B (Arctique) | SIGINT + EO/IR | ALLOW — classif. Prot. B | ALLOW — 13 ms | VALIDÉ |
| SC-02 | Fusion UAS + RADAR (surveillance aérienne) | UAS + RADAR | ALLOW — dominance Prot. A | ALLOW — 13 ms | VALIDÉ |
| SC-03 | Maritime RADAR + ACOUSTIC + EO/IR | 3 capteurs | ALLOW / RESTRICT ACOUSTIC | CONFORME | VALIDÉ |
| SC-04 | Tactique démonté UAS + SIGINT (coalition) | UAS + SIGINT | ALLOW | ALLOW | VALIDÉ |
| SC-05 | SIGINT Prot. B sur UNCLASSIFIED_NET | SIGINT | DENY RULE-003 | DENY — 13 ms | VALIDÉ |
| SC-06 | UAS Prot. B sans REL TO CAN | UAS | RESTRICT RULE-002 | RESTRICT | VALIDÉ |
| SC-07 | Anomalie ML — lignage profond × 15 noctune | EO/IR | RESTRICT C3 | RESTRICT | VALIDÉ |

---

## 4. Questions ouvertes (QO) actives

| ID | Statut | Description | Sprint cible | Bloquant ? |
|----|--------|-------------|--------------|------------|
| QO-FCE-01 | OUVERT | Valider probabilité de violation < 0,1% sur corpus ≥ 10 000 paquets | S2 | non |
| QO-FCE-02 | OUVERT | Benchmarker latence sur CPU embarqué ARM (Jetson, laptop renforcé) | S3 | non |
| QO-FCE-03 | OUVERT | Définir politique coalition OTAN (paires domaines autorisées) | S2 | non |
| QO-FCE-04 | OUVERT | Valider modèle ML sur données non-synthétiques (corpus partenarial) | S3 | non |
| QO-FCE-05 | OUVERT | Couvrir les lignes non testées audit/logger.py (marge 13%) | S2 | non |

---

## 5. Décisions de session

### DEC-S1-01 — Architecture 3 couches retenue

Date : 2026-06-20
Source : analyse du besoin (contexte__Fusion.pdf) + exploration de 3 solutions candidates
Décision : architecture tri-couche complémentaire retenue (PESFE + GLCT + LMAG) plutôt que
solutions monolithiques. Les 3 couches s'appliquent en séquence : C1 filtre en entrée par
règles statiques, C2 garantit la classification dominante via DAG, C3 surveille les
anomalies comportementales. Résultat combiné : probabilité de violation estimée < 0,001%.

### DEC-S1-02 — Fail-secure comme principe fondamental

Date : 2026-06-20
Source : exigences FCE (probabilité violation < 0,1%) + analyse des risques
Décision : en cas de règles multiples déclenchées sur un même paquet, la décision finale
est toujours la plus restrictive (DENY > QUARANTINE > RESTRICT > DOWNGRADE > ALLOW).
Cela s'applique à C1 (interne) et à la fusion C1+C3. C2 ne peut qu'escalader une
décision ALLOW, jamais dégrader un DENY. Confirmé par test test_fail_secure_multiple_rules.

### DEC-S1-03 — Hot-reload YAML sans redémarrage pipeline

Date : 2026-06-20
Source : exigence opérationnelle — transition rapide entre contextes (coalition / national)
Décision : PolicyEngine utilise un verrou RLock et swap atomique de la liste de règles.
Le hot-reload est thread-safe : les paquets en cours de traitement utilisent l'ancienne
liste jusqu'à completion, les paquets suivants utilisent la nouvelle liste.
Validé par test test_hot_reload_adds_rule (S1 + tests d'intégration).

### DEC-S1-04 — Dégradation gracieuse du détecteur ML (Couche 3)

Date : 2026-06-20
Source : exigences SWaP — déploiement sur laptop renforcé sans modèle pré-entraîné
Décision : si le détecteur ML n'est pas entraîné (modèle absent), predict() retourne
AnomalyResult(is_anomaly=False, confidence=0.0) avec warning. Le pipeline continue
avec C1 et C2 seuls. Aucune exception levée. Validé par test
test_predict_before_fit_returns_safe_default.

### DEC-S1-05 — Encodeur JSON custom pour types numpy

Date : 2026-06-20
Source : bug découvert lors des tests d'intégration (TypeError: bool_ non sérialisable)
Décision : ajout de _FCEJSONEncoder dans audit/logger.py gérant np.bool_, np.integer,
np.floating, np.ndarray. Utilisé dans tous les json.dumps() du journal d'audit.
Bug corrigé — 95/95 tests passent après correction.

### DEC-S1-06 — Principe de dominance pour classification de sortie (Couche 2)

Date : 2026-06-20
Source : exigence FCE — impossibilité de sous-classifier une sortie de fusion
Décision : compute_output_classification() remonte tous les ancêtres via nx.ancestors()
et retourne le maximum. Garantie mathématique : classif_sortie ≥ max(classif_sources).
Validé par tests test_dominance_principle_max, test_dominance_three_level_chain,
test_no_downgrade_possible.

---

## 6. Métriques Sprint 1

| Métrique | Valeur | Seuil | Statut |
|----------|--------|-------|--------|
| Tests passés | 95 / 95 | 100% | SATISFAIT |
| Couverture code | 93% | ≥ 90% | SATISFAIT |
| Latence moyenne pipeline | 13 ms | ≤ 50 ms | SATISFAIT |
| Latence maximale pipeline | 15 ms | ≤ 50 ms | SATISFAIT |
| Débit | 78 paquets/s | — | MESURÉ |
| Types de capteurs couverts | 5 | ≥ 2 | SATISFAIT |
| Niveaux de classification | 6 | ≥ Prot. B | SATISFAIT |
| Règles YAML chargées | 5 | ≥ 1 | SATISFAIT |
| Scénarios opérationnels validés | 7 | ≥ 3 | SATISFAIT |
| Taille modèle ML (sérialisé) | ~500 KB | ≤ 5 MB | SATISFAIT |

---

## 7. Notes session prochaine (Sprint 2)

Avant de démarrer Sprint 2, l'humain doit :
1. Merger la PR sprint/fce-analyse-v1 → main sur GitHub.
2. Confirmer les paires de domaines coalition à ajouter dans base_policy.yaml (QO-FCE-03).
3. Décider si un corpus partenarial est disponible pour valider le modèle ML (QO-FCE-04).
4. Confirmer la cible matérielle pour les benchmarks SWaP (QO-FCE-02 — Jetson Orin NX ou laptop renforcé).

Sprint 2 : extension des scénarios opérationnels (Arctic, maritime, OTAN), validation
probabilité violation < 0,1% sur corpus ≥ 10 000 paquets, couverture tests → 95%.

---

*STATUS.md v1.0 — Sprint 1 TERMINÉ — FCE FusionCapteurs — 2026-06-20*
*Généré par claude-sonnet-4-6*
