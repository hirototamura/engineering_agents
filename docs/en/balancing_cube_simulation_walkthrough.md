# Reading the self-balancing-cube experiment

Code and saved-evidence audit, 20 October 2026. This guide does not change a
requirement, score, controller, simulation or historical result. It distinguishes
the current runnable configuration, the configurations used in saved experiments,
and future improvements.

The project is a first step toward spacecraft engineering: build a bounded
physical system whose dynamics, control, experiment design and evidence can be
understood, then test whether an engineering agent can improve it responsibly.
The cube is a useful reaction-wheel control and engineering-process testbed.
It is not a dynamically equivalent model of a free-flying spacecraft.

## 1. Three systems that should not be confused

**Mission:** balance the real cube on any of its eight corners. **Current
development problem:** release a modeled cube near corner-000 equilibrium,
reject a short disturbance, and remain within numerical gates for six seconds.
**Agent problem:** propose a small permitted hardware/control change, test it,
retain the measured result, and use that evidence in the next proposal.

There are also three different meanings of “current model”:

These roles are now managed as CM-01, CM-02 and CM-03 in the One-Piece configuration catalogue. A separate CM-04 BOM reference was assessed on 21 October with no design iterations. See [the fixed BOM workflow](cube_bom_reference.md) and the [interactive catalogue and results](</Users/hiroto/Documents/ChatGPT/Engineering Agents/reports/cube-configuration-catalogue/index.html>).

- The blog displays the human-reviewed requirements/allocation model
  `reviewed-20261019-1`: 22 obligations, seven groups, 37 parameters, eight
  functions and ten components. Review approves wording and responsibility;
  it does not establish that the hardware passed.
- The runnable Engineering Agents scenario currently pins
  `cube.simulation.snapshot@bottom-corner-000-20261017-3`. It uses lower faces,
  approximate floor contact and the saved controller from the earlier MASS trial.
- The completed multi-agent study used `fixed-dt-mvp-2`, with upper wheels and
  the original requirement revisions. Changing the blog view did not rerun it.

The lower-wheel study was a human-directed model change, with zero LLM proposal
rounds. Its native MuJoCo exploration and validation each passed 12/12 cases.
Its full twelve-case MJX score has not been measured. There has not yet been a
completed lower-wheel multi-agent search matching the earlier study.

The standalone simulator is another entry point: its nominal lower-wheel
configuration is 180 mm, has an ideal pivot and rebuilds LQR. It is useful for
watching a cube, but it does not reproduce the exact contact-based agent run.

## 2. Where to look first

These links point to the actual local files used by this audit. The first file
to open is the **compiled configuration**, because the effective experiment is
assembled from several versioned inputs.

- [Current scenario dispatch](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/scenario.yaml:1>): snapshot selection, backend, LLM defaults and iteration limits.
- [Saved lower-wheel compiled configuration](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/bottom000-first-trial-20261017/candidates/candidate-001/compiled.json>): exact derived mechanics, actuator/contact/sensor configuration, saved `controller.K`, input digest and campaign ID.
- [Saved frozen snapshot](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/bottom000-first-trial-20261017/frozen-snapshot.json>): source revisions, requirements, KDPs, design bounds, cases and evaluation contract.
- [Exploration result](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/bottom000-first-trial-20261017/candidates/candidate-001/result.json>): twelve per-case summaries, gate decisions, sampled rows and pose frames.
- [Validation result](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/bottom000-first-trial-20261017/validation/result.json>): changed release/disturbance/seed conditions after selection.
- [Run summary](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/bottom000-first-trial-20261017/summary.json>): completion, stopping reason, best candidate and validation status.
- [Canonical lower-wheel snapshot records](</Users/hiroto/Documents/ChatGPT/Engineering Agents/one-piece/projects/balancing-cube/store/commits/56082d05ed0cfceec3467471bece01a915559a1fd59197ec1da4f8e5623139c2/records.json>): One-Piece source of truth.
- [Reviewed model records](</Users/hiroto/Documents/ChatGPT/Engineering Agents/one-piece/projects/balancing-cube/store/commits/a9ba4933a54b413437f8487b847f8ff4e7e26c79292cc3ce79457307197ac6dd/records.json>): current human-reviewed requirements and allocation baseline.

