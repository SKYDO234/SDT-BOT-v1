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

if not os.path.exists(CONFIG_FILE):
    default_config = {
        "TOKEN": "YOUR_DISCORD_BOT_TOKEN_HERE",
        "PREFIX": "$",
        "ADMIN_IDS": [],
        "ANTINUKE_ENABLED": True,
        "DEFAULT_DATA_DIR": "./vps_data"
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(default_config, f, indent=4)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

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

try:
    docker_client = docker.from_env()
    logging.info("Connected to Docker daemon successfully.")
except Exception as err:
    logging.error(f"Failed to connect to Docker daemon: {err}")
    docker_client = None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=config.get("PREFIX", "$"), intents=intents)

def generate_password(length=14):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def parse_size_to_bytes(size_str: str) -> int:
    size_str = size_str.lower().strip()
    match = re.match(r"^(\d+)([mg])$", size_str)
    if not match:
        raise ValueError("Invalid format. Use numbers followed by 'm' or 'g' (e.g., 512m, 20g, 100g).")
    num, unit = match.groups()
    num = int(num)
    bytes_val = num * 1024 * 1024 if unit == "m" else num * 1024 * 1024 * 1024
    if bytes_val < 256 * 1024 * 1024:
        raise ValueError("Memory allocation too small. Specify at least 256m.")
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

def get_normalized_os(os_input: str) -> tuple:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", os_input).upper()
    cleaned = cleaned.replace("DEBAIN", "DEBIAN")
    
    mapping = {
        "UBUNTU2204": "ubuntu:22.04",
        "UBUNTU2004": "ubuntu:20.04",
        "DEBIAN10": "debian:10",
        "DEBIAN11": "debian:11",
        "DEBIAN12": "debian:12",
        "DEBIAN13": "debian:13"
    }
    
    if cleaned in mapping:
        return cleaned, mapping[cleaned]
    raise ValueError(f"Unsupported OS version: `{os_input}`. Supported: Ubuntu 20.04/22.04, Debian 10/11/12/13.")

# ---------------------------------------------------------
# RELIABLE TAILSCALE & SSH SETUP ENGINE
# ---------------------------------------------------------
def _setup_tailscale_sync(container_id: str, root_password: str, os_key: str) -> str:
    container = docker_client.containers.get(container_id)
    
    # Initialize TUN device inside container environment
    tun_fix = "mkdir -p /dev/net && mknod /dev/net/tun c 10 200 2>/dev/null || true && chmod 600 /dev/net/tun"
    container.exec_run(f"bash -c '{tun_fix}'")

    # Install packages and start SSH server
    setup_script = f"""
    export DEBIAN_FRONTEND=noninteractive
    if [ "{os_key}" = "DEBIAN10" ] || [ "{os_key}" = "DEBIAN11" ]; then
        sed -i 's/deb.debian.org/archive.debian.org/g' /etc/apt/sources.list
        sed -i 's/security.debian.org/archive.debian.org/g' /etc/apt/sources.list
        sed -i '/updates/d' /etc/apt/sources.list
        echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99no-check
        echo 'Acquire::AllowInsecureRepositories "true";' >> /etc/apt/apt.conf.d/99no-check
    fi
    apt-get update -y -o Acquire::AllowInsecureRepositories=true >/dev/null 2>&1
    apt-get install -y --allow-unauthenticated curl openssh-server iptables iproute2 >/dev/null 2>&1
    echo "root:{root_password}" | chpasswd
    mkdir -p /var/run/sshd /var/run/tailscale /var/lib/tailscale
    ssh-keygen -A >/dev/null 2>&1
    /usr/sbin/sshd
    curl -fsSL https://tailscale.com/install.sh | sh >/dev/null 2>&1
    """
    container.exec_run(f"bash -c '{setup_script}'")

    # Start tailscaled in userspace mode to avoid network driver locks
    start_daemon = (
        "nohup tailscaled --state=/var/lib/tailscale/tailscaled.state "
        "--socket=/var/run/tailscale/tailscaled.sock --tun=userspace-networking >/tmp/tailscale.log 2>&1 &"
    )
    container.exec_run(f"bash -c '{start_daemon}'")

    time.sleep(2)

    clean_hostname = container.name.replace("_", "-")

    # Launch tailscale up and stream output to capture Auth URL instantly
    up_cmd = f"tailscale --socket=/var/run/tailscale/tailscaled.sock up --hostname={clean_hostname} --reset"
    exec_res = container.exec_run(f"bash -c '{up_cmd}'", stream=True)

    auth_url = None
    start_time = time.time()

    for chunk in exec_res.output:
        line = chunk.decode("utf-8", errors="ignore")
        match = re.search(r"https://[^\s]+\.tailscale\.com[^\s]*", line)
        if not match:
            match = re.search(r"https://login\.tailscale\.com/a/[a-zA-Z0-9]+", line)
        
        if match:
            auth_url = match.group(0)
            break
            
        if time.time() - start_time > 15:
            break

    if auth_url:
        return auth_url

    # Fallback to tailscale log inspection
    log_check = container.exec_run("cat /tmp/tailscale.log").output.decode("utf-8", errors="ignore")
    match_log = re.search(r"https://[^\s]+\.tailscale\.com[^\s]*", log_check)
    if not match_log:
        match_log = re.search(r"https://login\.tailscale\.com/a/[a-zA-Z0-9]+", log_check)

    if match_log:
        return match_log.group(0)

    raise RuntimeError("Failed to capture Tailscale link. Verify your VPS host network allows outgoing HTTPS.")

