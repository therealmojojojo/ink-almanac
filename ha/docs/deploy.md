# Deploy

## First-time setup

### 1. HAOS VM: SSH & Web Terminal add-on

In the HA UI:

1. Settings → Add-ons → Add-on Store → "Advanced SSH & Web Terminal" → Install.
2. Add-on config:
   ```yaml
   ssh:
     username: root
     password: ""
     authorized_keys:
       - "ssh-ed25519 AAAA... operator@workstation"
     sftp: true
     compatibility_mode: false
     allow_agent_forwarding: false
     allow_remote_port_forwarding: false
     allow_tcp_forwarding: false
   ```
3. Start the add-on and note the port (default `2222`).

### 2. Mosquitto broker add-on

Install "Mosquitto broker" from the add-on store if not already running.
Create a user for the device (e.g. `inkplate`) and record the password in
`firmware/include/secrets.h` (copied from `secrets.h.example`).

### 3. Renderer-host SSH access

The Sunday pairings automation SSHes from the HAOS VM to the Mac host.
Copy the operator's public key onto the Mac (`~/.ssh/authorized_keys`)
and put the matching private key into `/config/.ssh/id_ed25519` on the
VM (over the SSH add-on).

### 4. Wire `configuration.yaml`

Edit `/config/configuration.yaml` via the SSH add-on and add:

```yaml
homeassistant:
  packages: !include_dir_named custom/inkplate/integrations
automation inkplate: !include_dir_merge_list custom/inkplate/automations
sensor inkplate: !include_dir_merge_list custom/inkplate/sensors
```

`shell_command:` is defined inside `integrations/shell_commands.yaml` and loaded
automatically by the `packages` line above — do not add a second `!include` for
it, or HA will fail to load with a duplicate-key error.

### 5. Secrets

```bash
cp ha/secrets.yaml.example ha/secrets.yaml
# edit, fill in keys
```

The deploy script places this file at `/config/custom/inkplate/secrets.yaml`
on the VM — *not* `/config/secrets.yaml`. HA's `!secret` tag resolves from the
directory of the YAML doing the lookup upward, so the project fragments find
this file automatically while your existing `/config/secrets.yaml` (if any) is
left untouched.

## Deploy

```bash
make deploy-ha
```

Environment variables (optional):

| Var | Default | Meaning |
|---|---|---|
| `HA_HOST` | `homeassistant.local` | VM hostname |
| `HA_SSH_PORT` | `2222` | Add-on SSH port |
| `HA_USER` | `root` | Add-on SSH user |
| `HA_SSH_KEY` | `~/.ssh/id_ed25519` | Key path |

## Rollback

On the VM via SSH:

```bash
rm -rf /config/custom/inkplate
# then remove the three include lines from /config/configuration.yaml
ha core check && ha core restart
```

Native integrations (weather, sun, moon, Sonos) can be left in place — they're
idempotent and don't harm HA.
