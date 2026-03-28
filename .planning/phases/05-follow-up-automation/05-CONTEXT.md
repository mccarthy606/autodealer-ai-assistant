# Phase 5: Follow-Up Automation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Automated follow-up messages for unresponsive leads: 24h first reminder, 3-day second reminder, all via WhatsApp template messages (Meta 24h rule compliance), max 2-3 follow-ups per conversation, opt-out detection and immediate stop. Uses Celery Beat for periodic scheduling.

</domain>

<decisions>
## Implementation Decisions

### Follow-Up Schedule (FUP-01, FUP-02)
- **D-01:** Celery Beat periodic task runs every 15 minutes. Scans conversations for follow-up candidates.
- **D-02:** First follow-up: 24 hours after last customer message with no response.
- **D-03:** Second follow-up: 3 days (72 hours) after last customer message with no response.
- **D-04:** Only follow up on conversations where: mode="bot" (not handed off to manager), stage in ("PRESENTING", "DETAILS", "OUTBOUND_INIT", "BROWSING"), not already followed up at that tier.

### Template Messages (FUP-03)
- **D-05:** All follow-ups MUST use WhatsApp template messages, not free-form text (Meta 24h window rule — after 24h of no customer message, only templates allowed).
- **D-06:** Two template names:
  - `followup_24h_v1` — "Hola {{1}}! Seguís interesado en {{2}}? Está disponible por {{3}}. Te esperamos en {{4}}!"
  - `followup_3d_v1` — "Hola {{1}}! Te escribimos de {{2}}. El {{3}} que consultaste sigue disponible. Querés pasar a verlo?"
- **D-07:** Templates must be submitted to Meta for approval before follow-ups work in production.

### Limits (FUP-04)
- **D-08:** Maximum 2 follow-ups per conversation (24h + 3d). After both sent, no more auto follow-ups.
- **D-09:** Track follow-up count in `Conversation.state["followup_count"]` and `state["last_followup_at"]`.

### Opt-Out (FUP-05)
- **D-10:** Detect opt-out intents: "no", "no me interesa", "no gracias", "dejá de escribir", "stop", "not interested". Add to intent.py.
- **D-11:** On opt-out detection: set `state["opted_out"] = True`, never follow up again on this conversation.
- **D-12:** Respond with acknowledgment: "Entendido, no te vamos a molestar más. Si cambiás de opinión, escribinos!"

### Implementation
- **D-13:** New file: `src/tasks/followup_task.py` — Celery Beat task
- **D-14:** Use existing `WhatsAppCloudAdapter.send_template()` from Phase 4
- **D-15:** New Celery Beat schedule entry in `celery_app.py`

### Claude's Discretion
- Exact opt-out regex patterns
- Celery Beat interval (suggested 15 min, can adjust)
- Database query optimization for follow-up candidates
- Error handling for failed template sends

</decisions>

<canonical_refs>
## Canonical References

### Existing Code
- `src/tasks/celery_app.py` — Celery configuration (add Beat schedule)
- `src/adapters/whatsapp_cloud.py` — send_template() from Phase 4
- `src/services/conversation_engine.py` — state machine, intent handling
- `src/services/intent.py` — intent detection (add OPT_OUT intent)
- `src/db/models.py` — Conversation model (state JSONB)

### Research
- `.planning/research/PITFALLS.md` — P7 (follow-up spam), P1 (24h window)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `WhatsAppCloudAdapter.send_template()` — Built in Phase 4, ready for follow-up templates
- `Celery` + `Redis` — Already configured, just need Beat schedule
- `Conversation.state` JSONB — Can store followup_count, last_followup_at, opted_out
- `detect_intent()` — Add OPT_OUT intent patterns

### Integration Points
- `celery_app.py` — Add Beat schedule for followup task
- `intent.py` — Add OPT_OUT constant and regex patterns
- `conversation_engine.py` — Handle OPT_OUT intent → set opted_out flag

</code_context>

<specifics>
## Specific Ideas

No specific requirements — all decisions delegated to Claude.

</specifics>

<deferred>
## Deferred Ideas

- Re-engagement with new inventory matching preferences — v2
- Visit confirmation day-of reminder — v2
- Configurable follow-up schedule per dealership — v2

</deferred>

---

*Phase: 05-follow-up-automation*
*Context gathered: 2026-03-27*
