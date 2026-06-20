# REV-FC-S1 — Revue Sprint 1 FusionCapteurs
# Évaluation NEUROSYNAPSE-ISR ↔ Défi IDEeS "Fusion de capteurs fiable"
# Date : 2026-06-20 | Analyste : session Claude Sonnet 4.6
# Repo source : mckthierry/neurosynapse-proposal (Sprint 7, 82/100)
# Repo cible : mckthierry/FusionCapteurs

---

## VERDICT GLOBAL

Score estimé alignement NEUROSYNAPSE ↔ Défi B : 48/100
Verdict : NO-GO pour soumission directe au Défi "Fusion de capteurs fiable"

Raison principale : la proposition a été rédigée pour un défi différent
("IA multimodale pour décisions situationnelles améliorées", Défi A),
et présente 2 gaps critiques bloquants vis-à-vis du Défi B.

Nota : le score 82/100 de NEUROSYNAPSE reste valide pour le Défi A.
Ce REV-FC-S1 évalue exclusivement l'alignement avec le Défi B.

---

## SECTION 1 — MANQUEMENTS CRITIQUES [MC]

### MC-01 — Mauvais défi cible (BLOQUANT)

Sévérité : CRITIQUE — éliminatoire
Description :
  La proposition NEUROSYNAPSE-ISR a été rédigée et calibrée pour le Défi IDEeS A :
  "IA multimodale pour des décisions situationnelles améliorées"
  Le formulaire portail PID (FORMULAIRE_REFERENCE.md, champ 1-A, valeur fixe
  non modifiable) confirme ce ciblage.

  Le Défi B ("Fusion de capteurs par IA fiable pour des missions réelles")
  est un appel distinct, avec des critères, un intitulé et un calendrier
  différents (CFP ouverture 4 juin 2026, deadline 14 juillet 2026 d'après
  CanadaBuys). Les sections CO-2, CCP-1 à CCP-6 référencent les dimensions
  du Défi A et non du Défi B.

Recommandation :
  Résoudre QO-FC-01 (quel défi cible ?) avant tout travail de rédaction.
  Une soumission pour le Défi B nécessite une refonte du champ 1-A et une
  révision substantielle de CO-2 et CCP-6.

### MC-02 — Limite L1 contradictoire avec l'intitulé du Défi B (BLOQUANT)

Sévérité : CRITIQUE — potentiellement éliminatoire
Description :
  Le Défi B s'intitule "pour des missions réelles". NEUROSYNAPSE déclare
  explicitement la Limite L1 : validation sur données synthétiques
  haute-fidélité uniquement. La validation NMT-5 est sur synthétique.
  Cette limite est déclarée dans le PID (CCP-4, CCP-6, Résumé) et
  formalisée comme décision DEC-P2-03 (crédibilité > couverture).

  Un évaluateur du Défi B lira que la solution validée sur données
  synthétiques prétend répondre à un défi intitulé "missions réelles".
  C'est une contradiction directe, même si la Limite L1 est honnêtement
  déclarée.

Recommandation :
  Soit élaborer un plan de validation sur données réelles (même partiel) :
    - Partenariat dataset opérationnel (ex. DRDC, partenaire industriel NDA)
    - Validation sur simulateur haute-fidélité certifié MDN
  Soit argumenter explicitement pourquoi "synthétique haute-fidélité" est
  suffisant au niveau NMT-5 pour le Défi B — avec ancrage dans la doctrine
  de validation MDN.

### MC-03 — Classification multi-domaines absente (HAUTE)

Sévérité : HAUTE
Description :
  Le Défi B cite le risque de "compromission de sources, méthodes ou
  opérations" lors de la combinaison de données multi-domaines de
  classification (PROTÉGÉ B / NON CLASSIFIÉ). C'est une préoccupation
  sécuritaire centrale du défi.

  NEUROSYNAPSE déclare ce point hors périmètre Phase 1 (DEC-S7-01,
  CCP-6 Sprint 7). Aucune section du PID ne traite le flux de travail
  de fusion sécurisée multi-niveaux de classification.

