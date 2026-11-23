#!/bin/bash
set -euo pipefail

# Garante execução sempre a partir da raiz do projeto
cd "$(dirname "$0")"

CONFIG="run_config3.json"
TRUSTED_ROOT="data/trusted_model2"
LATEST_ROOT="data/latest_model2"
SKIP_EXISTING=false
USE_GUROBI=false
USE_WARM_START=false

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-existing)
      SKIP_EXISTING=true
      shift
      ;;
    --use-gurobi)
      USE_GUROBI=true
      shift
      ;;
    --use-warm-start)
      USE_WARM_START=true
      shift
      ;;
    --trusted-root)
      TRUSTED_ROOT="$2"
      shift 2
      ;;
    --latest-root)
      LATEST_ROOT="$2"
      shift 2
      ;;
    *)
      CONFIG="$1"
      shift
      ;;
  esac
done

if [ ! -f "$CONFIG" ]; then
  echo "Erro: arquivo de configuração não encontrado: $CONFIG" >&2
  exit 1
fi

echo "=========================================="
echo "  Configuração : $CONFIG"
echo "  Trusted root : $TRUSTED_ROOT"
echo "  Latest root  : $LATEST_ROOT"
echo "=========================================="

if [ "$USE_WARM_START" = true ]; then
  echo ">>> Compilando heurística C++ (src/heuristics)..."
  make -C src/heuristics
fi

TOTAL=$(python3 -c "
import json
d = json.load(open('$CONFIG'))
total = 0
for dt, cfg in d.items():
    m_by_st = cfg.get('machines_by_status')
    if m_by_st:
        total += len(m_by_st)
    else:
        total += 1
print(total)
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
      if [ ! -f "$TRUSTED_ROOT/$DATE_SLUG/$STATUS/output.json" ]; then
        ALL_DONE=false
        break
      fi
    done
    if [ "$ALL_DONE" = true ]; then
      echo "  [SKIP] $DT ($STATUSES) — output.json já existe em $TRUSTED_ROOT"
      continue
    fi
  fi

  echo ""
  echo "=========================================="
  echo "  [$CURRENT/$TOTAL - $PCT%]"
  echo "  dt           : $DT"
  echo "  status       : ${STATUSES:-todos}"
  echo "  machines     : ${MACHINES:-todas}"
  echo "  trusted_root : $TRUSTED_ROOT"
  echo "=========================================="

  echo ""
  echo ">>> [1/3] data_input_process.py"
  python3 src/main/data_input_process.py --dt "$DT" --trusted-root "$TRUSTED_ROOT" $ONLY_STATUS_ARG

  GUROBI_ARG=""
  if [ "$USE_GUROBI" = true ]; then
    GUROBI_ARG="--use-gurobi"
  fi

  WARM_START_ARG=""
  if [ "$USE_WARM_START" = true ]; then
    WARM_START_ARG="--use-warm-start"
    echo ""
    echo ">>> [Warm Start] Preparando solução heurística C++..."
    while IFS='|' read -r INPUT_FILE ORIG_HEUR_FILE MACHINE_ID MACHINE_NAME; do
      TARGET_HEUR_FILE="$(dirname "$INPUT_FILE")/output_heuristic.json"
      if [ -f "$ORIG_HEUR_FILE" ] && [ ! -f "$TARGET_HEUR_FILE" ]; then
        cp "$ORIG_HEUR_FILE" "$TARGET_HEUR_FILE"
        echo "  [Heurística] Reaproveitado output_heuristic.json de $ORIG_HEUR_FILE"
      fi
      if ! python3 -c "
import json, sys
from pathlib import Path
p = Path('$TARGET_HEUR_FILE')
if not p.exists():
    sys.exit(1)
data = json.loads(p.read_text(encoding='utf-8'))
found = any(m.get('machine_id') == $MACHINE_ID and m.get('objective_function') is not None for m in data.get('machines_scheduling', []))
sys.exit(0 if found else 1)
"; then
        echo "  [Heurística] Executando C++: $INPUT_FILE — $MACHINE_NAME (id=$MACHINE_ID)"
        python3 -m src.analysis.run_heuristic_multi "$INPUT_FILE" "$MACHINE_ID" --runs 10
      else
        echo "  [Heurística] Warm start disponível para $MACHINE_NAME (id=$MACHINE_ID)"
      fi
    done < <(python3 -c "
import json
from pathlib import Path

date_dir = Path('$TRUSTED_ROOT/$DATE_SLUG')
orig_date_dir = Path('data/trusted/$DATE_SLUG')
statuses = '$STATUSES'.split()
machines_filter = set('$MACHINES'.split())

if not statuses and date_dir.is_dir():
    statuses = [p.name for p in sorted(date_dir.iterdir()) if p.is_dir() and (p / 'input.json').exists()]

for st in statuses:
    inp = date_dir / st / 'input.json'
    orig_heur = orig_date_dir / st / 'output_heuristic.json'
    if not inp.exists():
        continue
    data = json.loads(inp.read_text(encoding='utf-8'))
    for m in data.get('machines', []):
        m_id = m['machine_id']
        m_name = m['machine_name']
        if machines_filter and m_name not in machines_filter:
            continue
        print(f'{inp}|{orig_heur}|{m_id}|{m_name}')
")
  fi

  echo ""
  echo ">>> [2/3] optimize.py"
  if ! python3 src/main/optimize.py --dt "$DT" --trusted-root "$TRUSTED_ROOT" $ONLY_STATUS_ARG $ONLY_MACHINES_ARG $GUROBI_ARG $WARM_START_ARG; then
    echo "  [AVISO] Falha ao executar optimize.py para $DT ($STATUSES) — seguindo para a próxima instância..."
    continue
  fi

  echo ""
  echo ">>> [3/3] data_output_process.py"
  python3 src/main/data_output_process.py --dt "$DT" --trusted-root "$TRUSTED_ROOT" --latest-root "$LATEST_ROOT" $ONLY_STATUS_ARG

  echo ""
  echo "  Concluído: $DT ($STATUSES) [$CURRENT/$TOTAL]"

done < <(python3 -c "
import json
d = json.load(open('$CONFIG'))
for dt, cfg in d.items():
    m_by_st = cfg.get('machines_by_status')
    if m_by_st:
        for st, ms in m_by_st.items():
            print(dt + '|' + st + '|' + ' '.join(ms))
    else:
        statuses = cfg.get('only_status', [])
        machines = cfg.get('machines', [])
        print(dt + '|' + ' '.join(statuses) + '|' + ' '.join(machines))
")

echo ""
echo "=========================================="
echo "  Pipeline finalizado. [$TOTAL/$TOTAL - 100%]"
echo "  Resultados salvos em: $TRUSTED_ROOT"
echo "=========================================="
