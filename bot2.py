import os
import sys
import json
import time
import re
import secrets
import string
import asyncio
import logging
import urllib.request
from datetime import datetime
import discord
from discord.ext import commands
import docker

# ---------------------------------------------------------
# LOGGING SETUP
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

CONFIG_FILE = "config.json"
DB_FILE = "vps_db.json"

# Load / Initialize Configuration
if not os.path.exists(CONFIG_FILE):
    default_config = {
        "TOKEN": "YOUR_DISCORD_BOT_TOKEN_HERE",
        "PREFIX": "$",
        "ADMIN_IDS": [],
        "ANTINUKE_ENABLED": True,
        "DEFAULT_DATA_DIR": "./vps_data",
        "BASE_SSH_PORT": 2200
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(default_config, f, indent=4)
    logging.info(f"Created initial {CONFIG_FILE}. Please update it with valid keys.")

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

# Helper function to get Host Public IP
def get_public_ip():
    try:
        return urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
    except Exception:
        return "127.0.0.1"

HOST_IPV4 = get_public_ip()

# Initialize Database
def load_db():
    if not os.path.exists(DB_FILE):
        return {"vps": {}, "admins": config.get("ADMIN_IDS", []), "port_counter": config.get("BASE_SSH_PORT", 2200)}
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if "admins" not in data:
                data["admins"] = config.get("ADMIN_IDS", [])
            if "port_counter" not in data:
                data["port_counter"] = config.get("BASE_SSH_PORT", 2200)
            return data
    except json.JSONDecodeError:
        return {"vps": {}, "admins": config.get("ADMIN_IDS", []), "port_counter": config.get("BASE_SSH_PORT", 2200)}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Initialize Docker Client
try:
    docker_client = docker.from_env()
    logging.info("Connected to Docker daemon successfully.")
except Exception as err:
    logging.error(f"Failed to connect to Docker daemon: {err}")
    docker_client = None

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=config.get("PREFIX", "$"), intents=intents)

# Helper Functions
def generate_password(length=14):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def parse_size_to_bytes(size_str: str) -> int:
    size_str = size_str.lower().strip()
    match = re.match(r"^(\d+)([mg])$", size_str)
    if not match:
        raise ValueError("Invalid format. Use numbers followed by 'm' or 'g' (e.g., 512m, 2g).")
    num, unit = match.groups()
    num = int(num)
    bytes_val = num * 1024 * 1024 if unit == "m" else num * 1024 * 1024 * 1024
    if bytes_val < 256 * 1024 * 1024:
        raise ValueError("Memory allocation too small. Specify at least 256m or 1g.")
    return bytes_val

def is_admin():
    async def predicate(ctx):
        db = load_db()
        admins = db.get("admins", [])
        if ctx.author.id in admins or ctx.author.guild_permissions.administrator:
            return True
        await ctx.send("❌ **Access Denied:** You do not have permission to execute this command.")
        return False
    return commands.check(predicate)

# ---------------------------------------------------------
# DOCKER PROVISIONING ENGINE (SSH & PORT MAPPING)
# ---------------------------------------------------------
def _build_and_run_sync(os_type: str, ram_bytes: int, cpu_cores: int, disk_bytes: int, container_name: str, host_ssh_port: int, root_password: str):
    os_upper = os_type.upper()
    data_dir = os.path.abspath(config.get("DEFAULT_DATA_DIR", "./vps_data"))
    os.makedirs(data_dir, exist_ok=True)
    nano_cpus = int(cpu_cores * 1_000_000_000)

    image_map = {
        "UBUNTU22.04": "ubuntu:22.04",
        "UBUNTU20.04": "ubuntu:20.04",
        "DEBIAN10": "debian:10",
        "DEBIAN11": "debian:11",
        "DEBIAN12": "debian:12",
        "DEBIAN13": "debian:13"
    }

    # Allow custom Docker Hub images or fallback to standard image map
    image_tag = image_map.get(os_upper, os_type.lower())

    try:
        docker_client.images.get(image_tag)
    except docker.errors.ImageNotFound:
        logging.info(f"Image {image_tag} not found locally. Pulling from Docker Hub...")
        docker_client.images.pull(image_tag)

    # Launch container mapping host port to container SSH port 22
    container = docker_client.containers.run(
        image=image_tag,
        name=container_name,
        command="tail -f /dev/null",
        detach=True,
        tty=True,
        stdin_open=True,
        mem_limit=ram_bytes,
        nano_cpus=nano_cpus,
        ports={'22/tcp': host_ssh_port},
        volumes={f"{data_dir}/{container_name}": {"bind": "/data", "mode": "rw"}},
        cap_add=["NET_ADMIN", "SYS_ADMIN"]
    )

    # Install OpenSSH server, set root password, enable login, and start sshd
    setup_cmd = (
        "bash -c 'export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y -qq openssh-server curl iproute2 >/dev/null 2>&1 && "
        f"echo \"root:{root_password}\" | chpasswd && "
        "sed -i \"s/#PermitRootLogin.*/PermitRootLogin yes/g\" /etc/ssh/sshd_config && "
        "sed -i \"s/PermitRootLogin.*/PermitRootLogin yes/g\" /etc/ssh/sshd_config && "
        "sed -i \"s/#PasswordAuthentication.*/PasswordAuthentication yes/g\" /etc/ssh/sshd_config && "
        "sed -i \"s/PasswordAuthentication.*/PasswordAuthentication yes/g\" /etc/ssh/sshd_config && "
        "mkdir -p /var/run/sshd && "
        "ssh-keygen -A && "
        "/usr/sbin/sshd'"
    )
    res = container.exec_run(setup_cmd)
    if res.exit_code != 0:
        raise RuntimeError(f"SSH configuration failed inside container: {res.output.decode('utf-8', errors='ignore')}")

    return container

