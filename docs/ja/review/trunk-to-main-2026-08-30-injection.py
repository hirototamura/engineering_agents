import json, tempfile, pathlib
from scenario.ssos_eclss_loop.evaluation_browser import write_evaluation_browser

root = pathlib.Path(tempfile.mkdtemp())
run = root / "run-a"
run.mkdir()
# A string that can plausibly reach evaluation.json: LLM-written prose, a model
# name passed via --set, or an ineligibility reason quoting model output.
payload = {
    "status": "scored",
    "run_conditions": {"run_id": "run-a", "actor": {"model": "</script><h1>INJECTED</h1><script>alert(1)//"}},
    "scores": {"total": 1, "max_score": 100},
}
(run / "evaluation.json").write_text(json.dumps(payload), encoding="utf-8")

out = write_evaluation_browser(root, default_run_id="run-a")
html = out.read_text(encoding="utf-8")
print("script tags in output:", html.count("<script>"))
print("closing tags       :", html.count("</script>"))
idx = html.find("INJECTED")
print("injected HTML escaped out of the JS string literal:", idx != -1)
print("...context...")
print(html[idx-120:idx+90])
