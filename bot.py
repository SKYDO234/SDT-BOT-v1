import os
import sys
import json
import time
import re
import secrets
import string
import asyncio
import logging
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
        "TAILSCALE_AUTHKEY": "tskey-auth-YOUR_TAILSCALE_AUTH_KEY_HERE"
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(default_config, f, indent=4)
    logging.info(f"Created initial {CONFIG_FILE}. Please update it with valid keys.")

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

# Initialize Database
def load_db():
    if not os.path.exists(DB_FILE):
        return {"vps": {}, "admins": config.get("ADMIN_IDS", []), "antinuke": config.get("ANTINUKE_ENABLED", True)}
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if "admins" not in data:
                data["admins"] = config.get("ADMIN_IDS", [])
            if "antinuke" not in data:
                data["antinuke"] = config.get("ANTINUKE_ENABLED", True)
            return data
    except json.JSONDecodeError:
        return {"vps": {}, "admins": config.get("ADMIN_IDS", []), "antinuke": config.get("ANTINUKE_ENABLED", True)}

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
# TAILSCALE & SSH SETUP ENGINE
# ---------------------------------------------------------
def _setup_tailscale_sync(container_id: str, auth_key: str, root_password: str) -> str:
    container = docker_client.containers.get(container_id)
    
    # Step 1: Install dependencies, configure SSH & root login
    install_cmd = (
        "bash -c 'export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y -qq curl iproute2 iptables openssh-server >/dev/null 2>&1 && "
        f"echo \"root:{root_password}\" | chpasswd && "
        "sed -i \"s/#PermitRootLogin.*/PermitRootLogin yes/g\" /etc/ssh/sshd_config && "
        "sed -i \"s/PermitRootLogin.*/PermitRootLogin yes/g\" /etc/ssh/sshd_config && "
        "sed -i \"s/#PasswordAuthentication.*/PasswordAuthentication yes/g\" /etc/ssh/sshd_config && "
        "sed -i \"s/PasswordAuthentication.*/PasswordAuthentication yes/g\" /etc/ssh/sshd_config && "
        "mkdir -p /var/run/tailscale /var/lib/tailscale /var/run/sshd && "
        "ssh-keygen -A && "
        "curl -fsSL https://tailscale.com/install.sh | sh >/dev/null 2>&1'"
    )
    res = container.exec_run(install_cmd)
    if res.exit_code != 0:
        raise RuntimeError(f"Package installation failed: {res.output.decode('utf-8', errors='ignore')}")

    # Step 2: Start SSH daemon
    ssh_start = container.exec_run("/usr/sbin/sshd")
    if ssh_start.exit_code != 0:
        raise RuntimeError(f"Failed to start SSH server: {ssh_start.output.decode('utf-8', errors='ignore')}")

    # Step 3: Launch Tailscale daemon in background
    start_daemon_cmd = (
        "bash -c 'nohup tailscaled --state=/var/lib/tailscale/tailscaled.state "
        "--socket=/var/run/tailscale/tailscaled.sock --tun=userspace-networking > /dev/null 2>&1 &'"
    )
    container.exec_run(start_daemon_cmd)

    # Step 4: Poll until socket exists
    socket_ready = False
    for _ in range(15):
        check_sock = container.exec_run("test -S /var/run/tailscale/tailscaled.sock")
        if check_sock.exit_code == 0:
            socket_ready = True
            break
        time.sleep(1)

    if not socket_ready:
        raise RuntimeError("Tailscale daemon socket failed to initialize inside container.")

    # Step 5: Convert hostname to valid DNS label
    clean_hostname = container.name.replace("_", "-")

    # Step 6: Authenticate Tailscale
    up_cmd = f"tailscale --socket=/var/run/tailscale/tailscaled.sock up --authkey={auth_key} --hostname={clean_hostname}"
    res_up = container.exec_run(up_cmd)
    if res_up.exit_code != 0:
        raise RuntimeError(f"Tailscale authentication failed: {res_up.output.decode('utf-8', errors='ignore')}")

    # Step 7: Fetch IPv4 Address
    ip_cmd = "tailscale --socket=/var/run/tailscale/tailscaled.sock ip -4"
    for _ in range(10):
        res_ip = container.exec_run(ip_cmd)
        ip_str = res_ip.output.decode("utf-8", errors="ignore").strip()
        if res_ip.exit_code == 0 and ip_str:
            return ip_str
        time.sleep(2)

    raise TimeoutError("Failed to fetch Tailscale IPv4 address.")

async def setup_tailscale_container(container, auth_key: str, root_password: str) -> str:
    return await asyncio.to_thread(_setup_tailscale_sync, container.id, auth_key, root_password)