Recommandation :
  Ajouter en CCP-4 ou CCP-6 un plan minimal de gestion des niveaux de
  classification à la frontière de fusion, même comme travaux futurs
  formels avec jalons identifiés, pour démontrer la conscience du risque.

### MC-04 — Deadline potentiellement manquée pour le Défi A (BLOQUANT)

Sévérité : CRITIQUE (si soumission non effectuée)
Description :
  STATUS.md indique une deadline de 2026-06-02 14h00 HAE pour le Défi A.
  La date courante est 2026-06-20, soit 18 jours après la deadline.
  Si la soumission n'a pas été effectuée avant le 2 juin 2026, le Défi A
  est fermé pour cette session de financement.

  QO-FC-02 : la soumission a-t-elle été effectuée le 2 juin 2026 ?

Recommandation :
  L'humain doit confirmer le statut de soumission avant tout sprint suivant.
  Si non soumis : pivoter vers le Défi B (deadline 14 juillet 2026).
  Si soumis : ce repo FusionCapteurs peut servir d'analyse comparative
  ou de base pour une soumission au Défi B.

---

## SECTION 2 — ALIGNEMENTS FORTS (à préserver)

### AF-01 — Architecture multi-capteurs ISR (score : 16/20)

La couverture de 4 modalités (radar RF, EO/IR, SIGINT, texte tactique)
via les encodeurs E1 est directement pertinente pour le Défi B.
Le mécanisme de substitution E1 permet l'extension à UAS et acoustique
sans refonte architecturale (CCP-3, DEC-S7-02).
Point fort à mettre en avant dans CO-2 si adaptation pour Défi B.

### AF-02 — Quantification de l'incertitude / IA fiable (score : 15/20)

MC Dropout N=30, ECE < 0.05, indicateurs HAUTE/MOYENNE/FAIBLE sont
exactement ce que "IA fiable" implique dans le Défi B. La terminologie
de fiabilité (avec preuve formelle : Gal & Ghahramani 2016) est un atout
majeur. Peu de propositions auront une justification aussi ancrée.

### AF-03 — Traçabilité cryptographique (score : 12/15)

SHA-256 par décision (E5, NIST FIPS 180-4) est directement pertinent
pour le Défi B qui mentionne la compromission de sources. L'audit
a posteriori répond partiellement à l'exigence de responsabilisation.
Limite : ne couvre pas la fusion multi-niveaux de classification.

### AF-04 — Contraintes SWaP et déploiement embarqué (score : 13/15)

Les contraintes < 220 Ko / ≤ 50 ms sur Jetson Orin NX sont bien
documentées et crédibles (8 jalons formels J-N1 à J-N8). Le déploiement
sans connectivité réseau est explicitement argumenté. C'est un différenciateur
fort pour le Défi B qui cible les "missions réelles" en terrain dégradé.

---

## SECTION 3 — ANGLES MORTS NON TRAITÉS

### AM-01 — Robustesse en conditions dégradées

Le Défi B implique "missions réelles" avec capteurs défaillants, signal
bruité, latence variable. NEUROSYNAPSE documente le comportement en mode
dégradé (modalités absentes = vecteur zéro) mais ne documente pas :
- Comportement avec N capteurs partiellement dégradés simultanément
- Mécanisme de détection de dérive de capteur en temps réel
- Comportement sous brouillage électronique (pertinent pour SIGINT/radar)

### AM-02 — Interopérabilité avec systèmes C4ISR existants

Le Défi B cible les Forces armées canadiennes. La proposition NEUROSYNAPSE
ne mentionne pas l'intégration avec les systèmes C4ISR/BMS canadiens existants
(ex. protocoles STANAG, formats de message tactique), au-delà de la mention
générique "chaîne de commandement" en CCP-3.

### AM-03 — Validation adversariale réelle

