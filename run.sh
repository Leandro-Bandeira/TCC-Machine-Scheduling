#!/bin/bash
set -euo pipefail

# Garante execução sempre a partir da raiz do projeto
cd "$(dirname "$0")"

CONFIG="run_config.json"
SKIP_EXISTING=false
USE_GUROBI=false
USE_WARM_START=false

for arg in "$@"; do
  case "$arg" in
    --skip-existing) SKIP_EXISTING=true ;;
    --use-gurobi) USE_GUROBI=true ;;
    --use-warm-start) USE_WARM_START=true ;;
    *) CONFIG="$arg" ;;
  esac
done

if [ ! -f "$CONFIG" ]; then
  echo "Erro: arquivo de configuração não encontrado: $CONFIG" >&2
  exit 1
fi

if [ "$USE_WARM_START" = true ]; then
  echo ">>> Compilando heurística C++ (src/heuristics)..."
  make -C src/heuristics
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

  DATE_SLUG=$(python3 -c "from datetime import datetime; print(datetime.strptime('$DT','%Y-%m-%d').strftime('%d%m%Y'))")

  if [ "$SKIP_EXISTING" = true ]; then
    ALL_DONE=true
    for STATUS in $STATUSES; do
      if [ ! -f "data/trusted/$DATE_SLUG/$STATUS/output.json" ]; then
        ALL_DONE=false
        break
      fi
    done
    if [ "$ALL_DONE" = true ]; then
      echo "  [SKIP] $DT — output.json já existe para todos os status"
      continue
    fi
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

  GUROBI_ARG=""
  if [ "$USE_GUROBI" = true ]; then
    GUROBI_ARG="--use-gurobi"
  fi

  WARM_START_ARG=""
  if [ "$USE_WARM_START" = true ]; then
    WARM_START_ARG="--use-warm-start"
    echo ""
    echo ">>> [Warm Start] Executando heurística C++..."
    while IFS='|' read -r INPUT_FILE MACHINE_ID MACHINE_NAME; do
      echo "  [Heurística] $INPUT_FILE — $MACHINE_NAME (id=$MACHINE_ID)"
      ./src/heuristics/heuristic "$INPUT_FILE" "$MACHINE_ID"
    done < <(python3 -c "
import json
from pathlib import Path

date_dir = Path('data/trusted/$DATE_SLUG')
statuses = '$STATUSES'.split()
machines_filter = set('$MACHINES'.split())

if not statuses and date_dir.is_dir():
    statuses = [p.name for p in sorted(date_dir.iterdir()) if p.is_dir() and (p / 'input.json').exists()]

for st in statuses:
    inp = date_dir / st / 'input.json'
    if not inp.exists():
        continue
    data = json.loads(inp.read_text(encoding='utf-8'))
    for m in data.get('machines', []):
        m_id = m['machine_id']
        m_name = m['machine_name']
        if machines_filter and m_name not in machines_filter:
            continue
        print(f'{inp}|{m_id}|{m_name}')
")
  fi

  echo ""
  echo ">>> [2/3] optimize.py"
  if ! python3 src/main/optimize.py --dt "$DT" $ONLY_STATUS_ARG $ONLY_MACHINES_ARG $GUROBI_ARG $WARM_START_ARG; then
    echo "  [AVISO] Falha ao executar optimize.py para $DT — seguindo para a próxima instância..."
    continue
  fi

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
