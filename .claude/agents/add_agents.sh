#!/usr/bin/env bash
# add_agents.sh — Installe les sub-agents Claude Code dans neurosynapse-proposal
# Exécuter depuis : ~/Projects/52_MULTIMODALE/AI/CCW/
# Usage : ./add_agents.sh [chemin_vers_agents/]

set -euo pipefail

REPO="neurosynapse-proposal"
AGENTS_SRC="${1:-agents}"   # dossier source des YAML (défaut : ./agents/)
AGENTS_DST="${REPO}/.claude/agents"

echo "→ Création de ${AGENTS_DST}..."
mkdir -p "${AGENTS_DST}"

FICHIERS=(
  analyste.yaml
  redacteur.yaml
  verificateur.yaml
  persona-A.yaml
  persona-B.yaml
  persona-C.yaml
  persona-D.yaml
)

echo "→ Copie des agents..."
for f in "${FICHIERS[@]}"; do
  src="${AGENTS_SRC}/${f}"
  dst="${AGENTS_DST}/${f}"
  if [[ -f "${src}" ]]; then
    cp "${src}" "${dst}"
    printf "  ✓ %s\n" "${f}"
  else
    printf "  ✗ MANQUANT : %s\n" "${src}" >&2
  fi
done

echo ""
echo "→ Vérification arborescence .claude/ :"
tree "${REPO}/.claude" 2>/dev/null || find "${REPO}/.claude" -type f | sort

echo ""
echo "✓ Agents installés. Prochain commit :"
echo "  cd ${REPO} && git add .claude/ && git commit -m '[S0] add Claude Code sub-agents (7 agents)'"
