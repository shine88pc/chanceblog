# Chance_Blog

> **⚠️ AI AGENTS / GPT / GROK / CLAUDE / ANY LLM — READ THIS FIRST**
>
> Before doing **any** work in this repository, you **MUST** complete the following steps **in order**:
>
> 1. **[`HANDLER.md`](./HANDLER.md)** — 현황·조치사항·폴더 규칙·GPT 인수인계
> 2. **[`AI_COLLAB.md`](./AI_COLLAB.md)** — 듀얼 블로그 규칙
> 3. **[`WORKLOG.md`](./WORKLOG.md)** — 최신 항목 3~5개
> 4. **[`AGENTS.md`](./AGENTS.md)** — 모든 AI 공통 상시 규칙 (코드·워크플로 작업이면 `docs/ENGINEERING_GUIDE.md`, `docs/SECURITY_GUARDRAILS.md`도)
>
> Do **not** skip these steps even if the user did not explicitly tell you to read them.  
> This is a hard requirement to prevent conflicts between multiple AIs and divergent local folders.

---

## Project Overview

- **Live site**: https://shine88pc.github.io/chanceblog/
- **Repository**: `shine88pc/chanceblog` (**유일한 공식 소스**)
- **Type**: Bilingual (KR/EN) magazine + dual blog with Blogger (practical life)
- **Stack**: Jekyll + custom `index.html` (Tailwind CDN)
- **Current priority**: Google AdSense approval; Blogger automation (draft/API)

## Important Files for AI Collaboration

| File | Purpose |
|------|---------|
| **[`HANDLER.md`](./HANDLER.md)** | Multi-AI handler — status, actions, folder sync, GPT handoff |
| **[`AI_COLLAB.md`](./AI_COLLAB.md)** | Dual-blog rules — read before any work |
| **[`WORKLOG.md`](./WORKLOG.md)** | Continuous handoff log |
| **[`AGENTS.md`](./AGENTS.md)** | Standing rules for every AI (guardrails, verification) |
| [`docs/CHARTER.md`](./docs/CHARTER.md) | Goal, roles, change tiers (T0–T3), multi-AI protocol |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | Full-auto pipeline, blog registry, how to add a blog |
| [`docs/ENGINEERING_GUIDE.md`](./docs/ENGINEERING_GUIDE.md) | How to write code and verify it |
| [`docs/SECURITY_GUARDRAILS.md`](./docs/SECURITY_GUARDRAILS.md) | Security and policy guardrails, incident playbooks |
| [`docs/DEFECT_REGISTER.md`](./docs/DEFECT_REGISTER.md) | Verified known defects and their status |
| [`docs/ISSUE_EDITS.md`](./docs/ISSUE_EDITS.md) | Issue-form based edit requests → PR (spec, security model) |
| [`docs/COPILOT_GUIDE.md`](./docs/COPILOT_GUIDE.md) | How to use Copilot/AI precisely without coding knowledge |
| [`docs/REQUEST_BRIEFING.md`](./docs/REQUEST_BRIEFING.md) | Briefing to paste into an AI that cannot see the repo (e.g. mobile Claude) so it writes task requests that fit this program; requests go in `인수인계/작업요청/` |
| [`docs/ANALYTICS_PLAN.md`](./docs/ANALYTICS_PLAN.md) | Proposal: one dashboard for visitors, top posts and per-site AdSense revenue (awaiting owner decision) |
| `.github/editorial/BLOGGER_PROMPT.md` | Blogger tone/structure |
| `.github/editorial/BLOGGER_API_SETUP.md` | Blogger API setup |
| `.github/editorial/CHANCE_BLOG_TEMPLATE.md` | Chance_Blog editorial standards |

## Local folder rule

Use **one** official clone of this repo only. Always `git pull` before work and `git push` after. Do not mix with other project folders in VS Code.

## For Human Contributors

Share the repository link with any AI. The AI is expected to follow the read order above automatically.
