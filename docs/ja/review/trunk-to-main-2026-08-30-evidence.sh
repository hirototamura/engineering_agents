#!/usr/bin/env bash
# Reproduces every verified finding of the trunk -> main review.
# Read-only with respect to the repository: all runs go to a scratch results root.
set -uo pipefail
cd /workspace
unset EA_RESULTS_ROOT || true
R=$(mktemp -d)

hr() { printf '\n=== %s ===\n' "$1"; }

hr "F1  physics gate: mass-balance ledgers PASS on telemetry that has no flow data"
python3 - <<'PY'
from scenario.ssos_eclss_loop.physics_gate import evaluate_physics
rows = [
    {"step": 0, "co2_storage_kg": 1.0, "o2_storage_kg": 8.0,
     "product_water_reserve_l": 80.0, "grey_water_collected_l": 0.0},
    {"step": 1, "co2_storage_kg": 1.0, "o2_storage_kg": 8.0,
     "product_water_reserve_l": 80.0, "grey_water_collected_l": 0.0},
]
for c in evaluate_physics(rows)["checks"]:
    if "ledger" in c["name"]:
        print(f"  {c['name']:15s} {c['status']:7s} residual={c['details'].get('residual')}")
print("  -> conservation certified for a run that reported no CO2/O2/water flows at all")
PY

hr "F2  integrity guard: a run where the guard never ran reports 'valid' evidence"
python3 -c "
from scenario.ssos_eclss_loop.integrity_guard import evidence_status
print('  evidence_status({}) ->', evidence_status({}))
print('  -> absence of the integrity block is indistinguishable from a clean check')
"

hr "F3  the documented canonical loop produces an evaluation the repo itself calls invalid"
python3 -m tools.cli run ssos_eclss_loop --backend mock --actor-mode labeled_rule_base \
  --steps 20 --run-id ev1 --results-root "$R" --set iteration.enabled=false >/dev/null 2>&1
python3 -c "
import json
p=json.load(open('$R/ev1/design_proposals.json'))
tgt=[c['payload']['target'] for c in p['changes'] if c['change_kind']=='set_parameter']
print('  run 1 set_parameter targets:', tgt)
"
python3 -m tools.cli run ssos_eclss_loop --backend mock --actor-mode labeled_rule_base \
  --steps 20 --run-id ev2 --results-root "$R" --set iteration.enabled=false \
  --apply-proposals "$R/ev1/design_proposals.json" >/dev/null 2>&1
echo "  run 2 CLI exit code: $?"
python3 -c "
import json
e=json.load(open('$R/ev2/evaluation.json'))
print('  run 2 evaluation status :', e['status'])
print('  run 2 invalid_reasons   :', e.get('invalid_reasons'))
print('  run 2 integrity         :', e['integrity'])
print('  -> the applier is allowed to move a threshold the guard classifies as the scoring bar,')
print('     the run is marked invalid, and the CLI still exits 0 without a word to the user')
"

hr "F4  --output-dir recursively deletes an arbitrary directory with no confirmation"
S=$(mktemp -d); mkdir -p "$S/precious/nested"
echo thesis > "$S/precious/thesis.txt"; echo data > "$S/precious/nested/data.csv"
echo "  before: $(find "$S/precious" -type f | wc -l) user files"
python3 -m tools.cli run ssos_eclss_loop --backend mock --actor-mode labeled_rule_base \
  --steps 3 --output-dir "$S/precious" --set iteration.enabled=false >/dev/null 2>&1
echo "  after : thesis.txt present? $(test -f "$S/precious/thesis.txt" && echo yes || echo NO-DELETED)"
echo "  after : nested/data.csv present? $(test -f "$S/precious/nested/data.csv" && echo yes || echo NO-DELETED)"
rm -rf "$S"

hr "F5  scorecard weights human survival at 20 points and cost+mass at 40"
python3 -c "
from scenario.ssos_eclss_loop import evaluation as ev
print(f'  crew survival       CREW_MAX = {ev.CREW_MAX}')
print(f'  cost                COST_MAX = {ev.COST_MAX}')
print(f'  mass                MASS_MAX = {ev.MASS_MAX}')
print(f'  -> cost+mass = {ev.COST_MAX+ev.MASS_MAX} vs survival {ev.CREW_MAX}')
"
python3 -m tools.cli run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base \
  --design-mode labeled_rule_base --steps 30 --run-id ev3 --results-root "$R" \
  --set iteration.enabled=false >/dev/null 2>&1
