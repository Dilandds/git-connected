# Fix Queue

Add issues below as they come in from the client. Priority 1 = do first, 5 = do last (or leave it blank / P5 for "whenever"). The Screen field is the only way the agent knows where to look in the code, so be specific — either a screen name from the app (e.g. "3D Viewer toolbar", "Project > R&D > Textures tab") or a file path if you already know it.

The agent works top-to-bottom by priority, 5 items per run, commits each fix directly to `main`, and checks the box when done. No automated testing or screenshot comparison — you verify manually and re-open the item (uncheck it, add a note) if it's wrong.

Format:
`- [ ] P<1-5> | <short title> | Screen: <hint> | <what's wrong / what should change>`

## Queue

- [ ] P1 | Example: fix save icon color | Screen: 3D Viewer toolbar | The save icon should be blue (#2563eb) instead of gray to match the rest of the toolbar.
