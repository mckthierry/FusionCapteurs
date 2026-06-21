# GLOSSAIRE.md — FCE FusionCapteurs

**Version** : 1.0 — Sprint 1 — 2026-06-20
**Autorité** : README.md + fce/models/data_object.py + policies/base_policy.yaml
**Règle** : ce fichier fait autorité sur tout terme non défini ailleurs. Toute nouvelle session doit lire ce fichier après STATUS.md.

---

## 1. Termes architecturaux

| Terme | Définition |
|---|---|
| FCE | Fusion Compliance Engine — moteur de conformité de fusion. Architecture tri-couche appliquant automatiquement les règles de classification, les contraintes juridiques et les politiques lors de l'agrégation de données multi-capteurs. |
| Pipeline FCE | Séquence d'exécution des 3 couches : C1 (PolicyEngine) → C2 (ProvenanceGraph) → C3 (AnomalyDetector) → AuditLogger → FCEResult. |
| Couche 1 — PolicyEngine | Moteur de politiques statiques. Charge des règles YAML lisibles par machine, les évalue sur chaque paquet entrant, applique le principe fail-secure. Supporte le hot-reload sans redémarrage. |
| Couche 2 — ProvenanceGraph | Graphe de provenance orienté acyclique (DAG). Enregistre le lignage de chaque donnée, calcule la classification de sortie dominante, détecte les violations inter-domaines. |
| Couche 3 — AnomalyDetector | Détecteur d'anomalies comportementales basé sur Isolation Forest. Surveillance en temps réel des patterns de flux. Optimisé SWaP : modèle ~500 KB, inférence < 1 ms sur CPU. |
| AuditLogger | Journal JSONL append-only. Enregistre chaque décision de conformité. Exportable en CSV pour accréditation, analyse forensique et contrôle externe. |
| FCEResult | Objet résultat d'un passage dans le pipeline. Contient : décision finale, décision C1, résultat ML, classification calculée, latence, violations inter-domaines. |
| ProvenanceRecord | Enregistrement de provenance immuable attaché à chaque paquet dès l'ingestion. Contient : UUID, sensor_id, sensor_type, classification, origin_domain, horodatage UTC, dissemination_controls, handling_caveats, lineage. |
| SensorDataPacket | Unité atomique du pipeline FCE. Encapsule une donnée brute de capteur avec sa ProvenanceRecord. Tout paquet traversant le FCE doit être créé via ce dataclass. |
| DAG | Directed Acyclic Graph — graphe orienté acyclique. Structure de données du ProvenanceGraph. Chaque nœud = un paquet, chaque arête = une dépendance de traitement. Acyclicité garantie par vérification à chaque ajout d'arête. |
| PolicyRule | Règle de conformité compilée depuis une définition YAML. Structure : condition déclarative + action d'enforcement + explication opérateur lisible. |
| LineageNode | Nœud dans le graphe de provenance. Contient : record_id, classification, sensor_type, origin_domain, node_type (ingestion / transform / fusion / output), horodatage. |

---

## 2. Termes opérationnels

| Terme | Définition |
|---|---|
| SWaP | Size, Weight and Power — contraintes physiques pour systèmes embarqués. Cibles FCE : modèle ML ≤ 5 MB, latence ≤ 50 ms sur CPU embarqué, empreinte mémoire minimale. |
| ISR | Intelligence, Surveillance, Reconnaissance — ensemble des capacités de collecte, traitement et exploitation du renseignement. Contexte de déploiement FCE. |
| Dissemination control | Contrôle de diffusion associé à un paquet (ex : REL TO CAN, NOFORN, EYES ONLY). Vérifiés par les règles YAML de C1 (type missing_caveat). |
| Handling caveat | Mention de manipulation spéciale associée à un paquet (ex : SIGINT, COMINT). Métadonnée de provenance, non utilisée pour l'enforcement C1 dans la version courante. |
| Lineage | Liste des IDs des paquets parents d'un paquet. Constitue le lignage de fusion. Enregistré dans ProvenanceRecord.lineage et reproduit comme arêtes dans le DAG C2. |
| Hot-reload | Rechargement à chaud des règles de politique (C1) ou des paires de domaines autorisées (C2) sans interruption du pipeline ni redémarrage du processus. |
| Cross-domain violation | Arête dans le DAG C2 entre deux nœuds de domaines réseau différents dont la paire n'est pas dans la liste des paires autorisées. Déclenche une escalade ALLOW → RESTRICT. |
| Opérateur explanation | Texte lisible par un humain expliquant la décision de conformité. Généré par PolicyRule (C1) ou AnomalyDetector (C3). Exporté dans le journal d'audit. |
| Contournement contrôlé | Mécanisme de dérogation aux politiques FCE avec traçabilité obligatoire. Non implémenté en Phase 1 — prévu en Sprint 4 avec garanties d'imputabilité. |
| Fail-secure | Principe d'engineering : en cas d'incertitude ou de conflit de règles, le système prend la décision la plus restrictive. Opposé de fail-open (décision la plus permissive). |

---

## 3. Termes de classification

| Terme | Définition |
|---|---|
| ClassificationLevel | Énumération ordonnée (IntEnum) des niveaux de classification. UNCLASSIFIED=0, PROTECTED_A=1, PROTECTED_B=2, PROTECTED_B_ENHANCED=3, SECRET=4, TOP_SECRET=5. |
| Principe de dominance | Règle de propagation de classification : la classification de sortie d'une fusion = max(classification de tous les ancêtres dans le DAG). Garantit l'impossibilité de sous-classification. |
| Protégé B | Niveau de classification canadien (GC) — seuil minimal requis par le défi FCE. Équivalent approximatif à CONFIDENTIAL dans d'autres nomenclatures. |
| NetworkDomain | Domaine réseau reconnu par le FCE : UNCLASSIFIED_NET, PROTECTED_NET, SECRET_NET, COALITION_NET. Validé à l'ingestion. |
| Paire de domaines autorisée | Tuple (source_domain, target_domain) pour lequel un flux inter-domaines est permis. Configurable via ProvenanceGraph.set_allowed_domain_pairs(). Hot-reload supporté. |

