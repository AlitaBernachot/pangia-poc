# PangIA Frontend Client

A React + Vite + Tailwind CSS frontend for the [PangIA](../README.md) geospatial AI assistant.

## Features

- **AI Chat page** — streaming chat with the PangIA backend over SSE, with:
  - File attachment support (click or drag & drop) modelled after [AI SDK Elements Attachments](https://elements.ai-sdk.dev/components/attachments)
  - Agent selector toggles to target specific data agents
  - Per-agent activity panels showing intermediate reasoning and tool calls
  - Markdown rendering for AI responses
  - Animated streaming cursor
- **FAQ / About page** — accordion FAQ and overview of available agents
- **React Router** — client-side routing between `/` (chat) and `/faq`

## Tech Stack

| Tool | Version |
|------|---------|
| React | 19 |
| Vite | 8 |
| Tailwind CSS | 4 |
| React Router | 7 |
| react-markdown | 10 |
| lucide-react | latest |

## Getting Started

### Development

```bash
# Install dependencies
npm install

# Start the dev server (proxies /api to localhost:8084)
npm run dev
```

The dev server runs at `http://localhost:5173`. API requests to `/api/*` are proxied to the backend at `http://localhost:8084`.

### Production Build

```bash
npm run build
npm run preview
```

### Docker

```bash
docker build -t pangia-frontend-client .
docker run -p 3000:80 pangia-frontend-client
```

## Configuration

Copy `.env.example` to `.env` and set `VITE_API_URL` if the backend is not on the same host.

```bash
cp .env.example .env
# Edit VITE_API_URL if needed
```