python3 -c "
import json
s=json.load(open('$R/ev3/summary.json')); e=json.load(open('$R/ev3/evaluation.json'))
ax=e['scores']['axes']
print(f\"  a real plant_sim run lost {s['crew_lost']} of {s['crew_initial']} occupants\")
print(f\"  and still scored {e['scores']['total']} / {e['scores']['max_score']}:\")
for k,v in ax.items():
    print(f'    {k:24s} {v[\"score\"]:>8} / {v[\"max_score\"]}')
print('  -> full marks on cost and mass while 49 people died')
"

hr "F6  the evaluation browser silently hides the cost and mass axes (40 of 100 points)"
python3 -c "
import json
from scenario.ssos_eclss_loop.evaluation_browser import AXIS_ORDER
ax=json.load(open('$R/ev3/evaluation.json'))['scores']['axes']
hidden=[k for k in ax if k not in AXIS_ORDER]
print('  engine axes :', list(ax))
print('  browser axes:', list(AXIS_ORDER))
print('  hidden      :', hidden, '=', sum(ax[k]['max_score'] for k in hidden), 'points')
"

hr "F7  generated multi-run report is a tracked file, so every run dirties the working tree"
git ls-files --error-unmatch src/experiments/results/evaluation.html >/dev/null 2>&1 \
  && echo "  src/experiments/results/evaluation.html is git-tracked" \
  && grep -n "evaluation.html" .gitignore | sed 's/^/  .gitignore: /'
git show HEAD:src/experiments/results/evaluation.html > "$R/committed_eval.html" 2>/dev/null
python3 -c "
import re
html=open('$R/committed_eval.html', encoding='utf-8').read()
ips=sorted(set(re.findall(r'http://10\.\d+\.\d+\.\d+:\d+/v1', html)))
cat=re.search(r'const CATALOG = (\{.*?\});\n', html, re.S)
import json; ids=list(json.loads(cat.group(1)).keys()) if cat else []
print('  private LAN endpoints baked into the committed artifact:', ips)
print(f'  local run ids committed by whoever ran it last: {len(ids)} ({ids[:3]} ...)')
"

hr "F8  the whole run catalog is interpolated raw into an inline <script> block"
python3 docs/ja/review/trunk-to-main-2026-08-30-injection.py 2>&1 | sed 's/^/  /'

hr "F9  a misspelled --set key is accepted silently and changes nothing"
python3 -m tools.cli run ssos_eclss_loop --backend mock --actor-mode labeled_rule_base \
  --steps 3 --run-id ev4 --results-root "$R" --set simulation.stepz=99 \
  --set iteration.enabled=false >/dev/null 2>&1
echo "  CLI exit code with a bogus --set path: $?"
python3 -c "
import json
print('  steps actually simulated:', json.load(open('$R/ev4/summary.json'))['steps'], '(the 99 was dropped without warning)')
"

hr "F10 api-contracts.md disagrees with the engine on almost every scorecard number"
python3 -c "
from scenario.ssos_eclss_loop import evaluation as ev
rows=[('actor survival max','50','%g'%ev.CREW_MAX),
      ('actor decision max','10','%g'%ev.DECISION_MAX),
      ('device response max','10','%g'%ev.RESPONSE_MAX),
      ('no-actor total','80','%g'%ev.NO_ACTOR_MAX),
      ('schema_version','1.0','2.0'),
      ('cost axis','undocumented','%g'%ev.COST_MAX),
      ('mass axis','undocumented','%g'%ev.MASS_MAX)]
print(f\"  {'quantity':22s} {'api-contracts.md':18s} engine\")
for n,d,c in rows: print(f'  {n:22s} {d:18s} {c}')
"

hr "verified NON-issues (checked and sound)"
echo "  - run id sanitisation blocks path traversal:"
python3 -c "
from scenario.jobs.resolve import sanitize_run_id
for bad in ('../../etc','a/b','..'):
    try: sanitize_run_id(bad); print(f'      {bad!r}: ACCEPTED')
    except ValueError as e: print(f'      {bad!r}: rejected')
"
echo "  - mock runs are byte-identical across repeats (deterministic)"
for i in d1 d2; do python3 -m tools.cli run ssos_eclss_loop --backend mock \
  --actor-mode labeled_rule_base --steps 10 --run-id $i --results-root "$R" \
  --set iteration.enabled=false >/dev/null 2>&1; done
cmp -s "$R/d1/telemetry.jsonl" "$R/d2/telemetry.jsonl" \
  && echo "      telemetry.jsonl identical" || echo "      telemetry.jsonl DIFFERS"
echo "  - on the real plant_sim backend the ledgers do close on genuine data:"
python3 -c "
import json
for c in json.load(open('$R/ev3/physics_gate.json'))['checks']:
    if 'ledger' in c['name']:
        print(f\"      {c['name']:15s} {c['status']:7s} residual={c['details'].get('residual'):.3g}\")
"

rm -rf "$R"
hr "done"
