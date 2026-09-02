# Ledger owner app — UI kit

One screen, `index.html`: the owner's home as designed in option 1b. Static HTML on the shared classes, with light click-through (approve → receipt, escalation approve, theme toggle, composer appends a user bubble). The React equivalents live in `../../components/core/` and map 1:1 to the existing app's `web/src/components/*.tsx`.

Regions, top to bottom: masthead band → hero (greeting + lede | hero figure + pills) → trend (stats row + area chart + axis) → main grid (thread + composer | rail: by-hour, top customers, unpaid, escalation card).
