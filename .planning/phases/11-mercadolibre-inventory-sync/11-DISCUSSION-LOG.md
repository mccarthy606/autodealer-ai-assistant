# Phase 11: MercadoLibre Inventory Sync - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-28
**Phase:** 11-mercadolibre-inventory-sync
**Areas discussed:** Метод синхронизации, Проданные/снятые товары, Конфликты данных, Частота и триггер

---

## Метод синхронизации

| Option | Description | Selected |
|--------|-------------|----------|
| API — основной | sync_listings() через OAuth токен. Надёжно, полные данные. | ✓ |
| Скрапинг — основной | fetch_seller_items_public() по nickname, без токена. Хрупко. | |
| Только API без fallback | Без скрапинга. | |

**Пагинация:**
| Option | Selected |
|--------|----------|
| Полная пагинация (offset loop) | ✓ |
| Лимит 50 (MVP) | |

---

## Проданные/снятые товары

| Option | Description | Selected |
|--------|-------------|----------|
| sold автоматически | ML = источник правды по статусу. | ✓ |
| available оставляем | Статус только дилер меняет вручную. | |

---

## Конфликты данных

| Option | Description | Selected |
|--------|-------------|----------|
| ML всегда источник правды | Sync перезаписывает цену, km, фото. | ✓ |
| Admin UI приоритетнее | Sync не трогает вручную изменённые поля. | |

---

## Частота и триггер

| Option | Selected |
|--------|----------|
| Каждые 4 часа (Celery beat) | ✓ |
| Каждый час | |
| 2 раза в день | |

**Scope:**
| Option | Selected |
|--------|----------|
| Только с ml_access_token | ✓ |
| Все дилеры | |

**Кнопка:**
| Option | Selected |
|--------|----------|
| Страница инвентаря (/admin/ui/cars) | ✓ |
| Страница интеграций | |
| Обе страницы | |

**Отображение результата:**
| Option | Selected |
|--------|----------|
| Цифры + время ("47 обновлено, 3 новых, hace 3 min") | ✓ |
| Только время | |
