# ADR-0001: Card-style radial menu replaces circular layout

## Status

Accepted (2026-07-03)

## Context

The original right-click radial menu displayed 3 action items (chat, costume, weather) as 80×80 circular buttons arranged in a left-crescent arc. The lock toggle was hidden in the menu center, invisible to users. The media control card (310×144) was positioned on the right side of a wide (~722px) popup.

Users reported being unable to find the lock function, and the crescent arc felt cluttered when the popup anchored near screen edges.

## Decision

Replace circular `RadialMenuItem` widgets with `RadialListRow` — a card-style row (46px tall, left color strip, icon area with hand-drawn line art, title + subtitle). The lock function moved from center to a dedicated row.

Layout: list (190px) on the left, media card (310px) on the far right with a calculated gap (~200px). The pet character sits in the gap between them.

Each icon is drawn with QPainter paths: speech bubble (chat), hanger silhouette (costume), sun with rays (weather), padlock (lock). No Unicode glyphs or emoji — the icons are hand-drawn to adapt to both light and dark system themes.

## Consequences

- **Positive**: Lock function is discoverable. Each action has a subtitle explaining what it does. Icons adapt to light/dark themes automatically.
- **Positive**: The original `RadialMenuItem` and `_layout_circle` / `_layout_with_media` are preserved — the row layout is only active when `RadialListRow` widgets are present in the item list. Menus without row items continue using the original circular layout.
- **Negative**: The popup is wider (~550-800px depending on gap) than the original circle-only layout, which may clip on small or vertically-oriented screens.
- **Negative**: The hand-drawn QPainter icons add ~60 lines of paint code and require a `_ICON_DRAWERS` dispatch table.
