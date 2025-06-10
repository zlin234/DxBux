import discord
from discord.ext import commands, tasks
import json
import os
import random

# ------------------ BOT SETUP ------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='-', intents=intents)

# ------------------ BALANCE STORAGE ------------------

BALANCE_FILE = 'balances.json'

def load_balances():
    if not os.path.exists(BALANCE_FILE):
        with open(BALANCE_FILE, 'w') as f:
            json.dump({}, f)
    with open(BALANCE_FILE, 'r') as f:
        return json.load(f)

def save_balances(balances):
    with open(BALANCE_FILE, 'w') as f:
        json.dump(balances, f, indent=4)

def get_balance(user_id):
    balances = load_balances()
    return balances.get(str(user_id), 1000)

def set_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = amount
    save_balances(balances)

def add_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = balances.get(str(user_id), 1000) + amount
    save_balances(balances)

# ------------------ ADMIN CHECK DECORATOR ------------------

def is_admin():
    async def predicate(ctx):
        return any(role.name.lower() == "carrot" for role in ctx.author.roles)
    return commands.check(predicate)

# ------------------ COMMANDS ------------------

@bot.command(aliases=["setbalance"])
@is_admin()
async def setbal(ctx, amount: int, member: discord.Member = None):
    if amount < 0:
        await ctx.send("❌ Amount must be 0 or more.")
        return

    if member:
        set_balance(member.id, amount)
        await ctx.send(f"✅ Set {member.display_name}'s balance to {amount} coins.")
    else:
        balances = load_balances()
        for uid in balances:
            balances[uid] = balances.get(uid, 1000) + amount
        save_balances(balances)
        await ctx.send(f"✅ Added {amount} coins to all known users' balances.")

@bot.command()
async def balance(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    bal = get_balance(member.id)
    await ctx.send(f"💰 {member.display_name}'s balance: {bal} coins.")

@bot.command()
async def cf(ctx, amount: int):
    bal = get_balance(ctx.author.id)
    if amount <= 0:
        await ctx.send("❌ Bet must be greater than zero.")
        return
    if amount > bal:
        await ctx.send("❌ You don't have enough coins to bet that much.")
        return

    result = random.choice(["heads", "tails"])
    if result == "heads":
        add_balance(ctx.author.id, amount)
        await ctx.send(f"🎉 You won! The coin landed on {result}. You gained {amount} coins!")
    else:
        add_balance(ctx.author.id, -amount)
        await ctx.send(f"😢 You lost! The coin landed on {result}. You lost {amount} coins.")

# ------------------ DAILY ALLOWANCE ------------------

@tasks.loop(hours=24)
async def daily_allowance():
    await bot.wait_until_ready()
    balances = load_balances()
    for uid in balances:
        balances[uid] = balances.get(uid, 1000) + 100
    save_balances(balances)
    print("✅ Daily allowance of 100 coins added to all users.")

@daily_allowance.before_loop
async def before_daily_allowance():
    await bot.wait_until_ready()

# ------------------ EVENTS ------------------

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    daily_allowance.start()

# ------------------ RUN BOT ------------------

bot.run(os.getenv("DISCORD_TOKEN"))
