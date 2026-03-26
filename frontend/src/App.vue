<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="logo">
        <span class="logo-icon">🌍</span>
        <span class="logo-text">PangIA <em>GeoIA Agent</em></span>
      </div>
    </header>
    <main class="app-main">
      <ChatInterface />
    </main>
  </div>
</template>

<script setup lang="ts">
import ChatInterface from '@/components/ChatInterface.vue'
</script>

<style>
/* ─── CSS Reset & Variables ─────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --color-bg: #0f1117;
  --color-surface: #1a1d27;
  --color-surface-2: #22263a;
  --color-border: #2e3347;
  --color-primary: #6366f1;
  --color-primary-hover: #4f51d4;
  --color-user-bubble: #6366f1;
  --color-ai-bubble: #22263a;
  --color-text: #e2e8f0;
  --color-text-muted: #8892a4;
  --color-accent: #38bdf8;
  --radius: 12px;
  --font: 'Inter', system-ui, sans-serif;
}

html, body {
  height: 100%;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font);
  font-size: 15px;
  line-height: 1.6;
}

#app { height: 100%; display: flex; flex-direction: column; }

/* ─── App Shell ─────────────────────────────────────────────────────────────── */
.app-shell { display: flex; flex-direction: column; height: 100vh; }

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1.5rem;
  height: 56px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.logo { display: flex; align-items: center; gap: 0.5rem; font-size: 1.1rem; font-weight: 600; }
.logo-icon { font-size: 1.4rem; }
.logo em { font-style: normal; color: var(--color-accent); font-size: 0.85rem; font-weight: 400; }

.app-main { flex: 1; overflow: hidden; display: flex; }
</style>
