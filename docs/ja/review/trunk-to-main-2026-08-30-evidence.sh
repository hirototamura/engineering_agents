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

hr "C1  a run that rewrote its scoring bar is adopted as approved_final"
python3 - <<'PY'
from scenario.ssos_eclss_loop.design_eval import (
    mark_final_eligibility, select_final_candidate, rank_candidates)
cheater = {
    "candidate_id": "cheater", "simulated": True,
    "constraint_evaluation": {"preflight_status": "valid", "constraint_status": "feasible"},
    "outcome": {"backend": "plant_sim", "physics_gate_passed": True,
                "crew_initial": 50, "crew_remaining": 50,
                "evaluation_status": "invalid",          # the repo's own verdict
                "evaluation_compact": {"score": 54.15, "max_score": 100}},
}
mark_final_eligibility(cheater, baseline_outcome={"crew_remaining": 0})
sel = select_final_candidate(rank_candidates([cheater]), baseline_outcome={"crew_remaining": 0})
print("  final_eligible :", cheater["final_eligible"], cheater["final_ineligible_reasons"])
print("  final_status   :", sel["final_status"])
print("  needs approval :", sel["requires_supervisor_approval"])
print("  -> evaluation_status == 'invalid' is never consulted by the adoption path")
PY
printf '  production call sites of evidence_status: '
rg -n "evidence_status" src/ --glob '*.py' 2>/dev/null \
  | rg -v 'def evidence_status|"evidence_status"' | wc -l | tr -d ' '
echo "  (0 == dead code: the function that turns the verdict into a refusal is never called)"

hr "C3  the section-9 supervisor gate is inert on the rule-based design path"
python3 -c "
from scenario.ssos_eclss_loop.design_proposals import supervisor_approval_reasons
doc = {'design_domain':'ssos_graph','changes':[{'change_kind':'action_profile','payload':{}}]}
print('  no final_status      :', supervisor_approval_reasons(doc) or 'NO REASONS -> auto-adopted')
print('  provisional_final    :', supervisor_approval_reasons(dict(doc, final_status='provisional_final')))
"

hr "C6  the --apply-proposals input is destroyed and replaced by the run's own output"
python3 -m tools.cli run ssos_eclss_loop --backend mock --actor-mode labeled_rule_base \
  --steps 20 --run-id c6 --results-root "$R" --set iteration.enabled=false >/dev/null 2>&1
cp "$R/c6/design_proposals.json" "$R/c6_input_snapshot.json"
python3 -m tools.cli run ssos_eclss_loop --backend mock --actor-mode labeled_rule_base \
  --steps 20 --run-id c6 --results-root "$R" --set iteration.enabled=false \
  --apply-proposals "$R/c6/design_proposals.json" >/dev/null 2>&1
python3 -c "
import json
def ars(p): return [c['payload']['fields'] for c in json.load(open(p))['changes'] if c['change_kind']=='action_profile']
print('  content applied      :', ars('$R/c6_input_snapshot.json'))
print('  content at that path now:', ars('$R/c6/design_proposals.json'))
print('  summary records path :', json.load(open('$R/c6/summary.json')).get('apply_proposals_path'))
print('  -> the recorded provenance path no longer holds what was applied')
"

hr "C7  a design that survives the whole reference mission is censored, then ranked last"
python3 - <<'PY'
from scenario.ssos_eclss_loop.evaluation import _tcl_axis
from scenario.ssos_eclss_loop.design_eval import rank_candidates, candidate_rank_key
STEP = 1200.0
mk = lambda n: [{"step": i, "raw_topics": {"plant_sim": {"simulation_time_s": i*STEP}}} for i in range(n)]
cfg = {"tcl": {"reference_seconds": 57600.0}}   # == exactly 48 steps of mission
for n in (48, 49):
    ax = _tcl_axis(mk(n), [], cfg, STEP)        # no crew_lost -> full survival
    last = (ax.get("metrics") or {}).get("survived_through_seconds")
    print(f"  steps={n}  mission covered={n*STEP:.0f}s  last sample={last}  -> {ax['status']}")
cand = lambda cid, s: {"candidate_id": cid, "final_eligible": True,
    "outcome": {"crew_remaining": 50, "evaluation_compact": {"score": s, "max_score": 100}}}
for c in rank_candidates([cand("A_survives_full_mission", None), cand("B_worse_but_scorable", 40.0)]):
    print(f"  rank {c['rank']}  {c['candidate_id']:26s} key={candidate_rank_key(c)}")
print("  -> the better design sorts last (one censored axis nulls the total; unscored ranks last)")
PY

hr "C8  distinct proposals collide on candidate_hash and are skipped as duplicates"
python3 -c "
from scenario.ssos_eclss_loop.design_state import normalize_fields, candidate_hash
a={'plant_sim.ars.capacity_kg_day':'20'}; b={'plant_sim.ogs.max_o2_kg_day':'40'}
print('  normalize_fields(a) =', normalize_fields(a))
print('  hash(a)  =', candidate_hash(a))
print('  hash(b)  =', candidate_hash(b))
print('  hash({}) =', candidate_hash({}))
print('  a and b collide:', candidate_hash(a)==candidate_hash(b))
"

hr "H1  crew survival is worth 20 points; cost+mass are worth 40"
python3 -m tools.cli run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base \
  --design-mode labeled_rule_base --steps 48 --run-id h1 --results-root "$R" \
  --set iteration.enabled=false >/dev/null 2>&1
python3 -c "
import json
s=json.load(open('$R/h1/summary.json')); e=json.load(open('$R/h1/evaluation.json'))
print(f\"  crew {s['crew_remaining']} / {s['crew_initial']}  ->  TOTAL {e['scores']['total']} / {e['scores']['max_score']}\")
for k in ('actor_survival','cost','mass'):
    a=e['scores']['axes'][k]; print(f\"    {k:16s} {a['score']:>6} / {a['max_score']}\")
print('  -> the entire crew is dead and the design still banks 40 points for being small')
"

hr "H6  an explicit --steps loses to --override-file"
printf 'simulation:\n  steps: 99\n' > "$R/ov.yaml"
python3 -m tools.cli run ssos_eclss_loop --backend mock --actor-mode labeled_rule_base \
  --steps 3 --run-id h6 --results-root "$R" --override-file "$R/ov.yaml" \
  --set iteration.enabled=false >/dev/null 2>&1
python3 -c "
import json;print('  asked --steps 3, actually ran', json.load(open('$R/h6/summary.json'))['steps'], 'steps')"

hr "H7  the test suite is not hermetic: an ambient env var fails 4 tests"
EA_RESULTS_ROOT=/tmp/ambient-review-root python3 -m pytest tests/tools/test_ssos_host.py \
  -q -p no:randomly 2>&1 | tail -2 | sed 's/^/  /'

hr "M6  audit.count = 0 silently becomes 3 auditors"
python3 -c "
from scenario.ssos_eclss_loop.design_ensemble import resolve_audit_config
for n in (0, 1, None):
    print(f'  audit.count={str(n):5s} -> {len(resolve_audit_config({\"audit\": {\"count\": n}})[\"agents\"])} auditor(s)')
"

hr "M9  core imports environment, against the documented layering rule"
rg -n "^from environment" src/core/agents/types.py src/core/scenario.py | sed 's/^/  /'
rg -n "Do not import upward" AGENTS.md | sed 's/^/  AGENTS.md /'

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