`scenario.yaml` is not the complete physics configuration. Normal dispatch
requires `ssot.path`; the One-Piece bridge resolves exact references, merges the
comparison design's mechanical properties and resolves the declared controller
design plant. In particular, the nominal 180 mm model is not the actual
166.235 mm comparison design. Run-specific overrides also replace YAML defaults:
the default `ollama/llama3.2` entry is not the model used in the saved Qwen study.

Read the executable resolution in
[scenario_run.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/scenario_run.py:19>) and
[MechanicalBridge](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/integrations/one_piece/mechanical_bridge.py:34>).

## 3. What makes the cube difficult?

Imagine a broom standing on its end. A small tilt moves its center of mass
away from directly above the support. Gravity then increases the tilt.
The cube has the same unstable equilibrium, but its actuators are internal
spinning wheels rather than a hand that can move the support.

The body frame starts at corner 000. At equilibrium its body diagonal
`(1,1,1)/sqrt(3)` points upward. Three orthogonal wheels spin about body x, y
and z axes. Lower mounting means centers near the three faces adjoining
corner 000. Those positions are fixed to the body; they do not follow the
contacting corner when the cube turns.

An illustrative one-axis, ideal-support equation is

\[
I_p\ddot\theta \simeq mgh\theta-\tau_w+\tau_d.
\]

Here `theta` is small tilt in radians, `I_p` is inertia about the support,
`m` is total mass, `h` is support-to-COM height, `tau_w` is the wheel-generated
correcting reaction torque, and `tau_d` is external disturbance torque.
The positive `mgh theta` term is destabilizing. Lowering the center of mass
reduces that term, but changes `I_p` too. Lower wheels do not make the cube
passively stable, and the effect on delayed, saturated feedback needs testing.

For the saved comparison mechanics:

- Side length: **166.235 mm**; total modeled mass: **0.704881 kg**.
- Modeled COM height: upper **156.455 mm**, lower **131.474 mm**.
- Gravity slope `mgh`: upper **1.08186**, lower **0.90912 N m/rad**.
- Gravity torque at 5 degrees: approximately **0.09429** versus **0.07924 N m**.

These are derived model quantities, not measured hardware properties. The
one-axis gravity torque should not be compared directly to one motor's rating:
the three actuator torques must be projected onto the requested correction
axis, and their available torque depends on wheel speed.

For the free body, a more useful angular-momentum description is

\[
J\dot\Omega+\Omega\times(J\Omega+A h)+A\dot h=\tau_{external},
\qquad h_i=J_{w,i}\dot\phi_i.
\]

This is an explanatory rigid-body/wheel approximation, not the literal contact
solver implementation. `A` maps wheel axes to body axes; accelerating a wheel
changes its momentum and applies the opposite torque to the body. A wheel
spinning at constant speed is not continuously producing control torque.
MuJoCo integrates the full multibody/contact model, including translation.

The saved wheel inertia is **7.98898e-5 kg m²**. At the 200 rad/s speed cap
(about 1,910 rpm), each wheel stores about **0.01598 N m s**. A 0.04 N m
disturbance lasting 0.24 s delivers **0.0096 N m s** in that world-axis
direction. The axes differ, but the comparison shows that finite momentum
capacity is already relevant. Increasing wheel inertia gives more momentum
storage at a given speed, while also changing mass, packaging and body inertia.