CCP-4 mentionne FGSM/PGD mais dans le cadre d'un entraînement adversarial
sur données synthétiques. Les attaques adversariales sur capteurs ISR réels
(leurres radar, spoofing GPS, pollution SIGINT) ne sont pas adressées.

### AM-04 — Plan de transition NMT-5 → NMT-6

Si le Défi B cible TRL 6-9 (build phase, $5M+), NEUROSYNAPSE s'arrête à
NMT-5. Aucun plan de passage NMT-5 → NMT-6 (démonstration en environnement
représentatif certifié) n'est esquissé dans la proposition actuelle.

---

## SECTION 4 — SCORE DÉTAILLÉ (alignement NEUROSYNAPSE ↔ Défi B)

| Dimension évaluée | Score | Max | Commentaire |
|-------------------|-------|-----|-------------|
| Couverture capteurs ISR | 16 | 20 | Radar/EO-IR/SIGINT couverts, UAS/acoustique non |
| Fiabilité IA / incertitude | 15 | 20 | MC Dropout + ECE documentés, bases solides |
| Données réelles (Limite L1) | 3 | 15 | Synthétique ≠ missions réelles — gap critique |
| Classification multi-domaines | 0 | 15 | Absent (hors périmètre Phase 1) |
| Déploiement embarqué SWaP | 13 | 15 | Bien documenté, crédible |
| Traçabilité / audit | 1 | 15 | SHA-256 présent mais multi-niveaux absent |

TOTAL : 48 / 100 — NO-GO pour Défi B tel quel

---

## SECTION 5 — RECOMMANDATIONS PRIORITAIRES

### P0 (Bloquant — décision humaine avant tout sprint)

P0.1 : Résoudre QO-FC-01 — confirmer le défi cible (A ou B)
P0.2 : Résoudre QO-FC-02 — confirmer si soumission Défi A effectuée le 2 juin
P0.3 : Si pivot vers Défi B : confirmer le budget plafond et les NMT cibles

### P1 (Si Défi B retenu — Sprint 2 prioritaire)

P1.1 : Adresser MC-02 (Limite L1 / données réelles) — décision stratégique
P1.2 : Adresser MC-03 (classification multi-domaines) — plan minimal requis
P1.3 : Réviser CO-2 pour harmonisation avec "Fusion de capteurs fiable" (pas "IA multimodale")
P1.4 : Étendre CCP-3 avec plan UAS/acoustique (mécanisme E1 substitution)

### P2 (Sprint 3 si Défi B)

P2.1 : Adresser AM-01 (robustesse conditions dégradées) dans CCP-4
P2.2 : Mentionner interopérabilité C4ISR (STANAG) dans CO-2 ou CCP-6
P2.3 : Ajouter esquisse NMT-5 → NMT-6 si budget Défi B justifie phase longue

---

## SECTION 6 — VERDICT PAR SECTION (si soumis au Défi B sans modification)

| Section | Score estimé | Gap principal |
|---------|-------------|---------------|
| CO-1 description R&D | 13/20 | Architecture solide, Limite L1 visible |
| CO-2 harmonisation | 5/20 | Harmonisé avec Défi A, pas Défi B |
| CCP-1 mérite scientifique | 12/15 | Solide, références publiées valides |
| CCP-2 innovation | 14/20 | Bonne différenciation, caveat littérature grise ok |
| CCP-3 incidence | 10/15 | Bon plan, UAS/acoustique manquants |
| CCP-4 faisabilité | 10/15 | Plan NMT-5 valide mais sur synthétique |
| CCP-6 alignement | 5/20 | Mauvais défi référencé, classification absente |
| CCP-7 coûts | 12/15 | Cohérent, recalibrage si plafond Défi B différent |

TOTAL ESTIMÉ : 81/120 → soit 67.5/100 — NO-GO (seuil 75)

---

*REV-FC-S1 — FusionCapteurs Sprint 1 — 2026-06-20*
*Questions ouvertes QO-FC-01 et QO-FC-02 bloquantes — résolution humaine requise*
*Score NEUROSYNAPSE pour Défi A (82/100) reste valide et non remis en question*
