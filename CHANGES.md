## Recent UI updates

- Added concise hover tooltips to canvas nodes so key settings like arrival rate, service rate, queue policy, routing policy, and scheduling policy are visible at a glance.
- Added info tooltips in the right-side properties panel and replaced the old help glyph with a standard circular `i` icon styled to match the dark UI.
- Improved tooltip positioning so node tooltips render above nearby nodes and properties-panel tooltips stay within the panel instead of overflowing off the right edge.
- Disabled server routing-policy selectors when a node has fewer than two outgoing edges, and added inline copy explaining that no routing decision exists in that case.
- Added an `Undo` action for canvas edits, including node moves and property changes, and prevented `Delete`/`Backspace` from removing the selected node while a properties-panel text input is actively being edited.

## Recent policy updates

- Added first-class server queue policies so server queue selection is now separate from downstream routing and station scheduling.
- Added uploadable custom policy support with separate categories for downstream server routing, local server queue policies, and upstream station scheduling policies.
- Updated the UI and API so users can upload policy files, browse their available custom policies, and assign the correct policy type directly from each node's editor.
