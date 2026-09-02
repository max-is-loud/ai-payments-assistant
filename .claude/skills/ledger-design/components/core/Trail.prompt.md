Agent activity list (PLAN / ACT / OBS / ASK / ERR) — feed it the turn's SSE events unchanged.

```jsx
<Trail events={turn.events} />
```
Failed observations render as an ERR sentence, not JSON.