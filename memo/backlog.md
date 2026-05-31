# Backlog — 研究・設計検討項目

MVP スコープ外だが、価値がありトラックしておくテーマ。実装優先度は [mvp_plan.md](mvp_plan.md) のロードマップに従う。

---

## BL-001: ロールラベル付与 vs 創発ロール（Base Role）

**ステータス**: 検討中（Week-1 以降）  
**関連**: Day 4 エージェントチーム設計、lunar_agents の structured communication 実験

### 背景

運用フェーズのエージェントチーム（Monitor / Diagnostician / Operator / DesignEngineer 等）は、**人間の都合による分業のラベル化**に過ぎない可能性がある。MVP では scrubber_degradation に即した**特定ロール**を与えて異常対応を通すが、これはデモ成立のための pragmatic な選択である。

### 検討問い

| 条件 | 仮説 |
| --- | --- |
| **Labeled** — シナリオ固有の 4 ロールを明示付与 | 異常対応が速く・再現性が高い。プロンプト/ルール設計が楽。 |
| **Unlabeled** — Base Role エージェント（ロール名・役割指示なし） | テレメトリと通信履歴のみから、状況に即した役割分担が**創発**する可能性。 |
| **比較** | 創発の質（対応速度、設計変更の妥当性、コミュニケーション冗長性）を定量比較できる。 |

### 価値

- lunar_agents で示した「構造化通信・個体差→創発」の延長線上で、**ECLSS レジリエンス・ループ**文脈での検証になる
- ロールを与える/与えない設計判断の根拠データになる
- One Piece 側の「誰が設計変更を提案したか」の provenance とも接続可能

### 実験案（未スケジュール）

1. 同一 `scrubber_degradation` シナリオ・同一 Mock ECLSS
2. **Run A**: `agents.mode: labeled`（scrubber_degradation 専用 4 ロール）
3. **Run B**: `agents.mode: base`（N 体の Base Role、ロール YAML なし）
4. 比較指標（案）:
   - 回復までの step 数（CO2 < 1000）
   - `messages.jsonl` の message_type 多様性 / 役割相当の自己記述
   - 設計変更の回数と最終 health
   - LLM 使用時: reasoning の individuality（lunar_agents 指標流用）

### MVP との関係

- **Week-1**: Labeled + rule_based のみ実装（汎用ロールフレームワークは作らない）
- **BL-001**: Week-2 以降 or ハッカソン後。Base Role 実装時に `agents.mode: base` を追加

---

## BL-002: （予約）

今後の検討項目をここに追記する。
