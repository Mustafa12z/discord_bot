import discord
from discord.ext import commands
import asyncio
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Set up intents (ensure that the Message Content Intent is enabled in your bot's settings)
intents = discord.Intents.default()
intents.message_content = True

# Create the bot instance with a command prefix
my_bot = commands.Bot(command_prefix="!", intents=intents)

# The permissions integer you want to implement:
PERMISSIONS_INT = 563226979264576

# Global list to store scheduled messages
scheduled_messages = []
next_schedule_id = 1

@my_bot.event
async def on_ready():
    # Generate the invite URL and print it to the command line
    invite_url = discord.utils.oauth_url(
        my_bot.user.id,
        permissions=discord.Permissions(PERMISSIONS_INT),
        scopes=["bot", "applications.commands"]
    )
    print("Invite URL:", invite_url)
    print(f"Logged in as {my_bot.user}.")

@my_bot.command()
async def invite(ctx):
    """Sends the invite URL with the custom permissions integer."""
    invite_url = discord.utils.oauth_url(
        my_bot.user.id,
        permissions=discord.Permissions(PERMISSIONS_INT),
        scopes=["bot", "applications.commands"]
    )
    await ctx.send(f"Invite me using this link: {invite_url}")

async def scheduled_message_task(sched_id, scheduled_time, content, channel):
    """Background task that waits until the scheduled time then sends the message."""
    now = datetime.datetime.now(datetime.timezone.utc)
    delay = (scheduled_time - now).total_seconds()
    if delay > 0:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return  # Task was cancelled
    await channel.send(content)
    # Remove the scheduled message from the list after sending
    global scheduled_messages
    scheduled_messages = [msg for msg in scheduled_messages if msg["id"] != sched_id]

@my_bot.command()
async def schedule(ctx):
    """Schedules a message to be sent at a specified future time with timezone adjustment."""
    global next_schedule_id, scheduled_messages

    def check(m):
        # Only accept responses from the command invoker in the same channel.
        return m.author == ctx.author and m.channel == ctx.channel

    # 1. Ask for the message to schedule.
    await ctx.send("What would you like your message to be?")
    msg_content = await my_bot.wait_for("message", check=check)

    # 2. Ask for the date/time and timezone offset until valid future time is provided.
    while True:
        await ctx.send("Enter the date and time for the message (Format: `YYYY-MM-DD HH:MM`):")
        msg_datetime = await my_bot.wait_for("message", check=check)
        try:
            scheduled_time = datetime.datetime.strptime(msg_datetime.content, "%Y-%m-%d %H:%M")
        except ValueError:
            await ctx.send("Invalid date format. Please use `YYYY-MM-DD HH:MM`.")
            continue

        await ctx.send("Enter the timezone offset from GMT in hours (e.g., +0 for GMT, -5 for EST, +3.5):")
        msg_tz = await my_bot.wait_for("message", check=check)
        try:
            tz_offset = float(msg_tz.content)
            tzinfo = datetime.timezone(datetime.timedelta(hours=tz_offset))
        except ValueError:
            await ctx.send("Invalid timezone offset. Please enter a number (e.g., +0, -5, 3.5).")
            continue

        # Attach the provided timezone and convert the time to UTC.
        scheduled_time = scheduled_time.replace(tzinfo=tzinfo)
        scheduled_time = scheduled_time.astimezone(datetime.timezone.utc)

        now = datetime.datetime.now(datetime.timezone.utc)
        delay = (scheduled_time - now).total_seconds()
        if delay <= 0:
            await ctx.send("The scheduled time is in the past! Please choose a future time.")
            continue
        break

    # 3. Ask for the channel to post the message in.
    await ctx.send("Mention the channel where the message should be sent:")
    msg_channel = await my_bot.wait_for("message", check=check)
    if msg_channel.channel_mentions:
        target_channel = msg_channel.channel_mentions[0]
    else:
        await ctx.send("No valid channel mentioned. Canceling scheduling.")
        return

    # Create a background task for the scheduled message.
    task = my_bot.loop.create_task(
        scheduled_message_task(next_schedule_id, scheduled_time, msg_content.content, target_channel)
    )
    scheduled_messages.append({
        "id": next_schedule_id,
        "author": ctx.author.name,
        "content": msg_content.content,
        "time": scheduled_time,
        "channel": target_channel,
        "task": task
    })
    await ctx.send(
        f"Message scheduled with ID {next_schedule_id} for {scheduled_time.strftime('%Y-%m-%d %H:%M')} GMT in {target_channel.mention}."
    )
    next_schedule_id += 1

@my_bot.command()
async def list(ctx):
    """Lists all scheduled messages."""
    if not scheduled_messages:
        await ctx.send("No scheduled messages.")
        return
    msg_lines = []
    for msg in scheduled_messages:
        time_str = msg["time"].strftime("%Y-%m-%d %H:%M GMT")
        line = f"ID {msg['id']} by {msg['author']} at {time_str} in {msg['channel'].mention}: {msg['content'][:30]}..."
        msg_lines.append(line)
    response = "\n".join(msg_lines)
    await ctx.send(f"Scheduled messages:\n{response}")

@my_bot.command()
async def delete(ctx):
    """Lists scheduled messages and deletes one based on its ID."""
    global scheduled_messages
    if not scheduled_messages:
        await ctx.send("No scheduled messages to delete.")
        return
    msg_lines = []
    for msg in scheduled_messages:
        time_str = msg["time"].strftime("%Y-%m-%d %H:%M GMT")
        line = f"ID {msg['id']} by {msg['author']} at {time_str} in {msg['channel'].mention}: {msg['content'][:30]}..."
        msg_lines.append(line)
    await ctx.send("Scheduled messages:\n" + "\n".join(msg_lines))
    await ctx.send("Enter the ID of the scheduled message you want to delete:")

    def check_id(m):
        return m.author == ctx.author and m.channel == ctx.channel

    msg_id = await my_bot.wait_for("message", check=check_id)
    try:
        del_id = int(msg_id.content)
    except ValueError:
        await ctx.send("Invalid ID. Cancellation of deletion.")
        return

    for msg in scheduled_messages:
        if msg["id"] == del_id:
            msg["task"].cancel()  # Cancel the scheduled task.
            scheduled_messages = [m for m in scheduled_messages if m["id"] != del_id]
            await ctx.send(f"Deleted scheduled message with ID {del_id}.")
            return

    await ctx.send("No scheduled message with that ID was found.")

# Run the bot using your environment variable for the token.
my_bot.run(os.environ["TOKEN"])

