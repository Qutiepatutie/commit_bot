""" import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

from config import REPO_FILE

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents)

def save_repo(repo):
    with open(REPO_FILE, "w") as f:
        f.write(repo)

def load_repo():
    if not os.path.exists(REPO_FILE):
        return None
    
    with open(REPO_FILE, "r") as f:
        return f.read().strip()
    
def remove_repo():
    if os.path.exists(REPO_FILE):
        os.remove(REPO_FILE)

@bot.command()
async def connect(ctx, repo: str):
    save_repo(repo)
    await ctx.send(f"Connected to {repo.split('/')[-1]}")


@bot.command()
async def disconnect(ctx):
    remove_repo()
    await ctx.send(f"Disconnected to current repository")

@bot.command()
async def status(ctx):
    repo = load_repo()

    if repo:
        await ctx.send(f"Watching: {repo.split('/')[-1]}")
    else:
        await ctx.send("Not watching any repository.")

bot.run(token)
 """
import os
import hmac
import hashlib
import discord
import json
from discord.ext import commands
from aiohttp import web
from dotenv import load_dotenv

from config import REPO_FILE

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
GITHUB_SECRET = os.getenv("GITHUB_SECRET")

# -----------------------
# Discord bot setup
# -----------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="$", intents=intents)


# -----------------------
# repo file helpers
# -----------------------
def save_repo(repo):
    with open(REPO_FILE, "w") as f:
        f.write(repo)


def load_repo():
    if not os.path.exists(REPO_FILE):
        return None

    with open(REPO_FILE, "r") as f:
        return f.read().strip()


def remove_repo():
    if os.path.exists(REPO_FILE):
        os.remove(REPO_FILE)


# -----------------------
# Bot commands
# -----------------------
@bot.command()
async def connect(ctx, repo: str):
    save_repo(repo)
    await ctx.send(f"Connected to {repo}")


@bot.command()
async def disconnect(ctx):
    remove_repo()
    await ctx.send("Disconnected current repository")


@bot.command()
async def status(ctx):
    repo = load_repo()
    if repo:
        await ctx.send(f"Watching: {repo}")
    else:
        await ctx.send("Not watching any repository.")


# -----------------------
# GitHub signature verify
# -----------------------
def verify_signature(data, signature):
    if not GITHUB_SECRET:
        return True

    mac = hmac.new(
        GITHUB_SECRET.encode(),
        msg=data,
        digestmod=hashlib.sha256
    )

    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


# -----------------------
# GitHub webhook endpoint
# -----------------------
async def github_webhook(request):
    repo = load_repo()
    if not repo:
        return web.Response(text="No repo configured")

    signature = request.headers.get("X-Hub-Signature-256")
    raw_body = await request.read()

    if signature and not verify_signature(raw_body, signature):
        return web.Response(status=403)

    payload = json.loads(raw_body.decode())

    event = request.headers.get("X-GitHub-Event")

    if event == "push":
        full_repo = payload["repository"]["full_name"]

        if full_repo != repo:
            return web.Response(text="Ignored repo")

        pusher = payload["pusher"]["name"]
        commits = payload["commits"]

        lines = []
        for c in commits[:5]:
            sha = c["id"][:7]
            msg = c["message"].split("\n")[0]
            url = c["url"]
            lines.append(f"[`{sha}`]({url}) {msg}")

        embed = discord.Embed(
            title=f"📦 New Push to {full_repo}",
            description="\n".join(lines),
            color=discord.Color.green()
        )

        embed.set_author(name=pusher)
        embed.set_footer(text=f"{len(commits)} commit(s)")

        channel = await bot.fetch_channel(CHANNEL_ID)

        if channel:
            await channel.send(embed=embed)

    return web.Response(text="OK")


# -----------------------
# start webhook server
# -----------------------
async def start_webserver():
    app = web.Application()
    app.router.add_post("/webhook", github_webhook)

    runner = web.AppRunner(app)
    await runner.setup()


    port = int(os.environ.get("PORT", 10000))

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Webhook listening on :{port}")


# -----------------------
# bot startup
# -----------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await start_webserver()


bot.run(TOKEN)