---
name: frontend-review
description: Review NTU Events discovery UI and working prototypes in the browser, checking desktop and mobile flows, visual clarity, accessibility, and browser errors.
---

# Frontend review

Run commands from the repository root. Read the active scope and approval stage
in [the implementation plan](../../../docs/IMPLEMENTATION_PLAN.md#5-current-milestone-uiux-and-frontend-consolidation).
Use [the business requirements](../../../docs/BUSINESS_REQUIREMENTS.md#5-discovery-experience)
to assess the product direction and [the development guide](../../../docs/DEVELOPMENT.md#frontend-agent-tools)
for startup, browser commands, and verification.

Use the installed Playwright CLI skill for browser mechanics. Prefix its
`playwright-cli` examples with `corepack pnpm exec`. Give the review its own
named session, such as `-s=frontend-review`, and close that session afterward.

Review the flows and screens affected by the task:

- Exercise discovery, event details, and return navigation. Check that useful
  filter and view context survives, including movement between approved views.
- Inspect desktop and mobile screenshots, not just the page snapshot. Check
  readable event facts, hierarchy, spacing, overflow, and reachable controls.
- Check keyboard navigation, visible focus, labels, contrast, and reduced
  motion. A narrow viewport alone does not verify touch interaction.
- Include relevant loading, empty, error, sparse-event, online, and hybrid
  states. Use clearly identified simulated data when a prototype needs it;
  do not publish or alter the owner's Events to manufacture a test case.
- Inspect console errors and failed requests. Distinguish application failures
  from unavailable backend data or external map services.

Keep screenshots and traces under ignored `var/audits/frontend/`. Report the
screens and flows checked, actionable findings with reproduction steps, and
anything unavailable or simulated. Do not equate a clean automated scan with
a complete accessibility review or prototype approval.
