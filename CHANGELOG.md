# Changelog

## 2026-09-27: ClawdBlock is now Pink Golem

The project was renamed to keep its name clearly apart from Anthropic's trademarks. The code, the tools and your world
are the same.

### Upgrading from ClawdBlock

1. Clone the new repository (`git clone https://github.com/sagistiki/pink-golem.git`), or point your existing clone
   at it: `git remote set-url origin https://github.com/sagistiki/pink-golem.git && git pull`.
2. Run `python3 pinkgolem.py connect <your client>` again. It registers the MCP server as `pinkgolem`, links the
   skill as `pinkgolem`, and removes the old `clawdblock` skill link.
3. That's it:
   - `clawdblock.json` is renamed to `pinkgolem.json` automatically.
   - Generators that read `CLAWDBLOCK_ROOT` / `CLAWDBLOCK_JOBS` / `CLAWDBLOCK_CU_DATA` keep working (both names are
     set).
   - `clawdblock.py` is now `pinkgolem.py`, and the skill folder is `skill/pinkgolem/`.

### Security (see [SECURITY.md](SECURITY.md))

- **Owners and guests:** `security.owners` in `pinkgolem.json`, asked for during setup. Chat lines reach the AI tagged
  `[owner]` or `[guest]`.
- **Guest lock, enforced in code:** after a guest talks to the AI, generators, admin commands (`op`, `whitelist`,
  `ban`, …), app patches and pack deploys are refused for 10 minutes, unless an owner types `!approve` (one action).
- `stop` is always refused. `minecraft_generate`'s `code` parameter is **off by default** (`security.allow_code`).
- `doctor` warns about missing owners, `allow_code` and `online-mode=false`.

**Existing installs:** add your Minecraft name to `pinkgolem.json`:

```json
"security": { "owners": ["YourMinecraftName"] }
```

Without it, every player counts as a guest and nobody can approve.

### Also new

- The default body is **Pink Golem**: the player `Golem` with the team prefix `Pink `, pink leather armor with a
  gold trim, and a pink block in hand, so players can tell it from a person. `bot_name`, `bot_prefix` and
  `bot_outfit: "none"` change it. A `bot_name` from an older config is kept.
- `npm run check` also fails when a doc gives a different tool count than the server really has (37).
- New banner.
