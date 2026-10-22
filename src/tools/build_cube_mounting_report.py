"""Build a compact bilingual view of the measured first-corner correction."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
from pathlib import Path


def build(study_root, run_dir, previous_result):
    sources = []
    def load(path):
        content = path.read_bytes()
        sources.append({"path": str(path.resolve()), "sha256": hashlib.sha256(content).hexdigest()})
        return json.loads(content)
    comparison = load(study_root / "native-final/comparison.json")
    summary = load(run_dir / "summary.json")
    validation = load(run_dir / "validation/result.json")
    previous = load(previous_result)
    qualification = load(study_root / "server/qualification/qualification.json")
    deployment = load(study_root / "server/deployment-verification.json")
    nominal_rebuilt = load(study_root / "native-comparison/comparison.json")["cells"]["M1C1"]
    reference_rebuilt = load(study_root / "reference-controller-check/result.json")
    comparison = copy.deepcopy(comparison)
    # Older comparison metadata used a stale "rebuilt_lower" label for C1.
    # The saved controller and digest identify the retained MASS controller.
    for key, cell in comparison["cells"].items():
        if key.endswith("C1"):
            cell["controller"] = "retained_MASS"
    selected = comparison["cells"]["M1C1"]
    passes = lambda result: f'{round(result["screening_pass_fraction"] * result["trial_count"])}/{result["trial_count"]}'
    fixture_passes = f'{sum(c["passed"] for c in qualification["comparisons"])}/{len(qualification["comparisons"])}'
    old_height = comparison["geometry"]["upper"]["com_above_corner_world_m"][2] * 1000
    new_height = comparison["geometry"]["lower"]["com_above_corner_world_m"][2] * 1000
    assert qualification["state"] == "verified_for_fixtures"
    assert selected["all_screening_passed"] and validation["all_screening_passed"]
    def heavy(result):
        return next(r["summary"] for r in result["records"] if "heavy" in r["domain_id"]
                    and r["condition_id"] == "confirm-b" and r["seed"] == 812)
    earlier, current = heavy(previous), heavy(validation)
    svg_file = study_root / "figures/mounting-comparison.svg"
    svg = svg_file.read_text()
    sources.append({"path": str(svg_file.resolve()), "sha256": hashlib.sha256(svg_file.read_bytes()).hexdigest()})
    svg = svg[svg.index("<svg"):]
    data = {"run_id": summary["run_id"], "source_snapshot_refs": comparison["source_snapshot_refs"],
        "geometry": comparison["geometry"], "cells": comparison["cells"],
        "existing_confirmation": {k: validation[k] for k in ("score", "trial_count", "screening_pass_fraction", "all_screening_passed", "gpu_state")},
        "known_heavy_case": {"previous": earlier, "lower_mount": current},
        "implementation_fixtures": qualification, "deployment": deployment, "sources": sources,
        "physical_verified": False, "other_seven_corners_verified": False}
    data["controller_label_note"] = "C1 is the retained MASS controller; original raw comparison labels were stale. Controller values, digests and measured results are unchanged."
    (run_dir / "mounting-report-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    def table(headers, rows):
        esc = lambda value: html.escape(str(value))
        return '<div class="scroll"><table><thead><tr>' + ''.join('<th>'+esc(h)+'</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+esc(c)+'</td>' for c in row)+'</tr>' for row in rows) + '</tbody></table></div>'
    output = []
    for lang in ("en", "ja"):
        def t(en, ja): return en if lang == "en" else ja
        title = t("First trial: lower-face reaction wheels", "初回試験：リアクションホイールを下側3面へ")
        other = "bottom-corner-trial-report.ja.html" if lang == "en" else "bottom-corner-trial-report.html"
        parts = [f'<header>One-Piece / Engineering Agents · 17 October 2026 <a href="{other}">{t("日本語", "English")}</a></header>',
            f'<main><h1>{title}</h1>',
            '<p class="lead">'+t("The mission covers all eight corners. This first trial implements corner 000, with fixed wheels on the three faces that meet at that corner.", "ミッションは8頂点すべてでの倒立保持です。初回試験は頂点000を対象とし、その頂点に接する3面にホイールを固定します。")+'</p>',
            '<p class="verdict">'+t(f"{passes(selected)} native MuJoCo development cases and {passes(validation)} existing confirmation cases passed. Representative native MuJoCo–MJX comparisons: {fixture_passes} passed, including cases that correctly lost balance. Hardware and the other seven corners remain unverified.", f"ネイティブMuJoCoで開発条件{passes(selected)}件、既存の確認条件{passes(validation)}件が合格しました。代表ケースのネイティブMuJoCo–MJX整合は{fixture_passes}件で成立し、想定どおり倒立を失うケースも含みます。実機と残り7頂点は未検証です。")+'</p>',
            '<h2>'+t("What physically changed in the model", "モデルで変更した物理配置")+'</h2><figure>'+svg+'</figure>',
            '<p>'+t(f"The mass and rotor inertias are unchanged. The numerical reference’s combined COM height falls from {old_height:.1f} to {new_height:.1f} mm above corner 000. The modeled wheel/rotor bodies move; fixed motor/stator mass remains lumped into the frame. Hardware mass distribution is uncalibrated.", f"総質量とロータ慣性は変えていません。数値比較の参照設計では、頂点000からの合成重心高さが{old_height:.1f} mmから{new_height:.1f} mmに下がります。移動するのはモデルのホイール・ロータ物体です。固定モータ・ステータ質量はフレームに集約したままで、実機の質量分布は未校正です。")+'</p>',
            '<h2>'+t("Separate mounting effects from controller effects", "配置の効果と制御器の効果を分ける")+'</h2>',
            '<p>'+t(f"The four cells use the same disclosed conditions, 1 ms physics timestep and 15 ms control period. The retained MASS controller is identical in both geometries. Lower COM did not improve its exploration score: {comparison['cells']['M0C1']['score']:.6f} → {selected['score']:.6f}. Both geometries passed these development gates with that controller.", f"4組を同じ公開済み条件、物理刻み1 ms、制御周期15 msで比較しました。保持したMASS制御器は両形状で同一です。重心は下がりましたが、その探索スコアは{comparison['cells']['M0C1']['score']:.6f}から{selected['score']:.6f}へ低下しました。この制御器では、両形状とも開発ゲートを通過しました。")+'</p>',
            table([t("Cell", "組合せ"),t("Mounting", "取付"),t("Controller", "制御器"),t("Gate passes", "ゲート合格"),"Score S"],
                [[key, cell["mount"], cell["controller"], f'{round(cell["screening_pass_fraction"] * cell["trial_count"])}/{cell["trial_count"]}', f'{cell["score"]:.6f}'] for key,cell in comparison["cells"].items()]),
            '<p>'+t(f"Two relinearized LQR alternatives passed only {passes(nominal_rebuilt)} and {passes(reference_rebuilt)} lower-mount cases. We kept those failures and retained the tested MASS controller. Subsequent Q edits use its exact frozen design-plant source; they do not silently change the plant used to generate K.", f"再線形化した2種類のLQRは、下側取付で{passes(nominal_rebuilt)}件と{passes(reference_rebuilt)}件にとどまりました。これらの失敗を保持し、試験済みMASS制御器を採用した暫定構成にしています。後のQ重み変更も、その設計プラントの正確な版を参照し、Kを作るプラントを暗黙に変えません。")+'</p>',
            '<h2>'+t("A known failure now passes", "既知の失敗条件の改善")+'</h2>',
            '<p><code>heavy-delay-prior-confirm / confirm-b / seed 812</code></p>',
            table([t("Metric", "指標"),t("Previous upper mounts", "以前の上側取付"),t("Lower mounts", "下側取付")], [
                ["speed_governor_fraction", f'{earlier["speed_governor_fraction"]:.1%}',f'{current["speed_governor_fraction"]:.1%}'],
                ["peak_tilt_deg",f'{earlier["peak_tilt_deg"]:.3f}',f'{current["peak_tilt_deg"]:.3f}'],
                ["final_1s_tilt_rms_deg",f'{earlier["final_1s_tilt_rms_deg"]:.3f}',f'{current["final_1s_tilt_rms_deg"]:.3f}']]),
            '<p class="caption">'+t("The speed-governor limit is 1%. These conditions were already disclosed; this is not a fresh or independent validation claim. A six-second simulation does not establish the draft thirty-second hardware hold.", "速度ガバナのしきい値は1%です。これらは公開済みの条件であり、新しい独立検証という主張ではありません。6秒のシミュレーションで、草案の実機30秒保持を示したことにはなりません。")+'</p>',
            '<h2>'+t("Check the implementations on representative fixtures", "代表ケースで実装の整合を確認")+'</h2>',
            table([t("Fixture", "ケース"),"native MuJoCo","MJX",t("Agreement", "整合")], [[r["id"],r["native_status"],r["mjx_status"],r["state"]] for r in qualification["comparisons"]]),
            '<p>'+t("These checks used saved K on MJX GPUs 6 and 7. Both implementations must also agree on expected failures. This covers four fixtures for the lower-face reference, not the full design envelope. Selective comparison in the design-loop runner still needs implementation.", "保存Kを使い、MJXはGPU 6と7で実行しました。想定した失敗も両実装で一致することを確認します。対象は下側取付の参照設計の4ケースであり、設計範囲全体ではありません。設計ループでの選択的比較は今後実装する必要があります。")+'</p>',
            '<h2>'+t("Six GPUs serve Qwen; two serve MJX", "Qwenに6 GPU、MJXに2 GPU")+'</h2>',
            '<div class="allocation"><b>Qwen replica 0 · GPU 0,1</b><b>Qwen replica 1 · GPU 2,3</b><b>Qwen replica 2 · GPU 4,5</b><b>MJX · GPU 6,7</b></div>',
            '<p>'+t("Native MuJoCo uses CPUs. Six concurrent short Qwen requests succeeded; every replica served two requests. This demonstrates deployment, not a sixfold latency improvement or a new LLM design campaign. The service is currently a transient user systemd service, with a preserved rollback launcher.", "ネイティブMuJoCoはCPUで実行します。Qwenへの短い6件の同時要求が成功し、各レプリカが2件ずつ処理しました。これはデプロイの確認であり、遅延が6分の1になったことや新しいLLM設計探索を示すものではありません。現在は一時的なユーザーsystemdサービスで動作し、復元用の旧ランチャーを保持しています。")+'</p>',
            '<details><summary>'+t("Exact records, measurements and source hashes", "正確な記録・測定値・出典ハッシュ")+'</summary><pre>'+html.escape(json.dumps(data,ensure_ascii=False,indent=2))+'</pre></details>',
            '<footer><code>cube.simulation.snapshot@bottom-corner-000-20261017-3</code><br>'+t("Requirement wording is draft. No adopted baseline, other-corner performance or physical validity is claimed.", "要求文は草案です。採用ベースライン、他頂点の性能、物理的妥当性は確定していません。")+'</footer></main>']
        page=f'<!doctype html><html lang="{lang}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{margin:0;background:#faf9f5;color:#202d34;font:17px/1.7 system-ui,sans-serif}}main,header{{max-width:1080px;margin:auto;padding:24px}}header{{border-bottom:1px solid #cdd3d1;font-size:14px}}header a{{float:right}}a{{color:#24566d}}h1{{font:500 clamp(32px,5vw,54px)/1.2 Georgia,serif}}h2{{font:500 29px/1.3 Georgia,serif;margin-top:48px}}.lead{{font-size:21px}}.verdict{{border-left:3px solid #b64628;background:#f0f1eb;padding:14px 20px}}figure{{margin:20px 0}}figure svg{{width:100%;height:auto}}.scroll,pre{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px;min-width:560px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #cdd3d1}}.caption,footer{{font-size:13px;color:#5b686e}}.allocation{{display:flex;gap:12px;flex-wrap:wrap}}.allocation b{{border-top:3px solid #24566d;padding-top:10px;font-size:14px}}pre{{font:11px/1.5 ui-monospace,monospace;max-height:440px}}details,footer{{border-top:1px solid #cdd3d1;margin-top:32px;padding-top:20px}}@media(max-width:650px){{main,header{{padding:18px}}body{{font-size:16px}}}}</style><body>'+''.join(parts)+'</body></html>'
        path=run_dir/('bottom-corner-trial-report.html' if lang=='en' else 'bottom-corner-trial-report.ja.html')
        path.write_text(page,encoding='utf-8');output.append(path)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-root',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--previous-result',type=Path,required=True)
    args=parser.parse_args()
    for path in build(args.study_root.resolve(),args.run_dir.resolve(),args.previous_result.resolve()):print(path)


if __name__=='__main__':main()
