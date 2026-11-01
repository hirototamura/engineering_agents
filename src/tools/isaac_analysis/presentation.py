"""Offline reading edition of the full, unchanged technical evidence.

The layout follows the balancing-cube research article. Numeric conclusions
come from the supplied summaries; prose and exact tables remain in the report.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path
import re


CHAPTERS = [
    (1, 'scope', 'The experiment', 'Exactly what was tested'),
    (8, 'results', 'Measured results', 'The larger cube passed fewer cases'),
    (9, 'trajectories', 'Eight-corner plots', 'Follow the tilt over six seconds'),
    (2, 'initial-conditions', 'Initial conditions', 'How each trial starts'),
    (3, 'mechanics', 'Mechanics', 'The cube, wheels and mass properties'),
    (4, 'controller', 'Controller & motors', 'What the controller commands'),
    (5, 'timing', 'Sensing & delays', 'What is delayed, noisy or ideal'),
    (6, 'physics', 'Physics & stopping', 'Contact, execution and termination'),
    (7, 'criteria', 'Screening criteria', 'The gates used to judge a trial'),
    (10, 'limitations', 'Limits of the evidence', 'What these simulations cannot establish'),
    (11, 'tools', 'Tools & filters', 'Select cases and reproduce the analysis'),
    (12, 'provenance', 'Exact source records', 'Resolved inputs and provenance'),
]


def inline(value):
    value = html.escape(value)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)


def body_blocks(markdown, output):
    """Render the generated Markdown subset without executing embedded HTML."""
    blocks = []
    code = in_table = False
    figure_count = 0
    for line in markdown.splitlines():
        if in_table and not line.startswith('|'):
            blocks.append('</tbody></table></div>')
            in_table = False
        if line.startswith('```'):
            blocks.append('</code></pre>' if code else '<pre><code>')
            code = not code
            continue
        if code:
            blocks.append(html.escape(line) + '\n')
            continue
        if line.startswith('!['):
            name = line.split('](', 1)[1][:-1]
            # Only the generated figure basenames may be read.
            if Path(name).name != name or not name.endswith('.png'):
                raise ValueError('Expected a local generated PNG basename')
            encoded = base64.b64encode((output / name).read_bytes()).decode()
            figure_count += 1
            comparison = name == 'paired-design-comparison.png'
            label = ('Both architectures · median and 95.5% coverage' if comparison else
                     name.split('-')[0].capitalize() + (' · all recorded motion' if '-all-recorded-' in name else ' · evaluation interval only'))
            explanation = ('Blue: reference. Orange: candidate. Each distribution is computed separately.' if comparison else
                           'Every selected case contributes at every timestamp, including free motion after the controller stops.' if '-all-recorded-' in name else
                           'Cases leave the bands after their stop. Later narrow bands describe survivors; read the remaining counts.')
            figure = (f'<figure><h3>{label}</h3><img alt="{html.escape(label)}: eight corner tilt plots" '
                          f'loading="lazy" src="data:image/png;base64,{encoded}"><figcaption>'
                          f'<strong>Figure {figure_count}.</strong> {explanation} '
                          'Time is in seconds; tilt is in degrees. Percentile bands describe the distribution across trials, '
                          'not uncertainty in the median or hardware performance.</figcaption></figure>')
            if figure_count > 1 and not comparison:
                figure = f'<details><summary>Show {label.lower()}</summary>{figure}</details>'
            blocks.append(figure)
            continue
        if line.startswith('|'):
            if not line.replace('|', '').replace('-', '').strip():
                blocks.append('</thead><tbody>')
                continue
            cells = line.strip('| ').split('|')
            if not in_table:
                blocks.append('<div class="table-scroll" role="region" aria-label="Detailed evidence table" tabindex="0"><table><thead>')
                in_table = True
                tag = 'th'
            else:
                tag = 'td'
            blocks.append('<tr>' + ''.join(f'<{tag}>' + inline(c.strip()) + f'</{tag}>' for c in cells) + '</tr>')
            continue
        if line:
            blocks.append('<p>' + inline(line) + '</p>')
    if in_table:
        blocks.append('</tbody></table></div>')
    return '\n'.join(blocks)


def render_report(markdown, output, summary, paired, groups):
    """Generate a self-contained article with every technical section retained."""
    output = Path(output)
    labels = list(groups)
    totals = {label: (sum(r['screening_passed'] for r in summary if r['campaign'] == label),
                      sum(r['cases'] for r in summary if r['campaign'] == label)) for label in labels}
    sections = {int(number): text for number, text in re.findall(r'^## (\d+)\. [^\n]+\n(.*?)(?=^## |\Z)', markdown, re.M | re.S)}
    if set(sections) != {row[0] for row in CHAPTERS}:
        raise ValueError('The reading edition requires all twelve technical sections')
    css = Path(__file__).with_name('reading.css').read_text()
    cards = []
    for j, label in enumerate(labels):
        passed, n = totals[label]
        f = groups[label]['factors']
        cards.append(f'<div class="result {"candidate" if j else "reference"}"><h3>{html.escape(label.capitalize())}</h3>'
                     f'<div class="score">{100 * passed / n:.2f}%</div><small>{passed:,} / {n:,} screening passes</small>'
                     f'<p>{f["side_m"] * 1000:.3f} mm side · {f["total_mass_kg"]:.4f} kg total mass</p></div>')
    regressed = sum(r['pass_to_fail'] for r in paired)
    improved = sum(r['fail_to_pass'] for r in paired)
    conclusion = (f'{regressed:,} paired cases changed from pass to fail; {improved:,} changed from fail to pass. '
                  'The larger design used the same saved controller. Geometry, mass and inertia changed together, so this comparison cannot isolate their separate effects.')
    rows = []
    for corner in sorted({r['corner'] for r in summary}):
        bars = []
        for j, label in enumerate(labels):
            r = next(r for r in summary if r['campaign'] == label and r['corner'] == corner)
            pct = 100 * r['pass_fraction']
            bars.append(f'<div class="bar {"candidate" if j else "reference"}"><span style="width:{pct:.3f}%"></span>'
                        f'<b>{pct:.1f}% · {r["screening_passed"]:,}/{r["cases"]:,}</b></div>')
        rows.append(f'<div class="corner-row"><code>{corner}</code>' + ''.join(bars) + '</div>')
    result_intro = ('<div class="result-grid">' + ''.join(cards) + '</div><p>' + conclusion + '</p>'
                    '<div class="legend"><span><i></i>Reference</span><span class="candidate"><i></i>Candidate</span></div>'
                    '<div class="corner-chart" aria-label="Screening pass fractions by corner">' + ''.join(rows) + '</div>')
    nav = ''.join(f'<a href="#{anchor}">{label}</a>' for _, anchor, label, _ in CHAPTERS)
    chapters = []
    for rank, (number, anchor, _, heading) in enumerate(CHAPTERS, 1):
        body = sections[number]
        # Start with a plain-language reading guide; retain the exact method.
        images = re.findall(r'^!\[.*$', body, re.M)
        if number == 9:
            body = re.sub(r'^!\[.*\n?', '', body, flags=re.M)
            rendered = ('<p>Each panel is one supported corner. The line is the median tilt; the shaded bands show how widely '
                        'the recorded trials spread at each instant. Darker bands contain the middle 68.3% of cases. '
                        'The palest band spans the full range. Every selected case contributes to the calculation.</p>'
                        '<p>The main view keeps motion after a controller stop, so failed cases stay visible. '
                        'Open an alternative view below to inspect the candidate or the surviving evaluation intervals. '
                        'These bands describe simulations, not confidence in real-world performance.</p>'
                        + body_blocks('\n'.join(images), output)
                        + '<details><summary>Exact percentile method, stopped-case policy and denominator audit</summary>'
                        + body_blocks(body, output) + '</details>')
        else:
            rendered = body_blocks(body, output)
        if number == 8:
            rendered = result_intro + '<details><summary>Exact per-corner counts, intervals and paired tests</summary>' + rendered + '</details>'
        if number == 12:
            rendered += '<p>The full source-catalog JSON and percentile CSV/JSON are included in the private analysis evidence pack. This HTML embeds every figure and needs no internet connection to read.</p>'
        chapters.append(f'<section id="{anchor}"><div class="section-no">{rank:02d} / Recorded evidence</div><h2>{heading}</h2>{rendered}</section>')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eight corners, two designs — Isaac cube technical report</title><style>{css}</style></head><body>
<a class="skip" href="#article">Skip to full report</a>
<header class="top"><a href="#">One-Piece / Engineering Agents</a><span>Isaac Sim · Monte Carlo evidence · 24 October 2026</span></header>
<div class="hero"><div class="eyebrow">Technical report / Existing campaign analysis</div>
<h1>Eight corners.<br>Two designs. One frozen controller.</h1>
<p class="subtitle">What 49,152 recorded cube trials tell us about balance, failure and the next engineering experiment.</p>
<p class="abstract">A self-balancing cube uses three internal reaction wheels to correct its tilt while standing on a corner. Here, two mechanical configurations face the same initial conditions and sensor-noise seeds on all eight corners. This report identifies exactly what was simulated and makes the failures visible alongside the successful cases.</p>
<p class="thesis"><strong>The larger cube performed worse under the saved controller.</strong> The experiment is useful evidence for the next design proposal. It does not establish physical balance or resolve the inconclusive MuJoCo–PhysX comparison.</p>
<div class="facts"><div><strong>49,152</strong>recorded episodes · two paired campaigns</div><div><strong>8</strong>corners · 3,072 cases each per design</div><div><strong>6 s</strong>duration · 401 recorded samples</div><div><strong>15 ms</strong>controller period and observation delay</div></div>
<div class="reading-map"><a href="#results"><b>What happened?</b><span>Pass rates, paired changes and all eight corners.</span></a><a href="#trajectories"><b>How did it move?</b><span>Time versus tilt, percentile bands and stopped cases.</span></a><a href="#initial-conditions"><b>What was tested?</b><span>Initial states, mechanics, gains, delays and physics.</span></a></div></div>
<div class="layout"><nav class="toc" aria-label="Report contents"><p>In this report</p>{nav}</nav><main class="article" id="article">{''.join(chapters)}</main></div>
<footer>Analysis date: 24 October 2026 (Asia/Tokyo). Existing measurements only; no new simulations were run for this report. Humans retain authority over requirements and adopted baselines. All exact technical tables and source identifiers are retained in this reading edition.</footer>
</body></html>'''
    (output / 'technical-report.html').write_text(page)
