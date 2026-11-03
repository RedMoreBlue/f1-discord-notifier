# F1 Discord Notifier

Pings your Discord **F1 role** before qualifying, sprint and race sessions — by default 1 hour, 15 minutes, 5 minutes before and when the session starts. All times are shown in **Estonian time** (`Europe/Tallinn`, switches between EET/EEST automatically).

The F1 calendar comes from the free [Jolpica F1 API](https://github.com/jolpica/jolpica-f1) (successor of the Ergast API). It's refreshed every 3 hours, so rescheduled sessions are picked up, and it's cached on disk in case the API is down.

## 1. Discord setup

1. **Webhook:** Channel settings → *Integrations* → *Webhooks* → *New Webhook* → *Copy Webhook URL*.
2. **Role ID:** User settings → *Advanced* → enable *Developer Mode*. Then Server settings → *Roles* → right-click your F1 role → *Copy Role ID*.
3. **Allow the role to be pinged:** Server settings → *Roles* → F1 → enable *Allow anyone to @mention this role* (webhooks can't ping a role otherwise).

### Optional: `/f1test` and `/f1next` slash commands

Webhooks can't receive commands, so for commands typed *in Discord* you need a bot:

1. <https://discord.com/developers/applications> → *New Application* → *Bot* → *Reset Token* → copy it into `DISCORD_BOT_TOKEN`.
2. *OAuth2* → *URL Generator* → scopes `bot` + `applications.commands` → open the URL and add the bot to your server.
3. Put your server ID (right-click server icon → *Copy Server ID*) into `DISCORD_GUILD_ID` so commands appear instantly.

`/f1test` is only visible to members with *Manage Server* by default (change under Server settings → *Integrations*), so random members can't spam the role.

## 2. Install on Debian (Proxmox LXC)

```bash
apt update && apt install -y git
git clone https://github.com/RedMoreBlue/f1-discord-notifier.git /opt/f1-discord-notifier
cd /opt/f1-discord-notifier
sh install.sh            # creates venv, user, .env and the systemd service
nano .env                # fill in DISCORD_WEBHOOK_URL and F1_ROLE_ID (and bot token if wanted)
systemctl restart f1notify
```

The repo is private, so `git clone` asks for a login: use your GitHub username and a [personal access token](https://github.com/settings/tokens) as the password (or make the repo public — it contains no secrets; those live only in `.env`).

Make sure the container's clock is right (`timedatectl`); it should be by default in an LXC since it uses the host clock.

## 3. Usage

| Command | What it does |
|---|---|
| `f1notify test` | Sends a test notification (next race, "starts in 15 minutes") to the F1 role |
| `f1notify test --session qualifying --minutes 5` | Test with another session / time |
| `f1notify upcoming` | Lists upcoming sessions in Estonian time (🔔 = will be notified) |
| `/f1test` in Discord | Same as `f1notify test` (bot only) |
| `/f1next` in Discord | Shows the next sessions (bot only) |
| `systemctl status f1notify` | Service status |
| `journalctl -u f1notify -f` | Live logs |

## Configuration (`.env`)

| Variable | Default | |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | — | required |
| `F1_ROLE_ID` | — | required |
| `REMINDER_MINUTES` | `60,15,5,0` | minutes before start; `0` = "starting now" |
| `SESSIONS` | `sprint_qualifying,sprint,qualifying,race` | also available: `fp1,fp2,fp3` |
| `TIMEZONE` | `Europe/Tallinn` | |
| `DISCORD_BOT_TOKEN` | empty | enables slash commands |
| `DISCORD_GUILD_ID` | empty | instant slash-command registration |

After editing: `systemctl restart f1notify`.

## Updating

```bash
cd /opt/f1-discord-notifier && git pull && sh install.sh
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest
```

Sent reminders are remembered in `data/sent.json`, so restarting the service never causes duplicate pings; a reminder missed by less than 3 minutes (e.g. during a restart) is still sent.
