---
name: First-principles proposal
about: 第一原理に基づく変更・機能提案（必須4点）
title: ""
labels: []
assignees: []
---

<!-- 日本語が先、English mirror は下部。 -->

## 0. 前提

第一原理に基づいて判断します。機能・設計・導入は「慣習」ではなく**本当に必要か**を常に問います。以下 4 点は、**必要／不必要の切り分け**のためです（テンプレートを埋める儀式ではありません）。**書けないものは、まだ起票する段階にない**と捉えてください。

---

## A. 現状の課題（What is broken / missing）

- 今の設計・実装のどこが問題か（コード・挙動ベースで具体的に）
- 現状で起きうる具体的な失敗例

→ **この記述が弱い場合、「そもそも直す必要があるのか？」を疑ってください。**

<!-- ここに記入 -->

---

## B. なぜ解決しなければならないか（Why it matters）

- 放置した場合のリスク（安全性・再現性・自作自演・レビュー不能など）
- 本プラットフォームのミッション（設計↔検証ループ、決定論ゲート）との関係

→ **第一原理から見て、今やる理由があるかをここで説明してください。**

<!-- ここに記入 -->

---

## C. 本 Issue のスコープ（Scope — In / Out）

- **In scope**（この Issue 単体で完了する範囲）
- **Out of scope**（やらないこと）

→ **必要な機能と不必要な機能の切り分けは、ここが本体です。**

<!-- ここに記入 -->

---

## D. 改善見込み（Expected outcome）

- マージ後にどう変わるか（挙動・テスト・ログ・安全性）
- 受入条件（Acceptance criteria）を箇条書き

→ **「やった結果、何が良くなるか」が書けないなら、優先度を再検討してください。**

<!-- ここに記入 -->

---

## （任意）マルチエージェント設計 Issue の追加記載

マルチエージェント設計に関わる場合は、上記に加えて次も記載してください。

| 項目 | 記載内容 |
| --- | --- |
| **設計のいけてないところ** | 現行コードの具体的な弱点 |
| **それによる課題** | その弱点が引き起こす問題 |
| **提案による改善見込み** | 変更後にどう良くなるか |

<!-- 該当する場合のみ記入 -->

---

## （参考）検証関連 Issue のスコープ上限

本プラットフォーム（`engineering_agents`）の**検証上限は MIL（Model-in-the-Loop）**です。フライトソフトウェア・ターゲット処理系・実ハードウェアが無いため、**SIL / PIL / HIL は本リポジトリでは成立しません**。検証・接続に関する Issue では、この上限を Out of scope または前提として明記してください。

---

# (English mirror)

## 0. Premise

We judge from **first principles**. Every feature, design change, or adoption must answer **is it truly necessary?** — not convention. The four sections below visualize **necessary vs unnecessary** functionality. **If you cannot fill them in, the item is not ready to file.**

---

## A. Current problem (What is broken / missing)

- What is wrong in the current design or implementation (concrete, code/behavior-based)
- Concrete failure modes that can happen today

→ **If this section is weak, ask whether the problem needs fixing at all.**

---

## B. Why it must be solved (Why it matters)

- Risks if left unaddressed (safety, reproducibility, self-dealing hallucination, unreviewable behavior, etc.)
- How this relates to the platform mission (design↔verification loop, deterministic gates)

→ **Explain why this work is justified from first principles, now.**

---

## C. Scope (In / Out)

- **In scope** — what **this issue alone** completes
- **Out of scope** — what is explicitly not done here

→ **Separating necessary from unnecessary functionality is the core job of this section.**

---

## D. Expected outcome

- What changes after merge (behavior, tests, logs, safety properties)
- Acceptance criteria as a bullet list

→ **If you cannot state what gets better, reconsider priority.**

---

## (Optional) Multi-agent design — additional fields

For multi-agent design work, also state:

| Item | What to write |
| --- | --- |
| **Design weakness** | Concrete weakness in existing code |
| **Resulting problem** | Failures or risks that follow |
| **Expected improvement** | How behavior improves after the change |

---

## (Reference) Verification ceiling

This platform's verification ceiling is **MIL (Model-in-the-Loop)**. Without flight software, target processor, or hardware, **SIL / PIL / HIL do not apply in this repository**. State this ceiling in scope or assumptions for verification-related issues.