---

## 4. Termes ML et détection d'anomalies

| Terme | Définition |
|---|---|
| Isolation Forest | Algorithme de détection d'anomalies basé sur l'isolation aléatoire de points dans un espace de features. Non-supervisé. Utilisé en C3 du FCE. Implémentation : sklearn.ensemble.IsolationForest. |
| Contamination | Paramètre Isolation Forest = fraction attendue d'anomalies dans les données d'entraînement. Valeur FCE : 0,001 (< 0,1% cible). |
| AnomalyResult | Objet résultat de C3. Contient : is_anomaly (bool), anomaly_score (float), confidence [0,1], explanation (str), severity (NONE / LOW / MEDIUM / HIGH). |
| Vecteur de features | Représentation numérique d'un SensorDataPacket pour le détecteur ML. 7 dimensions : classification normalisée, type capteur encodé, domaine encodé, heure normalisée, nb contrôles diffusion, profondeur lignage, présence mises en garde. |
| Dégradation gracieuse | Comportement de C3 si le modèle ML n'est pas entraîné : retourne AnomalyResult(is_anomaly=False, confidence=0.0) avec warning. Le pipeline C1+C2 continue normalement. |
| LabelEncoder | Encodeur sklearn transformant les labels catégoriels (sensor_type, origin_domain) en entiers pour le vecteur de features. Labels inconnus à l'inférence → encodé à 0 (conservateur). |

---

## 5. Actions d'enforcement

| Action | Priorité (fail-secure) | Définition |
|---|---|---|
| DENY | 0 (plus restrictif) | Rejet total du paquet. Aucune fusion autorisée. Requiert révision humaine. |
| QUARANTINE | 1 | Isolation du paquet. Validation humaine requise avant tout traitement. |
| RESTRICT | 2 | Acheminement restreint. Flags d'avertissement ajoutés. Opérateur notifié. |
| DOWNGRADE | 3 | Déclassement automatique avant fusion. Classification réduite au niveau cible. |
| ALLOW | 4 (moins restrictif) | Données conformes. Passage autorisé dans le pipeline de fusion. |

Note : la priorité encode l'ordre fail-secure. En cas de règles multiples déclenchées,
l'action avec la priorité la plus basse (DENY = 0) l'emporte toujours.

---

## 6. Acronymes

| Acronyme | Signification |
|---|---|
| FCE | Fusion Compliance Engine — Moteur de Conformité de Fusion |
| DAG | Directed Acyclic Graph — Graphe Orienté Acyclique |
| SWaP | Size, Weight and Power |
| ISR | Intelligence, Surveillance, Reconnaissance |
| UAS | Unmanned Aerial System — Système aérien sans pilote |
| SIGINT | Signals Intelligence — Renseignement d'origine électromagnétique |
| EO/IR | Electro-Optical / Infrared — Électro-optique / Infrarouge |
| ROE | Rules of Engagement — Règles d'engagement |
| JSONL | JSON Lines — format de journal structuré ligne par ligne |
| UUID | Universally Unique Identifier — identifiant unique universel (v4) |
| REL TO CAN | Releasable to Canada — contrôle de diffusion canadien |
| NOFORN | Not releasable to Foreign Nationals — contrôle de diffusion US |
| ML | Machine Learning — apprentissage automatique |
| CSV | Comma-Separated Values — format d'export tabulaire |

---

## 7. Termes réservés et conventions

| Convention | Règle |
|---|---|
| « moteur de conformité » | Désigne toujours le FCE complet (3 couches + audit). Ne pas utiliser pour désigner une seule couche. |
| « couche N » | Désigne C1 (PolicyEngine), C2 (ProvenanceGraph) ou C3 (AnomalyDetector). Numérotation fixe. |
| « fail-secure » | Désigne le principe de restriction maximale en cas de doute. Ne pas confondre avec « fail-safe » (sécurité physique). |
| « dominance » | Désigne exclusivement le principe de propagation de classification maximale dans le DAG (C2). Ne pas utiliser pour désigner la priorité des actions d'enforcement (C1). |
| « hot-reload » | Désigne uniquement le rechargement à chaud des configurations (politiques YAML ou paires de domaines). Ne pas utiliser pour désigner le redémarrage du pipeline. |

---

## 8. Références sources

- `fce/models/data_object.py` — définitions ClassificationLevel, SensorType, NetworkDomain, ProvenanceRecord, SensorDataPacket
- `fce/policy/engine.py` — EnforcementAction, PolicyDecision, PolicyRule, PolicyEngine
- `fce/lineage/graph.py` — LineageNode, CrossDomainViolation, ProvenanceGraph
- `fce/ml/anomaly_detector.py` — AnomalyResult, ComplianceAnomalyDetector
- `fce/audit/logger.py` — AuditLogger
- `fce/pipeline.py` — FCEResult, FusionComplianceEngine
- `policies/base_policy.yaml` — règles de conformité opérationnelles (RULE-001 à RULE-005)
- `contexte__Fusion.pdf` — besoin original, historique, résultats essentiels et souhaités

---

*GLOSSAIRE.md v1.0 — Sprint 1 — FCE FusionCapteurs — 2026-06-20*
*Vocabulaire unifié — fait autorité sur tout terme non défini ailleurs*
