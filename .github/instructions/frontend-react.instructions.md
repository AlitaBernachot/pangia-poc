---
# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

description: "Use when building React components or UI features in frontend-client/. Covers icon usage, styling conventions, and component rules."
applyTo: "frontend-client/**/*.{tsx,ts}"
---

# Frontend React Guidelines

## Icons

Always use **lucide-react** icons. Never use emoji characters as icons in JSX.

```tsx
// ✅ correct
import { AlertTriangle, Map } from 'lucide-react'
<AlertTriangle size={14} />

// ❌ wrong
<span>⚠️</span>
<span>🗺️</span>
```

Import only the icons you use. All available icons: https://lucide.dev/icons

## Links

All `<a>` elements that navigate to an external URL **must** include `target="_blank"` and `rel="noopener noreferrer"`.

```tsx
// ✅ correct
<a href={url} target="_blank" rel="noopener noreferrer">Open</a>

// ❌ wrong
<a href={url}>Open</a>
```

This applies to every link rendered in JSX, including those inside markdown renderers (`react-markdown` component overrides, etc.).

## Component structure & domain separation

- **Extract reusable UI primitives** into `src/components/common/` (e.g. `Modal`, `Badge`, `Button`). Never inline a generic UI pattern more than once.
- **Keep domain logic separate from UI.** A component in `common/` must not contain business or domain logic — pass everything it needs via props.
- **One responsibility per component.** If a component renders markup *and* manages complex state *and* handles data formatting, split it.
- **Prefer small, focused components** over large monolithic ones. When a section of JSX is independently meaningful, extract it.

```tsx
// ✅ correct — generic primitive in common/, domain logic in the feature component
// src/components/common/Modal.tsx  ← layout only
// src/components/chat/ConfirmDeleteModal.tsx ← uses Modal, owns the copy & logic

// ❌ wrong — modal markup inlined inside a feature component
function MyFeature() {
  return <div>...<div className="fixed inset-0 ...">...</div></div>
}
```
