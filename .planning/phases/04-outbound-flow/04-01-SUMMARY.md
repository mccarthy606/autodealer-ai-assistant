---
phase: "04"
plan: "01"
subsystem: adapters, services, database
tags: [whatsapp, mercadolibre, phone-normalization, migration]
dependency_graph:
  requires: [whatsapp_cloud.py, mercadolibre.py, models.py]
  provides: [send_template, get_buyer_contact, normalize_ar_phone, ix_inv_dealer_ml_item]
  affects: [04-02 outbound service pipeline]
tech_stack:
  added: []
  patterns: [mock-mode adapters, E.164 phone normalization, composite DB index]
key_files:
  created:
    - src/services/phone_utils.py
    - alembic/versions/004_add_ml_item_id_index.py
  modified:
    - src/adapters/whatsapp_cloud.py
    - src/adapters/mercadolibre.py
decisions:
  - "Lazy import of phone_utils inside get_buyer_contact to avoid circular imports"
  - "Phone normalizer builds 549+area+number format (WhatsApp E.164 for Argentina)"
metrics:
  duration: "2min"
  completed: "2026-03-27"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 2
---

# Phase 04 Plan 01: Adapter Extensions Summary

WhatsApp send_template() and ML get_buyer_contact() methods added, Argentine phone normalizer created, and composite index on (dealership_id, ml_item_id) migrated for fast outbound lookups.

## What Was Done

### Task 1: Adapter Method Extensions
- Added `send_template(to, template_name, language_code, components)` to `WhatsAppCloudAdapter` -- sends template messages via Graph API with full mock mode support
- Added `get_buyer_contact(question_id)` to `MercadoLibreAdapter` -- fetches buyer phone/email/name from ML Questions API using api_version=4
- Both methods follow existing adapter patterns: mock mode when unconfigured, httpx client, structured logging

### Task 2: Phone Normalizer + DB Migration
- Created `src/services/phone_utils.py` with `normalize_ar_phone(area_code, number)` function
- Handles common Argentine formats: area_code="11" + number="12345678" -> "5491112345678"
- Strips country code 54, leading 0, old mobile prefix 15, and avoids double-9
- Created Alembic migration 004: composite index `ix_inv_dealer_ml_item` on `(dealership_id, ml_item_id)`

## Deviations from Plan

None - plan executed exactly as written.

## Pre-existing Issues Noted

- Test suite has a pre-existing failure: `models.py` line 212 `text()` call conflicts with `Text` column import (Column object not callable). This is NOT caused by plan 04-01 changes and was verified to exist before these changes.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | b1f67c3 | feat(04-01): add send_template() to WhatsApp adapter and get_buyer_contact() to ML adapter |
| 2 | 15b207a | feat(04-01): add phone normalization utility and ml_item_id index migration |

## Known Stubs

None. All methods are fully implemented with proper mock mode, error handling, and return values.
