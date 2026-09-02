---
name: ledger-design
description: Use this skill to generate well-branded interfaces and assets for Ledger (the AI payments assistant owner app), either for production or throwaway prototypes/mocks. Contains design guidelines, colors, type, tokens, CSS classes, React components and a full-page UI kit.
user-invocable: true
---

Read the readme.md file within this skill, and explore the other available files: tokens/, components/components.css, components/core/*.jsx (+ .prompt.md), ui_kits/ledger/index.html.
If creating visual artifacts (slides, mocks, throwaway prototypes), link styles.css and use the .ldg-* classes to produce static HTML for the user to view. If working on production code (the React app in web/src), adopt tokens/*.css + components/components.css in place of web/src/styles.css and port components/core/*.jsx into web/src/components, keeping the existing hooks (useConversation) and API types unchanged.
If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.