For a spacecraft, wheel momentum storage and torque limits remain relevant.
However, a free-flying spacecraft has no supporting floor and no unstable
upright equilibrium from this contact/gravity geometry. Wheel momentum
unloading requires external torque, for example from magnetic torquers or
thrusters. Transfer the angular-momentum reasoning, control discipline and
evidence process; do not transfer cube contact performance as spacecraft
performance. See [NASA's GNC overview](https://www.nasa.gov/smallsat-institute/sst-soa/guidance-navigation-and-control/).

## 4. What the numerical model includes

The agent experiment uses a six-degree-of-freedom body plus three wheel angles:
**nine velocity DOFs**, with ten position coordinates because orientation is
represented by a four-component quaternion. Eight massless spherical corner
geometries contact a plane. Decorative frame and wheel geometry does not
provide full CAD collision checking. The model is rigid; structural bending,
fasteners, bearings and wheel imbalance are not resolved.

Contact uses an assumed 4 mm corner radius, sliding friction 0.7, and zero
torsional/rolling friction at the reference condition. Solver compliance is
not calibrated material stiffness. The current model requires symmetric
frame COM on the body diagonal. Fixed motor, battery, electronics and driver
mass are lumped into the frame. The lower-wheel change moves the modeled
rotating wheel/rotor bodies, not all motor mass.

The separate ideal-pivot model has a ball joint at the vertex. It is used for
controller design and diagnostics; a mechanical joint prevents contact loss
and slip, so it should not be mistaken for the floor-contact test.

Sources: [model.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/environment/mujoco/model.py:28>),
[contact.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/environment/mujoco/contact.py:29>) and
[MuJoCo's equations and contact formulation](https://mujoco.readthedocs.io/en/latest/computation.html).

### The fast feedback loop

The physics step is **1 ms**; control updates every **15 ms**, or about
66.7 Hz. One six-second case has 6,000 physics steps and 400 control intervals,
normally yielding 401 sampled observations. The LLM does not run in this loop.

The controller is a discrete linear quadratic regulator (LQR). Its state is

\[
x=[\theta_x,\theta_y,\omega_x,\omega_y,h_x,h_y]^T,
\qquad u_{xy}=-Kx.
\]

The builder linearizes an ideal-pivot MuJoCo transition about equilibrium and
computes `K` from the discrete Riccati equation for the cost
`sum(x^T Q x + u^T R u)`. Separate yaw-rate damping uses
`-k_yaw omega_z`; there is no commanded yaw-angle tracking trajectory.
The target is near-zero tilt and angular rate, with momentum regulation.

The saved lower trial retains the MASS controller, with approximately per-axis
gains `[-8.014, -1.175, -15.702]` in the specified tilt/rate/momentum ordering,
and yaw gain **0.03 N m s**. Its Q scale factors are tilt **1.0**, rate
**1.0310625**, momentum **0.825**; R stays `[100,100]`.
These entries have different units: their numerical magnitudes should not
be compared as if they were equal kinds of gain.

The current lower snapshot deliberately retains an historical upper-face
controller design plant for subsequent Q changes. It does not silently
redesign against a lower-wheel contact model. Ideal linear closed-loop
eigenvalues alone do not establish contact-model stability with delay and
saturation. The saved `K`, rather than a claim in an old hypothesis string,
is the execution evidence.

Sources: [control.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/environment/mujoco/control.py:8>),
[compile_controller](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/design.py:82>) and
[SciPy's discrete Riccati solver](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.solve_discrete_are.html).

### Sensing and actuation are approximations

The controller receives true simulated tilt/angular rate with Gaussian noise
and timestamp delay: tilt standard deviation **0.05 degrees**, gyro standard
deviation **0.2 degrees/s**, delay usually **15 ms**, increased to **30 ms**
in one stress domain. Encoder values and some coordinate transforms remain
ideal. There is no implemented accelerometer/magnetometer model, calibration,
bias drift, complementary filter or extended Kalman attitude estimator in
this loop. Calling it an implemented MPU6050 attitude-estimation pipeline
would overstate the model.

The motor model clips applied torque with the symmetric assumed envelope

\[
|\tau_i|\le\tau_{peak}\max(0,1-|\dot\phi_i|/\omega_{no-load}).
\]

For the saved BLDC family, peak torque is **0.0834 N m**, no-load speed is
**702.67 rad/s**, and the speed governor prevents accelerating further at
**200 rad/s**. The envelope is applied at each physics step while the most
recent controller request is held. No battery voltage sag, PWM/current loop,
regenerative braking or thermal dynamics are simulated. Continuous-torque
threshold exceedance is a proxy, and absolute mechanical work is not battery
energy.

Source: [sensor and torque pipeline](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/environment/mujoco/contact.py:127>).

## 5. A file-reading exercise

Start with the saved lower trial's `validation/result.json` and find the record
with `domain_id=heavy-delay-prior-confirm`, `condition_id=confirm-b`, `seed=812`.
Read its `summary`, then `screening`, then `rows` and `frames`.

The native replay in the blog compares the prior upper-wheel response with the
lower-wheel response under the same saved controller. In this known case,
peak tilt changes from about **3.260 degrees to 2.163 degrees**, and speed
governor fraction changes from **1.8% to 0.4%**, crossing the 1% gate. Both
episodes run six seconds. This is useful evidence about a known failure; it
is not a fresh independent discovery or proof of general improvement.

Next open the complete twelve-case aggregates. The lower geometry passes
12/12 exploration cases but its native scalar score is **0.988586**, below
the upper design's **0.991612**. This is not contradictory: a particular
failure can improve while average final-second tilt gets worse. An engineering
decision needs both facts.

The interactive companion uses the **saved lower validation** records, not
newly simulated or interpolated responses. Its charts are a way to inspect
what the solver actually produced. Their source is the linked result JSON.


## 6. Read the score as an engineering argument

The current score asks a narrow question: **How well does a fixed configuration complete twelve six-second numerical cases, stay inside the numerical screening limits, and settle near upright?** It does not measure the probability that a manufactured cube will work. It does not measure progress toward a complete spacecraft. It also does not represent the percentage of the reviewed requirements that have been verified.

For one candidate, the implemented objective is

\[
J=\frac{k}{12}-0.05\,\overline{e_{\mathrm{RMS}}}-0.2\,\overline{f_{\tau}},
\]

where \(k\) is the number of cases that pass **every** gate, \(e_{\mathrm{RMS}}\) is final-one-second total-tilt RMS in degrees, and \(f_\tau\) is the fraction of integrated physics steps at which at least one wheel exceeds its continuous-torque comparison threshold. Bars mean an arithmetic average over all twelve cases, including failed cases. The coefficients carry the normalization needed for the chosen units; they are frozen numerical development weights, not values derived from a physical success model.

The exact implementation is [aggregate](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/evaluation.py:92>). The weights and gates come from the run's frozen input under `plan.objective` and `contract.screening`, for example [the multi-agent run snapshot](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/mass-inspired-cube10-20261017t060309z-context-v3/multi_agent/frozen-snapshot.json>).

### What makes one case pass?

A case must complete the required **6 seconds**, report `completed`, and satisfy every following limit:

- Peak total tilt: **≤5 degrees**.
- Total-tilt RMS during the final one second: **≤2 degrees**.
- Contact fraction: **≥0.99**.
- Peak horizontal displacement: **≤2 millimetres**.
- Peak slip speed: **≤0.05 metres/second**.
- Continuous-torque comparison threshold exceeded: **≤10% of physics steps**.
- Speed governor active: **≤1% of physics steps**.

[Screening](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/evaluation.py:7>) applies those rules deterministically. Missing or nonfinite numeric measurements cannot pass their numeric gates. Matrix aggregation also rejects duplicate or missing case identities.

Execution limits and pass limits serve different purposes. The current model terminates after tilt exceeds **20 degrees**, horizontal drift exceeds **30 millimetres**, contact is continuously lost for **0.1 seconds**, or slip continuously exceeds **0.05 metres/second** for **0.15 seconds**. Therefore, `completed` can coexist with a screening failure. A cube can remain within the simulator's emergency bounds for six seconds while exceeding the tighter five-degree or two-millimetre acceptance gates. These are numerical development limits; they are separate from the reviewed hardware requirements.

### What exactly is averaged or counted?

At a **15-millisecond control tick**, the runner records a pose and other observations. Final-second RMS is

\[
e_{\mathrm{RMS}}=\sqrt{\frac{1}{N}\sum_{i=1}^{N}\theta_i^2}.
\]

Here \(\theta_i\) is total tilt, not an error averaged separately over two axes. The final window includes samples whose time is at least the episode's end time minus one second. For an early failed episode, that means the last second *before failure*. The independent completion gate prevents that short episode from being called a successful six-second test.

Peak tilt, slip, displacement, wheel speed, and motor torque are calculated from sampled rows. Contact fraction is the proportion of post-initial control-tick samples with normal force above **0.0001 newtons**. It is not a direct measurement of real contact reliability.

Drive counters instead run at each **1-millisecond physics step**. With an uninterrupted six-second episode, their denominator is approximately **6,000 integrated steps**. At each step, a counter is incremented once if **any one of the three wheels** triggers the condition. The fraction is not divided by three and is not an average over wheel-time. A roughly one-second final RMS window contains approximately 67 control samples; exact endpoint inclusion follows saved timestamps.

The continuous-torque fraction counts applied torque above a configured comparison threshold. It is **not a temperature prediction**. The governor fraction records occasions when a wheel has reached its speed limit and a nonzero permitted command would accelerate it farther in the same direction. The runner then blocks that accelerating command. The uncalibrated torque-speed envelope already reduces available torque as speed increases. Neither fraction predicts electrical power, battery sag, driver heating, regenerative braking, or component life.

See [drive limiting](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/environment/mujoco/contact.py:157>), [physics-step counting](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/environment/mujoco/contact.py:260>), and [summary construction](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/environment/mujoco/contact.py:273>).

### Twelve cases are a small test matrix

Each evaluated design runs **3 domain priors × 2 releases × 2 noise seeds**. These are twelve episodes for one configuration, not twelve configurations.

The domain priors deliberately vary several assumptions together. Nominal uses frame mass ×1, sliding friction 0.7, a 4-mm corner radius, and 15-ms delay. Heavy/delay uses mass ×1.15, friction 0.4, an 8-mm radius, and 30-ms delay. Light/small-contact uses mass ×0.85, friction 0.9, a 2-mm radius, and 15-ms delay. These combinations are unmeasured priors, not a calibrated distribution of production hardware.

Exploration release A starts at tilt `[1.5, −1.0]` degrees and yaw rate 0.15 rad/s, then applies `[0.04, −0.02, 0]` N·m for 0.24 seconds starting at 3 seconds. Release B starts at `[−1.0, 1.5]` degrees and −0.1 rad/s, then applies `[−0.02, 0.04, 0]` N·m over the same interval. Seeds are **101 and 102**.

Selection validation uses different release and disturbance conditions, seeds **811 and 812**, and a heavy-domain mass factor of **1.173**. It is a public, integrity-checked matrix rather than an access-isolated secret holdout. Later fresh-seed audits supply additional evidence, but should not be confused with the original selection validation. [Trial construction](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/design.py:121>) shows exactly how this Cartesian product becomes simulator inputs.

### A real score decomposition—and a reporting distinction

The selected multi-agent configuration has a saved **GPU-parallel projection** with twelve passing cases, mean final-second RMS **0.1699230270 degrees**, and zero continuous-torque penalty:

\[
J=12/12-0.05(0.1699230270)-0.2(0)=0.9915038486.
\]

This is not a 99.15% success probability. Once all cases pass and the torque penalty is zero, tiny score differences reflect only small changes in average final-second tilt RMS.

The historical Engineering Agents loop actually selected this configuration using the **native MuJoCo summaries**, which produced **0.9916124707**. Its proposal feedback, memory, and best-design selection used that runtime score. The blog later recomputed the same formula from saved MJX summaries to show GPU-parallel progress. [Adapter result assembly](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/adapter.py:103>), [best-design selection](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/loop.py:354>), and [the blog projection](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/tools/research_story/recent.py:77>) make this distinction explicit. MJX has not yet replaced native summaries as the runtime's primary selection input.

The fresh GPU audit passed twelve cases with score **0.9914858776**. The lower-wheel trial passed twelve native exploration cases with score **0.9885861309**; its complete twelve-case GPU score remains unmeasured. Those two implementations' scores should not be silently mixed on a single progress curve.

### Where the current score is weak

One failed case costs **1/12 = 0.083333** before the continuous penalties. Reducing mean RMS by 0.1 degrees adds **0.005**. Reducing torque-threshold exceedance by one percentage point adds **0.002**. Thus, this scalarization equates one extra passing case with roughly **1.667 degrees** less mean RMS. That trade is an engineering policy choice, not a physical law.

The score has abrupt gate boundaries, averages away worst-case margins, and rewards final-second precision more directly than disturbance recovery. It omits direct objectives for yaw error, settling time, overshoot, sustained wheel-momentum headroom, manufacturing cost, electrical energy, and temperature. Those omissions matter when preparing hardware. Repeatedly optimizing twelve visible cases also invites overfitting. Twelve passes cannot establish real-world reliability, thirty-second holding, or all-eight-corner capability.

### Proposed scoring version 2—not implemented

Keep execution validity, requirement conformance, and optimization performance separate. First reject invalid evidence. Next decide mandatory numerical gates. Among acceptable designs, compare worst-case margins and then declared performance measures. A good scorecard would retain duration, whole-episode and settled tilt, disturbance recovery, yaw error, slip/drift, torque margin, wheel-speed and momentum margin, and variation across predeclared fresh inputs. Electrical and thermal fields should remain unknown until a suitable model or measurement exists.

Choose weights and priorities with engineering judgment, then freeze a new evaluation-contract revision. Re-evaluate matched baselines and candidates under that revision. Preserve the old scores and selections. Agent productivity—useful improvement per computing effort and human intervention—and ultimate successful-project counts/rates belong in separate project-level evaluation, not inside a physical control score.

## 7. What the engineering agents actually do

There are two different control loops. The inner physical controller commands reaction-wheel torque every 15 ms during a six-second trial. The outer engineering loop proposes a configuration, waits for complete trials, reads their measurements, and proposes the next experiment. Qwen participates in this second loop. It does not decide each motor command while the cube balances.

The cube’s outer loop is implemented in the scenario layer, chiefly [loop.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/loop.py:237>). Its optional team of specialists is [DesignWorkflow](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/workflow.py:98>). These are role-specific calls to the same model, rather than five independently trained models. The latest pilot served `qwen3.8-27b-uncensored`, with weight root `orcarouter/Qwen3.8-27B-Uncensored-FP8`, through vLLM at port 8001. Its recorded settings include temperature 0.3, a 32,768-token context window, and a 1,536-token thinking budget. The exact declaration is in the [study manifest](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/mass-inspired-cube10-20261017t060309z-context-v3/study-manifest.json>).

### Configuration, history and the current model are different things

Normal dispatch starts in [scenario_run.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/scenario_run.py:19>). It loads YAML and overrides, resolves a versioned One-Piece snapshot, constructs the LLM client, and enables memory and specialist coordination when requested. [scenario.yaml](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/scenario.yaml:1>) currently defaults to `bottom-corner-000-20261017-3`, native MuJoCo, and five design rounds. It requires an explicit One-Piece store path.

The October 17 multi-agent pilot instead used `fixed-dt-mvp-2`, the earlier upper-wheel model and its pinned requirement inputs. The blog’s newer `reviewed-20261019-1` model is a current reference view. It does not retrospectively change historical experiments. A future lower-wheel experiment needs its own explicit snapshot and run declaration. [MechanicalBridge](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/integrations/one_piece/mechanical_bridge.py:34>) checks store integrity and resolves exact record revisions, rather than taking whichever requirement happens to be newest midway through a campaign.

### One experiment, in chronological order

1. **Freeze the environment.** The adapter copies the snapshot and hashes physics, control and evaluation code. Repeated resets detect changes. It writes `frozen-snapshot.json`, `environment.json` and the initial search policy. The comparison design is simulated before new proposals. A failed reference execution prevents the proposal stage.
2. **Read the evidence.** Before each proposal, the loop flushes queued One-Piece records, checks that its frozen snapshot has not changed, and retrieves fresh context. The full record projection is saved as `round-NN/ssot-context.json`.
3. **Ask for an experiment.** `prompt-data.json` combines controlled requirements and parameters with allowed changes, recent feedback, retrieved memory, current incumbent, and an output schema. A single designer call or the specialist workflow returns one candidate JSON object.
4. **Compile the candidate.** Trusted Python validates the field names, motor family, finite numbers and bounds. It derives masses, inertias and actuator properties, then generates or exactly reuses the saved feedback matrix K. The LLM cannot supply arbitrary K, edit simulation code, change sensors, or lower pass thresholds.
5. **Execute and measure.** Python runs the declared case matrix, computes metrics and checks numerical gates. It saves `candidates/candidate-NNN/compiled.json` and `result.json`, creates design/evaluation records, and appends a memory episode.
6. **Learn from the result.** After records are saved and reread, an optional optimizer proposes the next workflow settings. A deterministic policy update also adjusts search emphasis. The next proposal starts only after these steps finish.

This stage sequence is recorded as EN, PI, R, E. The executable sequence and persistence points are visible in [loop.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/loop.py:371>). If both mechanics and controller change, the program evaluates the four combinations of old/new mechanics and old/new controller. That comparison is anchored to the run’s frozen reference, not automatically the last proposed design. Repeated compiled inputs reuse exact saved evaluations, so one round is not necessarily one new simulation configuration.

### What the model can see—and what it cannot

The prompt retains requirement statements and revisions, acceptance criteria, approval state, KDP values and units, parameter origins and bounds, the comparison design, historical campaign summary, frozen execution conditions and the numerical objective. It contains a schema for six mechanical variables, motor family and four control settings. Recent feedback and the current incumbent connect these constraints to previous experiments. The [prompt projection](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/loop.py:49>) is deliberate: the LLM does not read the HTML report or browse the complete store itself.

A consequential limitation is the fresh feedback interface. [adapter.feedback](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/adapter.py:130>) returns a scalar score, an all-pass flag, implementation-agreement status and **names** of failed metrics. It does not return the newly measured per-case values, score contributions, threshold margins, torque histories or trajectories. Those richer outputs exist in result files, but the next LLM request does not automatically contain them. Imported historical memory can retain richer result summaries. The agent’s explanation of a tiny score change can therefore exceed the evidence actually shown in its prompt.

Memory is an append-only, hash-chained [JSONL journal](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/memory.py:107>). Retrieval selects exact configuration matches, the highest measured score, recent episodes and diverse relevant failures, under a bounded prompt budget. It uses deterministic retrieval, not embeddings or a vector database. Measurements are separated from unverified LLM hypotheses. Saving an interpretation in memory does not make it a physical fact.

### How the specialist team works

The initial workflow asks mechanical and control specialists independently. A critic then challenges their proposals; a coordinator selects or revises one compiler-ready experiment. The mechanical lens concerns geometry, mass, inertia and motor limits. The control lens concerns feedback, delay and momentum headroom. The critic seeks duplicates, confounded changes and unsupported mechanisms. It does not decide numerical acceptance.

After measured results, a fifth call—the optimizer—may change routing, first specialist, evidence-handoff order and one focus label: speed headroom, delay robustness, tilt recovery or isolated changes. Routing can become sequential cross-review instead of blind parallel proposals. These are edits to bounded workflow data, not new executable tools or trained weights. [workflow.py](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/workflow.py:173>) specifies the role instructions and actual handoffs.

Each attempted full round permits four 4,096-token completions and one 2,048-token optimizer completion, with a 140,000-token aggregate prompt ceiling. Equal ceilings do not imply equal actual compute. Every request is reconstructed from structured context and earlier selected outputs; the single-designer comparison is also reconstructed this way, not an unlimited persistent conversation.

### A concrete example: multi-agent round six

Round six entered with sequential cross-review, control first, focused on speed headroom. The control specialist proposed reducing angular-rate Q scaling from `1.0560625` to `1.0310625`, holding tilt Q at `1.0`, momentum Q at `0.825`, yaw gain at `0.03`, and mechanics unchanged. It predicted less transient wheel-speed demand. The mechanical specialist instead proposed a thicker wheel. The critic returned an empty JSON object. The coordinator chose the control experiment and supplied the registered `bldc_ec45` family and complete configuration.

Python prefixed the candidate ID with `round-6-`, compiled the controller, classified it as `M0C1`, and evaluated it as [candidate-010](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/mass-inspired-cube10-20261017t060309z-context-v3/multi_agent/candidates/candidate-010/result.json>). All twelve exploration cases passed; the recorded score was `0.9916124707109835`. This became the retained incumbent. Results were persisted and reread before the workflow optimizer ran. Its prompts, answers and saved controller can be followed from the [round-six folder](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/mass-inspired-cube10-20261017t060309z-context-v3/multi_agent/round-06/proposal.json>).

Two cautions matter. First, the empty critique was accepted because intermediate role outputs need only parse as dictionaries; the final candidate compiler has stronger checks. Second, the mechanical draft claimed that increasing thickness, at fixed mass and radii, increases axial wheel inertia. The implemented annular inertia formula does not contain thickness in its axial term. This illustrates why hypotheses need explicit mechanics checks. Neither a plausible explanation nor a schema-valid answer is sufficient engineering evidence.

### Tool ownership, stopping rules and next improvements

The present model is a bounded proposer, not an autonomous tool-using engineer. The [vLLM request](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/core/llm/vllm.py:387>) has messages and generation settings, but no tool declarations. Python owns tool timing, compilation, simulation, judgment and publication. No LLM call occurs inside the 15 ms physical-control cycle.

Default limits are five rounds, twenty configurations, thirty minutes and three stagnant rounds. Explicit longer campaigns can use twenty rounds, eighty configurations and two hours. Invalid proposals, provider errors, incomplete simulations, timeouts, missing required execution, changed snapshots and unsent records remain visible. The final exploration-selected incumbent receives an independent validation matrix; passing simulation does not adopt a hardware baseline. See [stop and finalization logic](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/loop.py:635>).

The latest paired pilot attempted ten cycles per arm but completed eight full cycles each. Two rejected outputs per arm consumed attempts. Multi-agent execution measured fourteen configurations; the single-designer arm measured ten. The finalized study remains inconclusive as a ten-completed-cycle comparison. A useful next step is richer measured feedback: per-case metric values, score decomposition, margins and prediction-versus-outcome comparisons, together with stronger critique completeness checks. These are proposed improvements; they are not implemented by this guide.

### Source trail

The main executable sources are [dispatch](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/scenario_run.py:10>), [loop](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/loop.py:237>), [workflow](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/workflow.py:98>), [memory](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/memory.py:58>), and [compiler](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/scenario/balancing_cube/design.py:31>). Historical evidence is declared by the [study manifest](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/mass-inspired-cube10-20261017t060309z-context-v3/study-manifest.json>) and bounded by its [finalization record](</Users/hiroto/Documents/ChatGPT/Engineering Agents/engineering_agents/src/experiments/results/mass-inspired-cube10-20261017t060309z-context-v3/finalization.json>).

## 8. A constructive next experiment

Before adding a larger model or more agents, make the existing experiment
more informative. Freeze the lower-wheel snapshot and saved controller, declare
a new evaluation revision, and compare baseline and candidate on the same
predeclared cases. Provide the proposer a per-case scorecard and require one
mechanical/control hypothesis with a predicted measurable effect. Record
whether the effect occurred, not only whether the scalar improved.

First identify mass/inertia, torque-speed limits, sensing delay and contact
properties on hardware. Separate those measurements from design assumptions.
Extend six-second tests toward the reviewed holding duration, test new corners
and define how the fixed wheel arrangement can meet all-eight-corner behavior.
Neither automatic wheel relocation nor self-righting is implemented.

Keep three evaluation levels separate: the cube's physical performance; the
engineering process's useful improvement per time, cost and human intervention;
and Engineering Agents' eventual project-level success count and success rate.
This case study currently supplies evidence about the first two only within a
small simulation experiment. It has not measured the ultimate project-level KPIs.

No solver, score policy, prompt, requirement or historical record was changed
while preparing this guide. Proposed improvements above need an explicitly
versioned implementation and matched tests.
