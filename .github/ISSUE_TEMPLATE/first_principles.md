---
name: First-principles proposal
about: 第一原理思考に基づく Issue（§0 定義 + 必須 A–D）
title: ""
labels: []
assignees: []
---

<!-- 日本語が先、English mirror は下部。 -->

## 0. 前提

**第一原理思考（First-principles thinking）** — 人によって定義は異なります。本リポジトリでは次の意味で使います。

> **第一原理思考**：既存の常識や前例を疑い、問題を根本的な要素にまで分解し、確実に証明できる事実だけを積み上げて新しい解決策を構築するアプローチ。

このテンプレートは、そうやって**知見・知恵を積み上げるための構造化手段**です。機能・設計・導入は「慣習」ではなく**本当に必要か**を常に問います。以下 4 点は、**必要／不必要の切り分け**のためです（テンプレートを埋める儀式ではありません）。**書けないものは、まだ起票する段階にない**と捉えてください。

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

# (English mirror)

## 0. Premise

**First-principles thinking** — definitions vary by person. In this repository we use:

> **First-principles thinking**: An approach that questions existing conventions and precedents, decomposes problems down to their fundamental elements, and builds new solutions by stacking only facts that can be reliably proven.

This template is a **structured means to accumulate knowledge and wisdom** that way. Every feature, design change, or adoption must answer **is it truly necessary?** — not convention. The four sections below visualize **necessary vs unnecessary** functionality. **If you cannot fill them in, the item is not ready to file.**

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
