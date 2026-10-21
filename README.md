# Celebration & Event Planner

A planning assistant for **weddings, birthdays and community events**. Give it your guest count, budget, date and context. It returns a budget split, a dated timeline, a vendor checklist, an explanation of why the plan looks the way it does, and personalised ideas.

**Chosen vertical:** Challenge 5, Celebration & Event Planner.

## Approach and logic

The design separates what must be *correct* from what can be *creative*, and never lets the second block the first.

| Layer | Files | Role |
|---|---|---|
| Deterministic engine | `planner.py`, `knowledge.py` | Budget, timeline, vendor checklist, warnings and a plain-language rationale. Pure functions of the request and an explicit `today`. |
| Decision engine | `decision.py` | Before any model call, decides how much the model may do (full, conservative, or skipped) from the event's context. |
| Guardrails | `guardrails.py` | Runs outside the model: injection screening, personal-data scrubbing, a per-request canary. |
| Orchestration | `services.py` | Sequences guardrails, routing, the model and output checks. Falls back to built-in ideas on any problem. |
| Adapter | `ai.py` | Gemini behind a `TextGenerationPort` interface (dependency inversion). Tests inject a fake instead. |
| HTTP | `main.py`, `security.py` | Routing, validation errors, rate limiting, security headers, compression. |
| UI | `static/` | Accessible form and results. No framework, no build step. |

Money is never left to a language model. Amounts use `Decimal` and the largest-remainder method, so the lines always add up to exactly the budget.

### Decisions made from user context

- **Event type** selects the budget weights, timeline and vendor checklist. About 10% is always held back as contingency.
- **Outdoor or mixed venue** adds a weather-backup category. **Accessibility needs** add an accessibility category. **Children** at a wedding or community event add a children's zone.
- **Dietary needs** extend the caterer checklist (for example written allergen handling for nut allergies).
- **Date** drives the timeline, worked backwards from the event. Overdue steps move to today, are flagged, and are counted in the rationale.
- **Budget per guest** is compared with a rough floor for the event type and currency. Below it, the plan warns the budget is tight.
- **Guests of 500 or more** add crowd, security and first-aid guidance.
- **AI routing:** an event within a day skips the model. A rush (under 14 days), tight budget or large crowd switches it to a conservative mode with lower temperature and matching instructions (for example "favour low-cost ideas"). Children and accessibility needs add their own instructions.

Every rule that shaped the plan appears under **Why this plan** in the UI, and ideas always say whether they came from the AI or the built-in list.

## How it works

1. The browser posts the form to `POST /api/plan`. Pydantic validates it. The engine builds the plan in well under a millisecond and returns it with no model involved.
2. The page renders the plan immediately, then posts the same details to `POST /api/ideas`.
3. The idea service screens free text (fields that look like instructions are withheld, emails, phone numbers and key-like strings are redacted), asks the decision engine for a mode, and calls Gemini with a data-only prompt and a random canary token.
4. The reply is treated as untrusted. A leaked canary, bad JSON, links, markup or personal data cause it to be discarded or cleaned. On any failure, built-in ideas are shown with an honest notice.
5. Identical requests are served from a bounded 10-minute cache.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=your-key      # optional
uvicorn app.main:app --reload
```

Open http://localhost:8000. Without a key the app runs with built-in ideas. The app reads environment variables, not a `.env` file. See `.env.example` for the names.

## Test and check

```bash
pip install -r requirements.txt ".[dev]"
pytest                  # 116 tests, fails below 95% coverage (currently 99%)
ruff check . && ruff format --check .
mypy app                # strict
bandit -r app
pip-audit -r requirements.txt
bash scripts/preflight.sh   # secrets, size, single branch, everything committed
```

CI (`.github/workflows/ci.yml`) runs the same checks on every push. Tests use a deterministic fake model and assert on resulting state, so none need a network or a real key. They cover the allocation maths (including randomised sum checks), each context rule, validation, injection handling, canary interception, caching, load shedding, rate limiting and proxy-header spoofing, security headers, and static accessibility checks on the HTML.

## Evaluation criteria and where to look

| Criterion | What was done |
|---|---|
| **Code quality** | Layered modules with one job each. Model access behind a port. Full type hints (`mypy --strict`). Google-style docstrings enforced by `ruff` (pydocstyle), plus formatting, import order and bugbear rules. Data separated from logic. |
| **Security** | Closed enums and bounded fields, unknown fields rejected. Guardrails run outside the model: injection screening, personal-data scrubbing, canary tokens, output validation. API key only from the environment, sent in a header, hidden from `repr`. CSP with no inline script or style, HSTS, frame denial, body-size cap, per-client rate limiting that ignores spoofed `X-Forwarded-For`, no docs endpoint, validation errors that do not echo input, no `innerHTML`. Pinned dependencies, `pip-audit` and `bandit` in CI. |
| **Problem alignment** | Budgets, timelines, vendor checklists and personalised ideas for the three event types, driven by the user's own context, with the reasoning shown and the AI's role stated honestly. |
| **Efficiency** | The plan never waits on the model. One shared HTTP client, a 12-second timeout, a cap on concurrent model calls that sheds load instead of queueing, a bounded cache, gzip, a bounded rate-limiter table, and in-flight requests cancelled when the user resubmits. Measured on a development container, a full plan takes about 0.2 ms. |
| **Testing** | Pure engine, injectable clock and model, state-based tests, parametrised cases, coverage gate. |
| **Accessibility** | Labelled controls, fieldsets, skip link, landmarks, 24 px or larger targets, dark focus ring with a 3:1 or better contrast, budget chart backed by a real table, a status region mounted at page load that announces one short message per state change instead of re-reading the page, focus moved to the results heading, errors in a `role="alert"` box, reflow to 320 px, reduced-motion support, locale-aware number and date formatting. |

## Assumptions and limits

- Budget weights, lead times and per-guest floors are general heuristics, not market quotes. The floor uses fixed approximate currency rates (INR, USD, EUR, GBP).
- The canary token detects prompt leakage. It is a tripwire, not the main defence. The system prompt holds no secrets.
- The injection screen is a heuristic. It drops suspicious free-text fields rather than rejecting the request, so a false positive costs a little personalisation and never blocks the plan.
- The rate limiter is in memory. For several instances, use a shared store. Behind a reverse proxy, set `TRUSTED_PROXY_HOPS` (1 on Cloud Run); otherwise every client appears to share the proxy's address.
- Nothing is stored. Each plan is generated per request.
- A `Dockerfile` is included for container hosts such as Cloud Run.
