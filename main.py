import discord
from discord.ext import commands
import random
import json
import os
from keep_alive import keep_alive

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="-", intents=intents)

BALANCE_FILE = "balances.json"

def load_balances():
    if os.path.exists(BALANCE_FILE):
        with open(BALANCE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_balances(balances):
    with open(BALANCE_FILE, "w") as f:
        json.dump(balances, f, indent=4)

balances = load_balances()

def get_balance(user_id):
    return balances.get(str(user_id), 1000)

def set_balance(user_id, amount):
    balances[str(user_id)] = amount
    save_balances(balances)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def cf(ctx, amount: int):
    user_id = str(ctx.author.id)
    current_balance = get_balance(user_id)

    if amount <= 0:
        return await ctx.send("Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("You don't have enough balance!")

    result = random.choice(["Heads", "Tails"])
    guess = random.choice(["Heads", "Tails"])  # You can change to allow user input

    if result == guess:
        new_balance = current_balance + amount
        await ctx.send(f"🎉 It was **{result}**! You won {amount} coins!")
    else:
        new_balance = current_balance - amount
        await ctx.send(f"😢 It was **{result}**. You lost {amount} coins.")

    set_balance(user_id, new_balance)

@bot.command()
@commands.has_role("Admin")
async def setbal(ctx, target: discord.Member, amount: int):
    if amount < 0:
        return await ctx.send("Balance can't be negative.")
    set_balance(target.id, amount)
    await ctx.send(f"Set {target.mention}'s balance to {amount} coins.")

@bot.command()
@commands.has_role("Admin")
async def setbalrole(ctx, role: discord.Role, amount: int):
    if amount < 0:
        return await ctx.send("Balance can't be negative.")
    
    count = 0
    for member in role.members:
        set_balance(member.id, amount)
        count += 1
    
    await ctx.send(f"Set balance of {count} members in **{role.name}** to {amount} coins.")

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