async def setup_tailscale_container(container, root_password: str, os_key: str) -> str:
    return await asyncio.to_thread(_setup_tailscale_sync, container.id, root_password, os_key)

# ---------------------------------------------------------
# UNLIMITED DOCKER RESOURCE PROVISIONING
# ---------------------------------------------------------
def _build_and_run_sync(image_tag: str, ram_bytes: int, cpu_cores: int, disk_bytes: int, container_name: str):
    data_dir = os.path.abspath(config.get("DEFAULT_DATA_DIR", "./vps_data"))
    os.makedirs(data_dir, exist_ok=True)
    
    nano_cpus = int(cpu_cores * 1_000_000_000)

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
        privileged=True
    )
    return container, cpu_cores, ram_bytes

async def build_and_run_vps(image_tag: str, ram_bytes: int, cpu_cores: int, disk_bytes: int, container_name: str):
    return await asyncio.to_thread(_build_and_run_sync, image_tag, ram_bytes, cpu_cores, disk_bytes, container_name)

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
                f"**OS:** `{info['os']}` | **Status:** `{info.get('status', 'PENDING_AUTH')}`\n"
                f"**CPU:** `{info['cpu']} Core(s)` | **RAM:** `{info['ram']}` | **Disk:** `{info['disk']}`\n"
                f"**SSH User:** `root` | **Password:** `{info.get('password', 'N/A')}`"
            ),
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="create")
@is_admin()
async def cmd_create(ctx, ram: str, cpu: int, disk: str, os_type: str, user: discord.Member):
    """Syntax: $create <ram> <cpu> <disk> <os> <user>"""
    try:
        ram_bytes = parse_size_to_bytes(ram)
        disk_bytes = parse_size_to_bytes(disk)
        os_key, image_tag = get_normalized_os(os_type)
    except ValueError as e:
        await ctx.send(f"❌ **Parameter Error:** {e}")
        return

    status_msg = await ctx.send(f"⏳ **[1/3]** Allocating `{ram}` RAM, `{cpu}` CPU Cores for {user.mention}...")
    
    container_name = f"vps-{user.id}-{int(time.time())}"
    root_password = generate_password()

    try:
        container, actual_cpu, actual_ram = await asyncio.wait_for(
            build_and_run_vps(image_tag, ram_bytes, cpu, disk_bytes, container_name),
            timeout=120.0
        )

        await status_msg.edit(content="⏳ **[2/3]** Generating Tailscale Link...")

        login_url = await asyncio.wait_for(
            setup_tailscale_container(container, root_password, os_key),
            timeout=120.0
        )

        await status_msg.edit(content=f"⏳ **[3/3]** Sending details to {user.mention} via DM...")

        vps_id = container.id[:10]

        dm_embed = discord.Embed(
            title="🚀 Your Custom VPS is Ready!",
            description="Click the link below to authenticate and attach this VPS to your Tailscale network.",
            color=discord.Color.blue()
        )
        dm_embed.add_field(name="Instance ID", value=f"`{vps_id}`", inline=True)
        dm_embed.add_field(name="Allocated RAM", value=f"`{ram}`", inline=True)
        dm_embed.add_field(name="Allocated vCPU", value=f"`{actual_cpu} Core(s)`", inline=True)
        dm_embed.add_field(name="Disk Storage", value=f"`{disk}`", inline=True)
        dm_embed.add_field(name="OS Distribution", value=f"`{os_key}`", inline=True)
        dm_embed.add_field(name="🔑 Tailscale Auth Link", value=f"[**Authenticate Tailscale Node**]({login_url})\n`{login_url}`", inline=False)
        dm_embed.add_field(name="🔐 SSH Credentials", value=f"**Port:** `22`\n**User:** `root`\n**Password:** `{root_password}`", inline=False)

        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            container.stop()
            container.remove()
            await status_msg.edit(content=f"❌ **Deployment Aborted:** Could not DM {user.mention}. Enable Direct Messages.")
            return

        db = load_db()
        db["vps"][vps_id] = {
            "container_id": container.id,
            "container_name": container_name,
            "owner_id": user.id,
            "owner_tag": str(user),
            "ram": ram,
            "cpu": actual_cpu,
            "disk": disk,
            "os": os_key,
            "password": root_password,
            "status": "PENDING_AUTH",
            "created_at": datetime.utcnow().isoformat()
        }
        save_db(db)

        await status_msg.edit(content=f"✅ **VPS Provisioned Successfully!**\n**ID:** `{vps_id}`\n**Assigned To:** {user.mention}\n📩 **Login link sent to Direct Messages.**")

    except Exception as err:
        logging.error(f"Error provisioning VPS: {err}", exc_info=True)
        await status_msg.edit(content=f"❌ **Deployment Failed:** `{err}`")

if __name__ == "__main__":
    bot.run(config.get("TOKEN"))
  