# ---------------------------------------------------------
# DOCKER PROVISIONING ENGINE
# ---------------------------------------------------------
def _build_and_run_sync(os_type: str, ram_bytes: int, cpu_cores: int, disk_bytes: int, container_name: str):
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

    if os_upper not in image_map:
        raise ValueError(f"Unsupported OS version: {os_type}")

    image_tag = image_map[os_upper]

    try:
        docker_client.images.get(image_tag)
    except docker.errors.ImageNotFound:
        logging.info(f"Image {image_tag} not found locally. Pulling from Docker Hub...")
        docker_client.images.pull(image_tag)

    container = docker_client.containers.run(
        image=image_tag,
        name=container_name,
        command="tail -f /dev/null",
        detach=True,
        tty=True,
        stdin_open=True,
        mem_limit=ram_bytes,
        nano_cpus=nano_cpus,
        volumes={f"{data_dir}/{container_name}": {"bind": "/data", "mode": "rw"}},
        cap_add=["NET_ADMIN", "SYS_ADMIN"],
        devices=["/dev/net/tun:/dev/net/tun"] if os.path.exists("/dev/net/tun") else None
    )
    return container

async def build_and_run_vps(os_type: str, ram_bytes: int, cpu_cores: int, disk_bytes: int, container_name: str):
    return await asyncio.to_thread(_build_and_run_sync, os_type, ram_bytes, cpu_cores, disk_bytes, container_name)

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
                f"**Tailscale IPv4:** `{info.get('ipv4', 'N/A')}`\n"
                f"**SSH User:** `root` | **Password:** `{info.get('password', 'N/A')}`"
            ),
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="create")
@is_admin()
async def cmd_create(ctx, ram: str, cpu: int, disk: str, os_type: str, user: discord.Member):
    """Command syntax: $create <ram> <cpu> <disk> <os> <user_id>"""
    auth_key = config.get("TAILSCALE_AUTHKEY")
    if not auth_key or auth_key == "tskey-auth-YOUR_TAILSCALE_AUTH_KEY_HERE":
        await ctx.send("❌ **Config Error:** Missing or default `TAILSCALE_AUTHKEY` in `config.json`.")
        return

    try:
        ram_bytes = parse_size_to_bytes(ram)
        disk_bytes = parse_size_to_bytes(disk)
    except ValueError as e:
        await ctx.send(f"❌ **Parameter Error:** {e}")
        return

    os_upper = os_type.upper()
    status_msg = await ctx.send(f"⏳ **[1/3]** Creating `{os_upper}` container for {user.mention}...")
    
    container_name = f"vps-{user.id}-{int(time.time())}"
    root_password = generate_password()

    try:
        container = await asyncio.wait_for(
            build_and_run_vps(os_upper, ram_bytes, cpu, disk_bytes, container_name),
            timeout=90.0
        )

        await status_msg.edit(content="⏳ **[2/3]** Configuring SSH & Tailscale networking...")

        tailscale_ip = await asyncio.wait_for(
            setup_tailscale_container(container, auth_key, root_password),
            timeout=120.0
        )

        await status_msg.edit(content=f"⏳ **[3/3]** Finalizing deployment for {user.mention}...")

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
            "ipv4": tailscale_ip,
            "password": root_password,
            "status": "RUNNING",
            "created_at": datetime.utcnow().isoformat()
        }
        save_db(db)

        dm_embed = discord.Embed(title="🚀 Your Tailscale VPS is Live!", color=discord.Color.green())
        dm_embed.add_field(name="Instance ID", value=f"`{vps_id}`", inline=True)
        dm_embed.add_field(name="Allocated RAM", value=f"`{ram}`", inline=True)
        dm_embed.add_field(name="Allocated vCPU", value=f"`{cpu} Core(s)`", inline=True)
        dm_embed.add_field(name="Disk Storage", value=f"`{disk}`", inline=True)
        dm_embed.add_field(name="OS Distribution", value=f"`{os_upper}`", inline=True)
        dm_embed.add_field(name="SSH Credentials", value=f"**Host:** `{tailscale_ip}`\n**Port:** `22`\n**User:** `root`\n**Password:** `{root_password}`", inline=False)

        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await status_msg.edit(content=f"✅ **VPS Provisioned Successfully!**\n**ID:** `{vps_id}`\n**Assigned To:** {user.mention}\n**IPv4:** `{tailscale_ip}`\n**Root Password:** `{root_password}`")

    except Exception as err:
        logging.error(f"Error provisioning VPS: {err}", exc_info=True)
        await status_msg.edit(content=f"❌ **Deployment Failed:** `{err}`")

if __name__ == "__main__":
    bot.run(config.get("TOKEN"))
