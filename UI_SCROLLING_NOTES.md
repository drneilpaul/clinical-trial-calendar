# UI Scrolling and Sticky Headers

This app renders the main calendar via HTML to enable sticky headers and large tables. The logic lives in `display_components.py`.

## Key Implementation Points

- The calendar is rendered via `components.html(...)` with a custom HTML table.
- Sticky headers require:
  - `position: sticky` (and `-webkit-sticky`) on header cells.
  - A fixed‑height scroll container with `overflow` enabled.
  - `border-collapse: separate` so sticky headers work reliably.
- Safari requires:
  - The `components.html(..., scrolling=False)` iframe setting for sticky to work.
  - Explicit `-webkit-sticky` applied via JavaScript for robustness.

## Scroll Container

The HTML generator `_generate_calendar_html_with_frozen_headers(...)`:
- Wraps the table in a `.calendar-container`.
- Applies scrollbar visibility based on session state (`show_scrollbars`).
- Uses localStorage to persist scrollbar preference.
- Supports auto‑scroll to “today” on initial load.

## Common Pitfalls

- Pandas `Styler` can override sticky positions; the app avoids inline styles where possible.
- If sticky headers stop working, confirm:
  - The container has a fixed height.
  - The iframe is not independently scrolling.
  - `position: sticky` is applied to header cells (JS fallback).

## Site Busy View

`display_site_busy_calendar(...)` uses a separate HTML layout (`_generate_site_busy_html`) with its own scroll container (`site-busy-container`) and a different auto‑scroll implementation.

