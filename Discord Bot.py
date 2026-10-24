import discord
from discord.ext import commands
from collections import defaultdict, deque
from datetime import timedelta
import asyncio
import os
import time

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Anti-spam:
SPAM_MESSAGE_LIMIT = 5
SPAM_TIME_WINDOW = 5  # seconds

# Timeout lengths for repeat offenses
TIMEOUTS = [
    60,       # 1 minute
    300,      # 5 minutes
    1800,     # 30 minutes
    3600,     # 1 hour
]

# Put the words you want blocked here.
# Keep everything lowercase.
BLOCKED_WORDS = {
    "nigga",
    "nigger",
    "retard",
    "retarded",
    "nga",
    "nger",
    "niga",
    "niger",
}

MOD_LOG_CHANNEL = "𝖑𝖔𝖌𝖘"


# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# user_id -> timestamps
message_history = defaultdict(lambda: deque())

# user_id -> number of offenses
offenses = defaultdict(int)

# Prevent the same spam burst from triggering repeatedly
spam_cooldowns = set()


# =========================
# HELPERS
# =========================

def is_staff(member):
    perms = member.guild_permissions

    return (
        perms.administrator
        or perms.manage_messages
        or perms.moderate_members
    )


def contains_blocked_word(text):
    words = (
        text.lower()
        .replace(".", " ")
        .replace(",", " ")
        .replace("!", " ")
        .replace("?", " ")
        .split()
    )

    return any(word in BLOCKED_WORDS for word in words)


def get_timeout(user_id):
    offense_number = offenses[user_id]

    index = min(
        offense_number,
        len(TIMEOUTS) - 1
    )

    return TIMEOUTS[index]


async def send_mod_log(guild, member, reason, seconds):
    channel = discord.utils.get(
        guild.text_channels,
        name=MOD_LOG_CHANNEL
    )

    if channel is None:
        return

    embed = discord.Embed(
        title="⚠️ Automatic Moderation",
        description=f"{member.mention} was automatically timed out."
    )

    embed.add_field(
        name="Reason",
        value=reason,
        inline=False
    )

    embed.add_field(
        name="Timeout",
        value=f"{seconds} seconds",
        inline=False
    )

    embed.add_field(
        name="Total Offenses",
        value=str(offenses[member.id]),
        inline=False
    )

    await channel.send(embed=embed)


async def punish(member, reason):
    seconds = get_timeout(member.id)

    offenses[member.id] += 1

    try:
        await member.timeout(
            timedelta(seconds=seconds),
            reason=f"AutoMod: {reason}"
        )

        await send_mod_log(
            member.guild,
            member,
            reason,
            seconds
        )

    except discord.Forbidden:
        print(
            f"Couldn't timeout {member}. "
            "Check the bot's permissions/role position."
        )


# =========================
# EVENTS
# =========================

@bot.event
async def on_ready():
    print("=" * 40)
    print(f"Logged in as {bot.user}")
    print("Anti-Spam: ENABLED")
    print("Word Filter: ENABLED")
    print("=" * 40)


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if not message.guild:
        return

    # Don't moderate staff
    if is_staff(message.author):
        await bot.process_commands(message)
        return

    user_id = message.author.id

    # =========================
    # BLOCKED WORD DETECTION
    # =========================

    if contains_blocked_word(message.content):

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        await punish(
            message.author,
            "Blocked language"
        )

        return

    # =========================
    # SPAM DETECTION
    # =========================

    now = time.monotonic()

    history = message_history[user_id]

    history.append(now)

    # Remove old messages from tracking
    while history and now - history[0] > SPAM_TIME_WINDOW:
        history.popleft()

    if len(history) >= SPAM_MESSAGE_LIMIT:

        if user_id not in spam_cooldowns:

            spam_cooldowns.add(user_id)

            try:
                await message.channel.purge(
                    limit=SPAM_MESSAGE_LIMIT + 3,
                    check=lambda m: m.author.id == user_id
                )
            except discord.Forbidden:
                pass

            await punish(
                message.author,
                f"Spam ({len(history)} messages in "
                f"{SPAM_TIME_WINDOW} seconds)"
            )

            history.clear()

            # Don't trigger again immediately
            await asyncio.sleep(SPAM_TIME_WINDOW)

            spam_cooldowns.discard(user_id)

        return

    await bot.process_commands(message)

# =========================
# RUN
# =========================

if not TOKEN:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN environment variable isn't set."
    )

bot.run(TOKEN)