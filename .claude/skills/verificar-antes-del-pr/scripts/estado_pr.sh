#!/usr/bin/env bash
# Muestra el estado de CI y del Quality Gate de SonarCloud para un PR de IdentityHub.
# Uso: bash estado_pr.sh <número-del-PR>
set -euo pipefail
PR="${1:?Indica el número del PR}"
REPO="EduarOC/IdentityHub"
PROYECTO="EduarOC_proyecto-de-grado"

sha="$(gh api "repos/$REPO/pulls/$PR" --jq '.head.sha')"
echo "PR #$PR · commit ${sha:0:7} · $(gh api "repos/$REPO/pulls/$PR" --jq '.mergeable_state')"
gh api "repos/$REPO/commits/$sha/check-runs" --jq '.check_runs[] | "  \(.name): \(.status) / \(.conclusion // "-")"'

curl -s "https://sonarcloud.io/api/qualitygates/project_status?projectKey=$PROYECTO&pullRequest=$PR" \
  | python -c "import json,sys
d=json.load(sys.stdin).get('projectStatus',{})
print('  Quality Gate:', d.get('status','sin análisis todavía'))
for c in d.get('conditions',[]):
    if c['status']=='ERROR': print('   ✗', c['metricKey'], c.get('actualValue'), '(umbral', c.get('errorThreshold'),')')"
curl -s "https://sonarcloud.io/api/issues/search?componentKeys=$PROYECTO&pullRequest=$PR&resolved=false&ps=20" \
  | python -c "import json,sys
d=json.load(sys.stdin)
for i in d.get('issues',[]): print('   -', i['type'], i['severity'], i['rule'], i['component'].split(':')[-1]+':'+str(i.get('line','')), '-', i['message'][:90])"
