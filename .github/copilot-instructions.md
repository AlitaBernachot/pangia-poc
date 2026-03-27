# Copilot Instructions

## Agents

- Whenever a new agent is added to `backend/app/agent/`, always update `README.md` to document it: include its name, purpose, and any relevant configuration or dependencies.

## Frontend

- Always use a PrimeVue component when one exists for the UI element being implemented (e.g. `Button`, `InputText`, `Dialog`, `DataTable`, `Dropdown`, `Toast`, etc.).
- Do not use plain HTML elements (`<button>`, `<input>`, `<select>`, ...) when an equivalent PrimeVue component is available.
- Import PrimeVue components from `primevue/<component-name>`.
