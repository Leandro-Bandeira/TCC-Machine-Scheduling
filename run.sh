#!/bin/bash
set -euo pipefail

# Garante execução sempre a partir da raiz do projeto
cd "$(dirname "$0")"

CONFIG="${1:-run_config.json}"

if [ ! -f "$CONFIG" ]; then
  echo "Erro: arquivo de configuração não encontrado: $CONFIG" >&2
  exit 1
fi

TOTAL=$(python3 -c "
import json
d = json.load(open('$CONFIG'))
print(sum(len(cfg.get('only_status', [])) for cfg in d.values()))
")

CURRENT=0

while IFS='|' read -r DT STATUSES MACHINES; do

  CURRENT=$((CURRENT + 1))
  PCT=$((CURRENT * 100 / TOTAL))

  ONLY_STATUS_ARG=""
  if [ -n "$STATUSES" ]; then
    ONLY_STATUS_ARG="--only-status $STATUSES"
  fi

  ONLY_MACHINES_ARG=""
  if [ -n "$MACHINES" ]; then
    ONLY_MACHINES_ARG="--only-machines $MACHINES"
  fi

  echo ""
  echo "=========================================="
  echo "  [$CURRENT/$TOTAL - $PCT%]"
  echo "  dt       : $DT"
  echo "  status   : ${STATUSES:-todos}"
  echo "  machines : ${MACHINES:-todas}"
  echo "=========================================="

  echo ""
  echo ">>> [1/3] data_input_process.py"
  python3 src/main/data_input_process.py --dt "$DT" $ONLY_STATUS_ARG

  echo ""
  echo ">>> [2/3] optimize.py"
  python3 src/main/optimize.py --dt "$DT" $ONLY_STATUS_ARG $ONLY_MACHINES_ARG

  echo ""
  echo ">>> [3/3] data_output_process.py"
  python3 src/main/data_output_process.py --dt "$DT" $ONLY_STATUS_ARG

  echo ""
  echo "  Concluído: $DT [$CURRENT/$TOTAL]"

done < <(python3 -c "
import json
d = json.load(open('$CONFIG'))
for dt, cfg in d.items():
    statuses = cfg.get('only_status', [])
    machines = cfg.get('machines', [])
    print(dt + '|' + ' '.join(statuses) + '|' + ' '.join(machines))
")

echo ""
echo "=========================================="
echo "  Pipeline finalizado. [$TOTAL/$TOTAL - 100%]"
echo "=========================================="
