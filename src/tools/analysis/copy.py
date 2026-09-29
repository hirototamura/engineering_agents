"""Locale strings for the self-contained HTML report.

Numbers are never stored here: :func:`tools.analysis.report.render` interpolates
every quantity from the findings dictionary. Axis labels inside the matplotlib
SVGs stay in English (units and ``ρ``) so mathtext does not fight a CJK font;
figure titles and captions in the HTML are translated.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

SUPPORTED_LANGS = ("en", "ja")

DEFAULT_TITLE = {
    "en": "Physics of a design agent",
    "ja": "設計エージェントの物理",
}
DEFAULT_SUBTITLE = {
    "en": "Order parameters, criticality and controllability of the ECLSS design-verify loop",
    "ja": "ECLSS 設計→検証ループの順序変数・臨界性・可制御性",
}

_EN: Dict[str, Any] = {
    "html_lang": "en",
    "figure_prefix": "Figure",
    "yes": "yes",
    "no": "no",
    "lang_en": "English",
    "lang_ja": "日本語",
    "generated": "Generated {generated} from {n_runs} simulations",
    "backend_line": "Engineering Agents <code>ssos_eclss_loop</code> · plant_sim backend",
    "footer": (
        "Reproduce with <code>python3 -m tools.analysis run</code> then "
        "<code>python3 -m tools.analysis report</code>. Every number in this document "
        "is computed from the datasets under <code>src/experiments/analysis/datasets/</code>; "
        "none is typed in."
    ),
    "kpi_simulations": "simulations analysed",
    "kpi_saving": "designs saving the crew",
    "kpi_budget": "of those within budget",
    "kpi_zero_gain": "axes with zero gain",
    "kpi_archetype": "dominant loop archetype",
    "h_summary": "Summary",
    "summary_intro": (
        "This report treats an Engineering Agents campaign as a dynamical system on a "
        "design space and characterises it the way a physical system would be characterised: "
        "identify the order parameter, locate the transition, measure the response, and only "
        "then judge the controller. Three results follow, in that order."
    ),
    "key1": (
        "<p><b>1. The system has one order parameter and a sharp transition.</b> "
        "Survival is governed by how much margin each subsystem has against its own critical "
        "coverage. Two logistics combined by the law of the minimum explain "
        "{r2} of the variance in surviving crew on held-out designs from the {n}-point grid. "
        "Scaling the hardware up and scaling the crew down — two physically unrelated "
        "manipulations — trace the same curve to within {delta} crew fraction.</p>"
    ),
    "key2": (
        "<p><b>2. The mission is infeasible under its own budget.</b> "
        "Of {n} designs on the grid, {n_full} keep the whole crew alive and "
        "<b>{n_budget}</b> of those fit inside the declared "
        "<code>design_constraints.budgets</code>. The lightest surviving station masses "
        "{mass} kg against a {mass_ceil} kg ceiling ({over}% over) and costs "
        "{cost} MUSD against {cost_ceil} MUSD. No design agent, however good, can satisfy "
        "both. Under this repository's own stated hierarchy — the mission is paramount and "
        "design requirements may be revised beneath it — the budget is the requirement that "
        "has to move.</p>"
    ),
    "key3": (
        "<p><b>3. The shipped rule designer actuates axes with zero gain at the point where "
        "it starts.</b> It places {action_share} of its step magnitude in the action subspace "
        "and {capacity_share} in the capacity subspace. At the shipped operating point every "
        "action and policy axis measures a gain of exactly zero: sweeping them over a 20-fold "
        "range leaves surviving crew unchanged. Every chain lands in the <i>saturating</i> "
        "archetype — the loop moves steadily (turning cosine {cosine}, i.e. a perfectly "
        "straight march) and the outcome never changes.</p>"
    ),
    "h_method": "Method and data",
    "method_p1": (
        "Every run is a 72-step <code>plant_sim</code> simulation of a 24-hour mission with 50 "
        "crew, driven through the documented CLI. A design is imposed by writing a "
        "<code>capacity_profile</code> proposal and passing it to <code>--apply-proposals</code>, "
        "which is the same path the tool-use designer uses to adopt a candidate, so the "
        "experiment grid and the agent's own proposals move through identical code."
    ),
    "method_p2": (
        "One consequence of using that path is worth stating, because it shapes what the grid "
        "measures. Applying a capacity change also runs <code>sync_action_payloads</code>, which "
        "raises the crew's request to what the new hardware can honour. Every point on the "
        "response surface is therefore a <i>well-operated</i> station rather than new hardware "
        "driven by stale procedures, which is the right comparison for a sizing question and is "
        "also what the design agent would actually ship. The one-at-a-time sweeps deliberately do "
        "not sync, so they isolate the payload axis on its own."
    ),
    "method_figures_note": "",
    "th_dataset": "dataset",
    "th_runs": "runs",
    "th_varies": "what it varies",
    "th_answers": "what it answers",
    "datasets": [
        ["seed replicates", "--seed only", "is the plant stochastic?"],
        ["response surface", "ARS x OGS nameplate", "phase diagram, criticality, cost of survival"],
        ["one-at-a-time", "one axis, shipped point", "controllability where the loop starts"],
        ["one-at-a-time (relieved)", "one axis, OGS sized to 42 kg/day",
         "controllability once O2 is not binding"],
        ["crew scaling", "crew size, station fixed", "denominator half of the collapse test"],
        ["iso-ray", "all capacities by a common factor", "numerator half of the collapse test"],
        ["design chains", "--iterate length", "the closed loop actually running"],
    ],
    "h_uncertainty": "Where the uncertainty is",
    "p_uncertainty": (
        "Replaying one configuration under {n_seeds} different seeds reproduces the outcome "
        "exactly: the spread in evaluation score across seeds is {score_spread} and in surviving "
        "crew {crew_spread}. With rule-based actors and designers the whole pipeline is "
        "deterministic, so there is no replicate noise to bootstrap over. Every interval in this "
        "report is therefore taken across design points and scenario conditions, which is where "
        "the variation genuinely lives. Stochasticity would enter only through an LLM designer, "
        "which needs a provider this analysis did not have."
    ),
    "fig_mass_title": "Conservation holds in every run",
    "fig_mass_caption": (
        "The physics gate recomputes each mass ledger independently of the state it audits and "
        "passed in {passed} of {total} runs. Residuals are identically zero, so no result below "
        "is an artefact of a leaking simulator."
    ),
    "h_order": "The order parameter and its transition",
    "p_order": (
        "The three sizing variables have different units and baselines that differ by an order "
        "of magnitude, so they cannot be compared directly. Dividing each by the crew's daily "
        "demand for the same quantity gives a dimensionless coverage ratio ρ whose unit point is "
        "physically meaningful: ρ = 1 is the smallest station that services the crew in steady "
        "state. Liebig's law of the minimum then suggests the binding coverage "
        "ρ<sub>min</sub> = min(ρ<sub>ARS</sub>, ρ<sub>OGS</sub>, ρ<sub>WRS</sub>) as the single "
        "scalar order parameter. The shipped station sits at ρ<sub>ARS</sub> = 0.087 and "
        "ρ<sub>OGS</sub> = 0.220 — undersized by a factor of eleven and five."
    ),
    "fig_phase_title": "Survival phase diagram",
    "fig_phase_caption": (
        "The habitable region is bounded on the O2 axis and is entered well below ρ = 1 on the "
        "CO2 axis, because the survival rule watches stored CO2 rather than instantaneous removal."
    ),
    "fig_crit_title": "Order parameter and susceptibility",
    "fig_crit_caption": (
        "The plant is deterministic, so the susceptibility is the derivative of the response, not "
        "a variance over replicates. Its peak locates the critical coverage."
    ),
    "th_crit_axis": "axis",
    "th_rho_star": "critical coverage ρ*",
    "th_width": "transition width",
    "th_peak": "peak susceptibility",
    "th_r2": "R²",
    "profile_names": {},
    "h_collapse": "A falsification test of the coverage ratio",
    "p_collapse": (
        "If ρ really is the order parameter, then halving the crew and doubling the hardware "
        "must be the same intervention, because both double ρ. The two sweeps share no runs and "
        "manipulate physically unrelated quantities. They agree to within {max_abs} crew fraction "
        "at worst and {mean_abs} on average across {n_paired} paired points, with correlation "
        "{corr}. The residual gap is real and systematic: at equal ρ a smaller crew does slightly "
        "better, because a fixed per-operation batch size serves a smaller crew proportionally "
        "further."
    ),
    "fig_collapse_title": "Two independent sweeps collapse onto one curve",
    "fig_collapse_caption": (
        "Adding hardware and removing people are different physical acts that move the same "
        "dimensionless quantity, and the response follows the quantity rather than the act."
    ),
    "h_steer": "What the loop can steer, and what it steers",
    "fig_ctrl_title": "Controllability against actuation",
    "fig_ctrl_caption": (
        "Only one axis moves the outcome at the point where the loop starts, and it is the one "
        "the shipped designer never touches."
    ),
    "p_span": (
        "At the shipped operating point, sweeping every action-subspace axis across "
        "{n_mult} multipliers spanning {lo}× to {hi}× produces exactly {n_out} distinct "
        "outcome{plural}: {outcomes}. The mechanism is visible in the operations log."
    ),
    "fig_sat_title": "Why the request payload does nothing for O2",
    "fig_sat_caption": (
        "The plant delivers the smaller of the request and the nameplate and says so in "
        "limited_by, so everything above the nameplate is discarded on arrival. This is the "
        "mechanism behind the zero gain measured above, read off the plant's own limiter field "
        "rather than inferred."
    ),
    "h_state_dep": "Controllability is state-dependent",
    "th_subspace": "subspace",
    "th_gain_shipped": "gain at shipped point",
    "th_gain_relieved": "gain with O2 relieved",
    "p_state_dep": (
        "The highlighted rows are the important ones. They have zero gain where the loop starts "
        "and substantial gain once the oxygen famine is lifted, which means the shipped designer's "
        "preferred axis is not useless in general — it is useless <i>until a different subsystem "
        "is fixed first</i>. Diagnosing that requires reasoning about which constraint binds, and "
        "the rule designer's fixed multiplicative policy has no mechanism to do so. One-at-a-time "
        "sensitivity measured at a single operating point would have concluded the axis was dead; "
        "the second sweep is what distinguishes the two cases."
    ),
    "h_rugged": "The landscape is not monotone",
    "p_rugged": (
        "Along the ARS axis, {descents} of {transitions} grid transitions ({rate}) move the "
        "outcome <i>down</i> while capacity goes up, with a worst single descent of {worst} "
        "crew fraction. Adding hardware can cost lives here because the operations are scheduled "
        "against a busy guard: a larger batch occupies the subsystem for longer and can miss the "
        "window in which the next one was needed. A designer that trusts one evaluation per step "
        "and climbs greedily will be sent backwards by these reversals, which is an argument for "
        "the multi-candidate re-simulation the tool-use designer performs rather than for a larger "
        "step size."
    ),
    "h_loop": "The closed loop as a trajectory",
    "fig_loop_title": "Order parameters of the design chain",
    "fig_loop_caption": (
        "Displacement grows linearly, the step size never decays, the turning angle is pinned at "
        "+1, and the outcome is flat. This is an open-loop march, not a search."
    ),
    "fig_arch_title": "Trajectory archetypes",
    "fig_arch_caption": (
        "Separating 'proposed nothing' from 'proposed something ineffective' matters: the two look "
        "identical in an outcome plot and have opposite fixes."
    ),
    "th_chain": "chain",
    "th_iterations": "iterations",
    "th_archetype": "archetype",
    "th_displacement": "displacement",
    "th_dsurvival": "Δ survival",
    "th_cap_share": "capacity share",
    "th_act_share": "action share",
    "th_discarded": "proposals discarded",
    "p_discarded": (
        "A further {rate} of proposals never reach a simulation at all. The chain strips every "
        "<code>set_parameter</code> change from <code>applied_proposals.json</code> to keep the "
        "verification requirements frozen across iterations — a correct and deliberate safeguard, "
        "since a designer that can move its own acceptance thresholds can declare success without "
        "changing the plant. The designer, however, is never told, so it re-proposes the identical "
        "threshold change on every iteration and spends two of its five proposal slots on a move "
        "that is discarded by construction."
    ),
    "h_tcl": "Time to first crew loss",
    "log_rank": "Log-rank χ²(1) = {stat}, p = {p}.",
    "fig_surv_title": "Survival curves by coverage regime",
    "fig_surv_caption": (
        "Designs above and below half coverage separate immediately and never re-cross. "
        "Censoring is taken from the scorecard's own right_censored status rather than imputed."
    ),
    "h_predictive": "A compact predictive law",
    "p_predictive": (
        "The comparison below follows the structure used for collective-dynamics models: a "
        "trivial baseline, single-variable models, and the structured models the physics "
        "suggests. Each is fitted on a random half of the grid ({n_train} designs) and scored on "
        "the other half ({n_test}), so a flexible model cannot win by memorising the surface. "
        "Balanced accuracy accompanies R² because the outcome saturates hard at 0 and 1, and "
        "plain accuracy would reward a constant predictor."
    ),
    "th_model": "model",
    "th_heldout_r2": "held-out R²",
    "th_rmse": "RMSE",
    "th_ba": "balanced accuracy",
    "th_assumes": "what it assumes",
    "model_notes": {},
    "p_predictive_result": (
        "The law of the minimum as usually stated does <i>badly</i> here — held-out R² of "
        "{naive}, worse than ignoring the CO2 axis altogether ({ogs_only}). The reason is that "
        "the two subsystems do not become critical at the same coverage: the ARS transition sits "
        "at ρ* = {star_ars} and the OGS transition at ρ* = {star_ogs}. Taking the raw minimum "
        "therefore names the wrong bottleneck wherever the numerically smaller coverage is the "
        "one with the lower threshold, which on this grid is most cells. Rescaling each coverage "
        "by its own critical value first recovers {margin}, and taking the minimum of the two "
        "fitted <i>responses</i> rather than of their inputs reaches {response} on held-out "
        "designs. Two logistics, four parameters, and a minimum reproduce a 121-point response "
        "surface. The quantity that matters is each subsystem's margin against its own threshold, "
        "not its raw coverage."
    ),
    "fig_pred_title": "Observed against predicted survival",
    "fig_pred_caption": (
        "Two logistics in the two coverage ratios, combined by the law of the minimum, "
        "reproduce a 121-point response surface."
    ),
    "h_cost": "The cost of keeping the crew alive",
    "fig_pareto_title": "Survival against station footprint",
    "fig_pareto_caption": (
        "The feasible box and the surviving set do not intersect. This is a property of the "
        "requirements, not of any agent that searches inside them."
    ),
    "p_cost": (
        "The lightest station on the grid that keeps all 50 crew alive sizes ARS to {ars} kg/day "
        "and OGS to {ogs} kg/day, reaching ρ<sub>ARS</sub> = {rho_ars} and ρ<sub>OGS</sub> = "
        "{rho_ogs}. It masses {mass} kg, costs {cost} MUSD and occupies {volume} m³, against "
        "ceilings of {mass_ceil} kg, {cost_ceil} MUSD and {vol_ceil} m³. It breaches all three."
    ),
    "h_implies": "What this implies for the design agent",
    "imp1_title": "Report infeasibility as a result, not a failure.",
    "imp1": (
        "The chain currently ends with <code>NOT_IMPROVED</code>, which reads as an agent that "
        "underperformed. The measured situation is that the mission and the budget cannot both "
        "be met, and the honest output is a request to revise the budget with the cheapest "
        "surviving design attached as evidence."
    ),
    "imp2_title": "Make the binding constraint drive the proposal.",
    "imp2": (
        "The plant already reports <code>limited_by</code> and <code>fully_satisfied</code> on "
        "every operation, and those fields identify the binding subsystem exactly. A designer "
        "that reads them would not spend six iterations enlarging a request the backend discards."
    ),
    "imp3_title": "Tell the designer what was discarded.",
    "imp3": (
        "Freezing the requirements is right; silently dropping the proposals is what makes the "
        "designer repeat them. Echoing the filtered changes back would free two of five proposal "
        "slots immediately."
    ),
    "imp4_title": "Do not climb greedily.",
    "imp4": (
        "{rate} of capacity increases along the ARS axis make the outcome worse, so "
        "single-evaluation hill climbing is unreliable here. The tool-use designer's "
        "multi-candidate re-simulation is the right shape of answer."
    ),
    "imp5_title": "Instrument coverage directly.",
    "imp5": (
        "ρ is computable from the config before a run starts and predicts the outcome with "
        "R² = {r2}. Surfacing it in the scorecard would turn most of this analysis into a "
        "single pre-flight number."
    ),
    "h_limits": "Limits of this analysis",
    "lim1": (
        "Both agent sides run in <code>labeled_rule_base</code> mode. No LLM provider was "
        "reachable, so the tool-use designer that <i>can</i> emit <code>capacity_profile</code> "
        "changes was never exercised. The controllability and phase-diagram results characterise "
        "the plant and therefore apply to any designer; the loop-dynamics results characterise "
        "the rule designer specifically."
    ),
    "lim2": (
        "All runs use the <code>plant_sim</code> backend. The <code>mock</code> backend "
        "produces no survival or scorecard data, and <code>ros2</code> needs SSOS Docker."
    ),
    "lim3": (
        "Failure injection is off in the sweeps so that coverage is the only thing varying. "
        "The chains keep the shipped default, which enables it."
    ),
    "lim4": (
        "The grid is {n} points over two axes with WRS held fixed, justified by its measured "
        "zero gain and a baseline coverage of 6.4. A finer grid would sharpen the critical "
        "coverage estimates but is unlikely to move the qualitative conclusions."
    ),
}

_JA: Dict[str, Any] = {
    "html_lang": "ja",
    "figure_prefix": "図",
    "yes": "はい",
    "no": "いいえ",
    "lang_en": "English",
    "lang_ja": "日本語",
    "generated": "{generated} に {n_runs} 件のシミュレーションから生成",
    "backend_line": "Engineering Agents <code>ssos_eclss_loop</code> · plant_sim バックエンド",
    "footer": (
        "再現は <code>python3 -m tools.analysis run</code> のあと "
        "<code>python3 -m tools.analysis report</code>。"
        "本文の数値はすべて <code>src/experiments/analysis/datasets/</code> から算出しており、手入力はない。"
    ),
    "kpi_simulations": "解析したシミュレーション",
    "kpi_saving": "乗員を救う設計",
    "kpi_budget": "うち予算内",
    "kpi_zero_gain": "ゲインゼロの軸",
    "kpi_archetype": "支配的なループ原型",
    "h_summary": "要約",
    "summary_intro": (
        "本レポートは Engineering Agents のキャンペーンを設計空間上の力学系として扱い、物理系と同じ手順で"
        "特徴づける。順序変数を特定し、転移を求め、応答を測り、そのうえで初めて制御器を評価する。"
        "結果はこの順に三つある。"
    ),
    "key1": (
        "<p><b>1. 系には一つの順序変数と鋭い転移がある。</b>"
        "生存は、各サブシステムが自身の臨界カバレッジに対してどれだけ余裕を持つかで決まる。"
        "最小律で結合した二つのロジスティックは、{n} 点グリッドのホールドアウト設計において"
        "生存乗員の分散の {r2} を説明する。"
        "ハードウェアを増やす操作と乗員を減らす操作は物理的には無関係だが、同じ曲線を乗員比にして"
        "{delta} 以内でなぞる。</p>"
    ),
    "key2": (
        "<p><b>2. ミッションは宣言された予算の下では実行不能である。</b>"
        "グリッド上の {n} 設計のうち乗員全員を生かすのは {n_full}、そのうち宣言された "
        "<code>design_constraints.budgets</code> に収まるのは <b>{n_budget}</b>。"
        "最も軽い生存ステーションは質量 {mass} kg（上限 {mass_ceil} kg、{over}% 超過）、"
        "費用 {cost} MUSD（上限 {cost_ceil} MUSD）。どれほど優れた設計エージェントでも両方は満たせない。"
        "本リポジトリ自身の階層 — ミッションが最優先で、設計要求はその下で改訂できる — に従えば、"
        "動かすべきなのは予算のほうである。</p>"
    ),
    "key3": (
        "<p><b>3. 出荷時のルール設計器は、出発点でゲインゼロの軸を動かしている。</b>"
        "ステップ大きさの {action_share} を action 部分空間に、{capacity_share} を capacity 部分空間に置く。"
        "出荷時の動作点では action / policy のすべての軸のゲインが正確にゼロで、20 倍まで掃引しても"
        "生存乗員は変わらない。すべての連鎖は <i>saturating</i>（飽和）原型に落ちる。"
        "ループは定常に動き（転回余弦 {cosine}、つまり完全な直進）、結果は一度も変わらない。</p>"
    ),
    "h_method": "方法とデータ",
    "method_p1": (
        "各実行は乗員 50 名・24 時間ミッションの 72 ステップ <code>plant_sim</code> で、文書化された CLI から駆動する。"
        "設計は <code>capacity_profile</code> 提案を書いて <code>--apply-proposals</code> に渡すことで課す。"
        "これは tool-use 設計器が候補を採用するのと同じ経路なので、実験グリッドとエージェント自身の提案は"
        "同一のコードを通る。"
    ),
    "method_p2": (
        "この経路を使う帰結を一つ書いておく。グリッドが測っているものの形が決まるからである。"
        "容量変更を適用すると <code>sync_action_payloads</code> も走り、乗員の要求を新しいハードウェアが"
        "応えられる量まで引き上げる。したがって応答面上の各点は、古い手順のまま動く新ハードウェアではなく"
        "<i>正しく運用された</i> ステーションである。サイジングの比較として正しく、設計エージェントが実際に"
        "出荷するものでもある。一方、一変数掃引は意図的に同期せず、ペイロード軸を単独で切り出す。"
    ),
    "method_figures_note": (
        "図中の軸ラベルは単位と ρ を保つため英語のままである。図の題とキャプションは日本語。"
    ),
    "th_dataset": "データセット",
    "th_runs": "実行数",
    "th_varies": "変化させるもの",
    "th_answers": "答える問い",
    "datasets": [
        ["seed 再現", "--seed のみ", "プラントは確率的か"],
        ["応答面", "ARS × OGS 定格", "相図、臨界性、生存のコスト"],
        ["一変数掃引", "一軸、出荷時の点", "ループ出発点での可制御性"],
        ["一変数掃引（緩和）", "一軸、OGS を 42 kg/day", "O₂ が律速でなくなったあとの可制御性"],
        ["乗員スケール", "乗員数、ステーション固定", "崩壊検定の分母側"],
        ["等方レイ", "全容量を共通倍率", "崩壊検定の分子側"],
        ["設計連鎖", "--iterate の長さ", "実際に回っている閉ループ"],
    ],
    "h_uncertainty": "不確かさの所在",
    "p_uncertainty": (
        "同一構成を {n_seeds} 個の異なるシードで再生すると結果は完全に一致する。"
        "評価スコアのシード間ばらつきは {score_spread}、生存乗員は {crew_spread}。"
        "ルールベースの actor / designer ではパイプライン全体が決定的なので、再現ノイズを"
        "ブートストラップする対象がない。本レポートの区間はすべて設計点とシナリオ条件にまたがって"
        "取っており、変動が本当に住んでいる場所である。確率性は LLM 設計器を通して初めて入り、"
        "それには本解析が持たなかったプロバイダが必要になる。"
    ),
    "fig_mass_title": "すべての実行で保存則が成り立つ",
    "fig_mass_caption": (
        "物理ゲートは監査対象の状態とは独立に各質量台帳を再計算し、{total} 件中 {passed} 件で通過した。"
        "残差は恒等的にゼロであり、以下の結果はシミュレータの漏れの産物ではない。"
    ),
    "h_order": "順序変数とその転移",
    "p_order": (
        "三つのサイジング変数は単位が異なり、ベースラインも桁が違うため直接比較できない。"
        "それぞれを同じ量に対する乗員の日需要で割ると、単位点が物理的に意味を持つ無次元のカバレッジ比 ρ になる。"
        "ρ = 1 は定常状態で乗員をまかなえる最小のステーションである。"
        "リービッヒの最小律は、律速カバレッジ "
        "ρ<sub>min</sub> = min(ρ<sub>ARS</sub>, ρ<sub>OGS</sub>, ρ<sub>WRS</sub>) を"
        "単一のスカラー順序変数として示唆する。"
        "出荷時ステーションは ρ<sub>ARS</sub> = 0.087、ρ<sub>OGS</sub> = 0.220 に位置し、"
        "それぞれ 11 倍・5 倍のアンダーサイズである。"
    ),
    "fig_phase_title": "生存の相図",
    "fig_phase_caption": (
        "居住可能な領域は O₂ 軸で頭打ちになり、CO₂ 軸では ρ = 1 よりかなり下で入る。"
        "生存規則が瞬間除去量ではなく貯蔵 CO₂ を見ているためである。"
    ),
    "fig_crit_title": "順序変数と感受率",
    "fig_crit_caption": (
        "プラントは決定的なので、感受率は応答の微分であり、再現にわたる分散ではない。"
        "ピークが臨界カバレッジを示す。"
    ),
    "th_crit_axis": "軸",
    "th_rho_star": "臨界カバレッジ ρ*",
    "th_width": "転移幅",
    "th_peak": "感受率のピーク",
    "th_r2": "R²",
    "profile_names": {
        "ARS (CO2 removal)": "ARS（CO₂ 除去）",
        "OGS (O2 generation)": "OGS（O₂ 生成）",
        "crew scaling": "乗員人数スケール",
    },
    "h_collapse": "カバレッジ比の反証テスト",
    "p_collapse": (
        "ρ が本当に順序変数なら、乗員を半減することとハードウェアを倍にすることは同じ介入である。"
        "どちらも ρ を倍にするからである。二つの掃引は実行を共有せず、物理的に無関係な量を操作する。"
        "最悪で乗員比 {max_abs}、{n_paired} 組の平均で {mean_abs}、相関 {corr} で一致する。"
        "残差の差は本物で系統的である。同じ ρ では少人数のほうがわずかに良く、"
        "操作あたりのバッチサイズが固定だと少人数を比例して長く支えられるためである。"
    ),
    "fig_collapse_title": "独立な二つの掃引が一本の曲線に潰れる",
    "fig_collapse_caption": (
        "ハードウェアを足すことと人を減らすことは異なる物理行為だが、動かす無次元量は同じで、"
        "応答はその行為ではなくその量に従う。"
    ),
    "h_steer": "ループが操れるものと、実際に操っているもの",
    "fig_ctrl_title": "アクチュエーションに対する可制御性",
    "fig_ctrl_caption": (
        "ループの出発点で結果を動かす軸は一つだけで、出荷時設計器はそれに触れない。"
    ),
    "p_span": (
        "出荷時の動作点で、action 部分空間のすべての軸を {n_mult} 個の倍率"
        "（{lo}× から {hi}×）で掃引すると、異なる結果はちょうど {n_out}{plural} 通りになる: {outcomes}。"
        "機構は運用ログに見える。"
    ),
    "fig_sat_title": "要求ペイロードが O₂ に効かない理由",
    "fig_sat_caption": (
        "プラントは要求と定格の小さいほうを供給し、それを limited_by に書く。"
        "定格を超えた分は到着時点で捨てられる。"
        "上で測ったゼロゲインの機構であり、推論ではなくプラント自身のリミッタ欄から読める。"
    ),
    "h_state_dep": "可制御性は状態に依存する",
    "th_subspace": "部分空間",
    "th_gain_shipped": "出荷点でのゲイン",
    "th_gain_relieved": "O₂ 緩和後のゲイン",
    "p_state_dep": (
        "強調行が重要である。ループ出発点ではゲインゼロだが、酸素飢餓を解くと実質ゲインが出る。"
        "出荷時設計器の好みの軸は一般に無用なのではなく、<i>別のサブシステムを先に直すまで</i>無用なのである。"
        "それを診断するにはどの制約が律速かを推論する必要があり、ルール設計器の固定乗法ポリシーには"
        "その機構がない。単一動作点の一変数感度は「死んだ軸」と結論しただろう。"
        "二つの場合を分けるのは第二の掃引である。"
    ),
    "h_rugged": "景観は単調ではない",
    "p_rugged": (
        "ARS 軸に沿って、グリッド遷移 {transitions} のうち {descents}（{rate}）は容量が増えているのに"
        "結果が<i>下がる</i>。最悪の単一段差は乗員比 {worst}。"
        "ハードウェア追加が命を奪い得るのは、運用がビジーガードに対してスケジュールされるからである。"
        "大きなバッチはサブシステムを長く占有し、次のバッチが必要だった窓を逃し得る。"
        "ステップあたり一評価を信じて貪欲に登る設計器は、これらの反転で押し戻される。"
        "これはステップを大きくする論拠ではなく、tool-use 設計器が行う多候補再シミュレーションの論拠である。"
    ),
    "h_loop": "閉ループを軌道として見る",
    "fig_loop_title": "設計連鎖の順序変数",
    "fig_loop_caption": (
        "変位は線形に増え、ステップサイズは減衰せず、転回角は +1 に固定され、結果は平坦である。"
        "探索ではなく開ループの行進である。"
    ),
    "fig_arch_title": "軌道の原型",
    "fig_arch_caption": (
        "「何も提案しなかった」と「効かない何かを提案した」を分けることが重要である。"
        "結果のプロットでは同一に見え、必要な対処は正反対だからである。"
    ),
    "th_chain": "連鎖",
    "th_iterations": "反復",
    "th_archetype": "原型",
    "th_displacement": "変位",
    "th_dsurvival": "Δ 生存",
    "th_cap_share": "capacity 割合",
    "th_act_share": "action 割合",
    "th_discarded": "棄却された提案",
    "p_discarded": (
        "さらに提案の {rate} はシミュレーションに到達しない。"
        "連鎖は検証要求を反復間で凍結するため、<code>applied_proposals.json</code> からすべての "
        "<code>set_parameter</code> 変更を取り除く。設計器が合格閾値自身を動かせばプラントを変えずに"
        "成功を宣言できるので、これは正しく意図された安全策である。"
        "しかし設計器には伝わらないため、毎反復で同一の閾値変更を再提案し、五枠中二枠を"
        "構造上棄却される手に使う。"
    ),
    "h_tcl": "最初の乗員損失までの時間",
    "log_rank": "ログランク χ²(1) = {stat}、p = {p}。",
    "fig_surv_title": "カバレッジ領域別の生存曲線",
    "fig_surv_caption": (
        "カバレッジ半分の上下の設計は直後に分かれ、二度と交わらない。"
        "打ち切りはスコアカード自身の right_censored から取り、補完しない。"
    ),
    "h_predictive": "コンパクトな予測則",
    "p_predictive": (
        "以下の比較は集団力学モデルで使われる構造に従う。自明なベースライン、単変数モデル、"
        "物理が示唆する構造化モデルである。それぞれグリッドの無作為な半分（{n_train} 設計）でフィットし、"
        "残りの半分（{n_test}）で採点する。柔軟なモデルが曲面を暗記して勝つことを防ぐためである。"
        "結果が 0 と 1 に強く飽和するため、R² に加えて balanced accuracy を併記する。"
        "単純正答率は定数予測器を過大評価する。"
    ),
    "th_model": "モデル",
    "th_heldout_r2": "ホールドアウト R²",
    "th_rmse": "RMSE",
    "th_ba": "balanced accuracy",
    "th_assumes": "仮定",
    "model_notes": {
        "the training mean; the floor any real model must clear":
            "訓練平均。実在モデルが超えねばならない床",
        "one logistic in the CO2 coverage, O2 ignored":
            "CO₂ カバレッジのロジスティック一つ。O₂ は無視",
        "one logistic in the O2 coverage, CO2 ignored":
            "O₂ カバレッジのロジスティック一つ。CO₂ は無視",
        "logistic in min(rho_ARS, rho_OGS): the law of the minimum as usually stated":
            "min(ρ_ARS, ρ_OGS) のロジスティック。通例の最小律",
        "the same law after dividing each coverage by its own critical value":
            "各カバレッジを自身の臨界値で割ったあとの同じ法則",
        "the two subsystems in series, survival as the product of their responses":
            "二つのサブシステムを直列。生存は応答の積",
        "the binding subsystem sets the outcome: min of the two responses":
            "律速サブシステムが結果を決める。二つの応答の min",
    },
    "p_predictive_result": (
        "通例どおり述べた最小律はここでは<i>弱い</i>。ホールドアウト R² は {naive} で、"
        "CO₂ 軸を無視するほうがましである（{ogs_only}）。"
        "二つのサブシステムは同じカバレッジで臨界にならないからである。"
        "ARS の転移は ρ* = {star_ars}、OGS の転移は ρ* = {star_ogs}。"
        "生の最小を取ると、数値的に小さいカバレッジのほうが閾値が低い場合に誤ったボトルネックを名指し、"
        "このグリッドではそれが大半のセルである。"
        "先に各カバレッジを自身の臨界値でリスケールすると {margin} まで戻り、"
        "入力ではなくフィットした二つの<i>応答</i>の最小を取るとホールドアウトで {response} に達する。"
        "ロジスティック二つ、パラメータ四つ、最小一つで 121 点の応答面を再現する。"
        "効く量は生のカバレッジではなく、各サブシステムが自身の閾値に対して持つ余裕である。"
    ),
    "fig_pred_title": "観測生存対予測生存",
    "fig_pred_caption": (
        "二つのカバレッジ比のロジスティックを最小律で結合すると、121 点の応答面を再現する。"
    ),
    "h_cost": "乗員を生かすコスト",
    "fig_pareto_title": "ステーションフットプリントに対する生存",
    "fig_pareto_caption": (
        "実行可能箱と生存集合は交わらない。これは要求の性質であり、その中を探索するエージェントの性質ではない。"
    ),
    "p_cost": (
        "グリッド上で乗員 50 名を全員生かす最も軽いステーションは、ARS を {ars} kg/day、"
        "OGS を {ogs} kg/day とし、ρ<sub>ARS</sub> = {rho_ars}、ρ<sub>OGS</sub> = {rho_ogs} に達する。"
        "質量 {mass} kg、費用 {cost} MUSD、体積 {volume} m³ に対し、上限は {mass_ceil} kg、"
        "{cost_ceil} MUSD、{vol_ceil} m³。三つとも破る。"
    ),
    "h_implies": "設計エージェントへの含意",
    "imp1_title": "実行不能は失敗ではなく結果として報告する。",
    "imp1": (
        "連鎖は現在 <code>NOT_IMPROVED</code> で終わり、エージェントの力不足に読める。"
        "測られた状況はミッションと予算を同時に満たせないということであり、正直な出力は、"
        "最も安い生存設計を証拠として添えた予算改訂の要求である。"
    ),
    "imp2_title": "律速制約に提案を駆動させる。",
    "imp2": (
        "プラントはすでに毎操作で <code>limited_by</code> と <code>fully_satisfied</code> を報告し、"
        "律速サブシステムを正確に指す。それを読む設計器なら、バックエンドが捨てる要求を"
        "六回拡大したりはしない。"
    ),
    "imp3_title": "棄却された内容を設計器に伝える。",
    "imp3": (
        "要求を凍結するのは正しい。提案を黙って落とすことが再提案を生む。"
        "フィルタした変更をエコーすれば、五枠中二枠が即座に空く。"
    ),
    "imp4_title": "貪欲に登らない。",
    "imp4": (
        "ARS 軸に沿った容量増加の {rate} は結果を悪化させるため、単一評価の山登りはここでは信頼できない。"
        "tool-use 設計器の多候補再シミュレーションが、答えの正しい形である。"
    ),
    "imp5_title": "カバレッジを直接計測する。",
    "imp5": (
        "ρ は実行前に config から計算でき、結果を R² = {r2} で予測する。"
        "スコアカードに出せば、本解析の大部分は飛行前の一つの数になる。"
    ),
    "h_limits": "本解析の限界",
    "lim1": (
        "エージェントの両側とも <code>labeled_rule_base</code> である。LLM プロバイダに到達できなかったため、"
        "<code>capacity_profile</code> 変更を<i>出せる</i> tool-use 設計器は一度も動かしていない。"
        "可制御性と相図の結果はプラントを特徴づけるので任意の設計器に当てはまる。"
        "ループ力学の結果はルール設計器に固有である。"
    ),
    "lim2": (
        "すべての実行が <code>plant_sim</code> バックエンドである。<code>mock</code> は生存・スコアカードを出さず、"
        "<code>ros2</code> には SSOS Docker が必要である。"
    ),
    "lim3": (
        "スイープでは障害注入を切り、カバレッジだけが変わるようにしている。"
        "連鎖は出荷時デフォルトのまま（有効）である。"
    ),
    "lim4": (
        "グリッドは二軸 {n} 点で WRS を固定している。実測ゲインがゼロで、ベースラインカバレッジが 6.4 であることが根拠である。"
        "より細かいグリッドは臨界カバレッジの推定を鋭くするが、定性的結論は動きにくい。"
    ),
}


def strings_for(lang: str) -> Mapping[str, Any]:
    """Return the copy dictionary for ``lang`` (``en`` or ``ja``)."""

    if lang == "ja":
        return _JA
    if lang == "en":
        return _EN
    raise ValueError(f"unsupported report language: {lang!r} (expected en or ja)")
