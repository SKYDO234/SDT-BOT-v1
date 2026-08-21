# <div align="center">🚀 SDT-BOT V1

**Powerful Discord VPS Access Bot**

Get a public IPv4 address for your VPS directly through Discord instead of using SSH/TMate keys.

# 🌐 Tailscale Powered • ⚡ Fast • 🔐 Secure • 🤖 Discord Based

![Python] (https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)
![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?style=for-the-badge&logo=discord)
![Linux] (https://img.shields.io/badge/Linux-Ubuntu%20%7C%20Debian-black?style=for-the-badge&logo=linux)
! [Tailscale](https://img.shields.io/badge/Tailscale-IPv4-blue?style=for-the-badge)

</div>---

# ✨ Features

- 🌐 IPv4 Address Instead of SSH/TMate
- 🤖 Discord VPS Management
- 🔐 Tailscale Authentication
- 👑 Admin Permission System
- ⚡ Fast & Lightweight
- 🐧 Linux VPS Support
- 🛠️ Simple Configuration
- 📡 Tailscale-Based Networking

---

# 🐧 Supported Systems

SDT-BOT V1 is designed to run on Linux VPS environments.

Operating System| Status
Ubuntu| ✅
Debian| ✅
Other Linux Distributions| ⚠️

---

# 👤 Commands

SDT-BOT V1 provides Discord commands for interacting with the VPS and its networking system.

«The exact commands available depend on the version of the bot installed.»

---

# 📦 Manual Installation

1️⃣ Clone Repository

git clone https://github.com/SKYDO234/SDT-BOTV1
cd SDT-BOTV1

2️⃣ Update Packages

apt update

3️⃣ Install Pip

apt install pip

4️⃣ Install Python Requirements

Run:

pip install -r requirements.txt

If you get a breaking system packages / externally-managed-environment error, run:

python3 -m pip install --break-system-packages -r requirements.txt

---

⚙️ Configuration

After installing the requirements, open:

config.json

Configure all required values, including:

ADMIN_ID
BOT_TOKEN
TAILSCALE_AUTH_KEY

---

👑 How To Get Admin ID

1. Open your Discord server.
2. Open your Discord profile.
3. Click the three dots.
4. Select Copy User ID.
5. Paste the ID into "config.json".

«If Copy User ID does not appear, enable Developer Mode in Discord settings.»

---

🤖 How To Get Discord Bot Token

1️⃣ Open Discord Developer Portal

Go to:

https://discord.com/developers/applications

2️⃣ Create Your Bot

1. Create a new application.
2. Open the Bot tab.
3. Create/configure your bot.
4. Enable the required three Privileged Gateway Intents.
5. Click Reset Token.
6. Copy your bot token.
7. Paste it into "config.json".

⚠️ Never share your Discord bot token publicly.

---

🌐 How To Get Tailscale Auth Key

1️⃣ Open Tailscale

Open the Tailscale website and log into your account.

2️⃣ Open Settings

1. Click the three-line menu.
2. Open Settings.
3. Go to Keys.
4. Select Auth Keys.
5. Create a new authentication key.
6. Enable Reusable if required by your setup.
7. Click Create.
8. Copy the generated auth key.
9. Paste it into "config.json".

⚠️ Keep your Tailscale auth key private.

---

▶️ Start The Bot

After configuring "config.json", start SDT-BOT V1 with:

python3 bot.py

If the configuration is correct, the bot will start and connect to Discord.

---

🌐 IPv4 Access

Unlike traditional setups that provide an SSH/TMate key, SDT-BOT V1 is designed around Tailscale networking to provide an IPv4 address for accessing your VPS.

This makes the connection process easier and removes the need to rely on a TMate session for the VPS connection.

---

📁 Project Structure

SDT-BOTV1
│
├── bot.py
├── config.json
├── requirements.txt
├── README.md
└── ...

---

⚠️ Important

«Keep your Discord Bot Token and Tailscale Auth Key private.

Never upload "config.json" containing your real credentials to GitHub.

If a token or key is accidentally exposed, revoke/reset it immediately.»

---

❤️ Credits

Developer: SKYDO234

Discord VPS IPv4 Management System

---

<div align="center">⭐ Star this repository if you like this project!

🚀 SDT-BOT V1 — IPv4 Instead of SSH/TMate

Made with ❤️ by SKYDO234

</div>
