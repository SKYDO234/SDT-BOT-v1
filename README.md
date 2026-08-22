# <div align="center">🚀 SDT-BOT V1

**Powerful Discord VPS Management Bot**

Create • Manage • Access Linux VPS directly from Discord

🌐 Tailscale Powered • ⚡ Fast • 🔐 Secure • 🤖 Discord Based

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python) 
![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white) 
![Linux](https://img.shields.io/badge/Linux-Ubuntu%20%7C%20Debian-black?style=for-the-badge&logo=linux) 
![Tailscale](https://img.shields.io/badge/Tailscale-200033?style=for-the-badge&logo=tailscale&logoColor=white)

</div>---

# ✨ Features

- 🌐 IPv4 Address Instead of SSH/TMate
- 🤖 Discord VPS Management
- 🔐 Tailscale Login Authentication
- 👑 Admin Permission System
- ⚡ Fast & Lightweight
- 🐧 Ubuntu VPS Support
- 📡 Tailscale IPv4 Networking
- 🛠️ Simple Configuration

---

# 🐧 Supported Operating Systems

Operating System| Status
Ubuntu 20.04| ✅ Supported
Ubuntu 22.04| ✅ Supported

«⚠️ Only Ubuntu 20.04 and Ubuntu 22.04 are supported.»

---

# 👤 User Commands

Command| Description
"$about"| Display bot information
"$myvps"| View your VPS
"$manage"| VPS management guide
"$ping"| Check bot latency
"$help"| Display all commands

---

# 👑 Administrator Commands

Command| Description
"$create <ram> <cpu> <disk> <os> <@user>"| Create a VPS
"$list"| List all VPS
"$system"| Display host CPU, RAM & Disk usage
"$start vps <id>"| Start VPS
"$restart vps <id>"| Restart VPS
"$deletevps <id>"| Delete VPS
"$create-admin <@user>"| Add Bot Admin
"$delete-admin <@user>"| Remove Bot Admin
"$reset"| Reset VPS data

---

# 📦 Manual Installation

1️⃣ Clone Repository


```bash
git clone https://github.com/SKYDO234/SDT-BOT-v1
cd SDT-BOTV1
```

2️⃣ Update Package

```bash
apt update
```

3️⃣ Install Pip

```bash
apt install pip
```

4️⃣ Install Python Requirements

Run:

```bash
pip install -r requirements.txt
```

If you get a breaking system packages or externally-managed-environment error, run:

```bash
python3 -m pip install --break-system-packages -r requirements.txt
```

---

# ⚙️ Configuration

Open:

config.json

Configure the required values:

BOT_TOKEN
ADMIN_ID

---

# 👤 How To Get Your Admin ID

1. Open your Discord server.
2. Open your Discord profile.
3. Click the three dots.
4. Click Copy User ID.
5. Paste your Discord ID into "config.json".

«💡 If Copy User ID is not available, enable Developer Mode in Discord settings.»

---

# 🤖 How To Get Your Discord Bot Token

1. Open the Discord Developer Portal:

https://discord.com/developers/applications

2. Create a new application.
3. Open the Bot tab.
4. Configure your bot.
5. Enable all three Privileged Gateway Intents.
6. Click Reset Token.
7. Copy your bot token.
8. Paste it into "config.json".

⚠️ Never share your Discord bot token.

---

# 🌐 Tailscale Login

SDT-BOT V1 does not require a Tailscale Auth Key.

Instead, SDT-BOT V1 uses the Tailscale login/authentication link.

When Tailscale requires authentication:

1. Start the bot.
2. Follow the Tailscale login link provided by the setup.
3. Open the link in your browser.
4. Log in to your Tailscale account.
5. Complete the authentication.
6. Return to your VPS and continue the setup.

🔐 No Tailscale Auth Key needs to be added to "config.json".

---

# ▶️ Start The Bot

After completing the configuration, run:

```bash
python3 bot.py
```

The bot will start and connect to Discord.

---

# 🌐 IPv4 Instead Of SSH/TMate

SDT-BOT V1 is designed to provide an IPv4-based connection instead of generating an SSH/TMate key.

With Tailscale networking, your VPS can be accessed through its Tailscale IPv4 address.

# 🚀 No More SSH/TMate Key Hassle!

Create VPS → Tailscale Login → Get IPv4 → Connect

---

# 📊 VPS Information

Every VPS can contain information such as:

- 🆔 VPS ID
- 🐧 Operating System
- 💾 RAM
- 🖥️ CPU
- 💿 Disk
- 📡 IPv4 Address
- 👤 Owner
- 🟢 VPS Status

---

⚠️ Important

«SDT-BOT V1 currently supports Ubuntu 20.04 and Ubuntu 22.04 only.»

«Do not use unsupported operating systems.»

«Keep your Discord Bot Token private.»

«SDT-BOT V1 does not use a Tailscale Auth Key. Authentication is performed through the Tailscale login link.»

---

# 📁 Project Structure

SDT-BOTV1
│
├── bot.py
├── config.json
├── requirements.txt
├── README.md
└── ...

---

# ❤️ Credits

**Developer: SKYDO234**

Discord VPS IPv4 Management System

---

<div align="center">⭐ Star this repository if you like this project!

🚀 SDT-BOT V1 — IPv4 Instead of SSH/TMate

Made with ❤️ by SKYDO234

</div>
