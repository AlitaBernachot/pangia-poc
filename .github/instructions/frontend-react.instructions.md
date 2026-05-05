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
