# 開発履歴

当時のマイルストーン記録です。現行の状態は[親ページ](../../../../ja/users/scenarios/scrubber_degradation/index.md)で確認してください。

### scrubber_degradation（Mock ECLSS + EPS）— 完了


| 領域         | 内容                                                                        |
| ---------- | ------------------------------------------------------------------------- |
| シミュレータ     | `StationSimulator`（`MockEclssSimulator` + `EpsBackend` mock / `ssos_eps`） |
| シナリオ       | `scrubber_degradation` — 50 step、step 20 から異常注入                           |
| エージェント     | `none` / `labeled_rule_base` / `llm`、同種エンジニア N 体                          |
| 回復         | ファン加速、負荷削減、EPS ブースト、一時バイパス                                                |
| 事後設計       | `design_proposals.json`（scrubber 凍結。ランタイムトポロジ変更なし）                        |
| provenance | ランタイム **回復**（`request_eps_boost`）                                         |
| ダッシュボード    | CO₂ ppm / EPS / トポロジ / 2 run 比較                                           |

```text
[ scrubber_degradation — Mock 凍結 ]
  StationSimulator → ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json（scrubber ドメイン）
  Dashboard（ppm / EPS / トポロジ）
```