async def build_and_run_vps(os_type: str, ram_bytes: int, cpu_cores: int, disk_bytes: int, container_name: str, host_ssh_port: int, root_password: str):
    return await asyncio.to_thread(_build_and_run_sync, os_type, ram_bytes, cpu_cores, disk_bytes, container_name, host_ssh_port, root_password)

# ---------------------------------------------------------
# BOT COMMANDS
# ---------------------------------------------------------
@bot.event
async def on_ready():
    logging.info(f"Bot online as {bot.user.name} ({bot.user.id})")

@bot.command(name="myvps")
async def cmd_myvps(ctx):
    db = load_db()
    user_vps = [(vps_id, info) for vps_id, info in db.get("vps", {}).items() if info.get("owner_id") == ctx.author.id]

    if not user_vps:
        await ctx.send("❌ **No active VPS instances found.**")
        return

    embed = discord.Embed(title="🖥️ Your Managed VPS Instances", color=discord.Color.green())
    for vps_id, info in user_vps:
        embed.add_field(
            name=f"Instance ID: {vps_id}",
            value=(
                f"**OS:** `{info['os']}` | **Status:** `{info.get('status', 'RUNNING')}`\n"
                f"**CPU:** `{info['cpu']} Core(s)` | **RAM:** `{info['ram']}` | **Disk:** `{info['disk']}`\n"
                f"**SSH Host:** `{info.get('host_ip', HOST_IPV4)}`\n"
                f"**SSH Port:** `{info.get('ssh_port')}`\n"
                f"**User:** `root` | **Password:** `{info.get('password')}`"
            ),
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="create")
@is_admin()
async def cmd_create(ctx, ram: str, cpu: int, disk: str, os_type: str, user: discord.Member):
    """Command syntax: $create <ram> <cpu> <disk> <os> <user_id>"""
    try:
        ram_bytes = parse_size_to_bytes(ram)
        disk_bytes = parse_size_to_bytes(disk)
    except ValueError as e:
        await ctx.send(f"❌ **Parameter Error:** {e}")
        return

    os_upper = os_type.upper()
    status_msg = await ctx.send(f"⏳ **[1/2]** Creating `{os_upper}` container for {user.mention}...")
    
    container_name = f"vps-{user.id}-{int(time.time())}"
    root_password = generate_password()

    # Get next available SSH port
    db = load_db()
    assigned_port = db.get("port_counter", 2200) + 1
    db["port_counter"] = assigned_port
    save_db(db)

    try:
        container = await asyncio.wait_for(
            build_and_run_vps(os_upper, ram_bytes, cpu, disk_bytes, container_name, assigned_port, root_password),
            timeout=120.0
        )

        await status_msg.edit(content=f"⏳ **[2/2]** Finalizing deployment for {user.mention}...")

        vps_id = container.id[:10]
        db = load_db()
        db["vps"][vps_id] = {
            "container_id": container.id,
            "container_name": container_name,
            "owner_id": user.id,
            "owner_tag": str(user),
            "ram": ram,
            "cpu": cpu,
            "disk": disk,
            "os": os_upper,
            "host_ip": HOST_IPV4,
            "ssh_port": assigned_port,
            "password": root_password,
            "status": "RUNNING",
            "created_at": datetime.utcnow().isoformat()
        }
        save_db(db)

        dm_embed = discord.Embed(title="🚀 Your Docker VPS is Live!", color=discord.Color.green())
        dm_embed.add_field(name="Instance ID", value=f"`{vps_id}`", inline=True)
        dm_embed.add_field(name="Allocated RAM", value=f"`{ram}`", inline=True)
        dm_embed.add_field(name="Allocated vCPU", value=f"`{cpu} Core(s)`", inline=True)
        dm_embed.add_field(name="Disk Storage", value=f"`{disk}`", inline=True)
        dm_embed.add_field(name="OS Distribution", value=f"`{os_upper}`", inline=True)
        dm_embed.add_field(
            name="🔑 Connection Details (Termux / PuTTY / Termius)",
            value=(
                f"**Host / IP:** `{HOST_IPV4}`\n"
                f"**Port:** `{assigned_port}`\n"
                f"**User:** `root`\n"
                f"**Password:** `{root_password}`\n\n"
                f"**SSH Command:**\n`ssh root@{HOST_IPV4} -p {assigned_port}`"
            ),
            inline=False
        )

        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await status_msg.edit(
            content=(
                f"✅ **VPS Provisioned Successfully!**\n"
                f"**ID:** `{vps_id}` | **Assigned To:** {user.mention}\n"
                f"**Connect Command:** `ssh root@{HOST_IPV4} -p {assigned_port}`\n"
                f"**Password:** `{root_password}`"
            )
        )

    except Exception as err:
        logging.error(f"Error provisioning VPS: {err}", exc_info=True)
        await status_msg.edit(content=f"❌ **Deployment Failed:** `{err}`")

if __name__ == "__main__":
    bot.run(config.get("TOKEN"))
