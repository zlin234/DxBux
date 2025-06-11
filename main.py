import os
import discord
from discord.ext import commands
import random
import json
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta

# ------------------ BALANCE MANAGEMENT ------------------

BALANCE_FILE = "balances.json"
BANK_FILE = "bank_data.json"
INTEREST_TRACKER_FILE = "interest_tracker.json"

def load_balances():
    try:
        with open(BALANCE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_balances(balances):
    with open(BALANCE_FILE, "w") as f:
        json.dump(balances, f)

def get_balance(user_id):
    balances = load_balances()
    return balances.get(str(user_id), 1000)

def set_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = amount
    save_balances(balances)

# ------------------ BANK MANAGEMENT ------------------

def load_bank_data():
    try:
        with open(BANK_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_bank_data(bank_data):
    with open(BANK_FILE, "w") as f:
        json.dump(bank_data, f)

def get_bank_data(user_id):
    bank_data = load_bank_data()
    if str(user_id) not in bank_data:
        bank_data[str(user_id)] = {
            "plan": None,
            "deposited": 0
        }
        save_bank_data(bank_data)
    return bank_data[str(user_id)]

def update_bank_data(user_id, data):
    bank_data = load_bank_data()
    bank_data[str(user_id)] = data
    save_bank_data(bank_data)

# ------------------ BANK PLANS ------------------

BANK_PLANS = {
    "basic": {
        "name": "Basic",
        "min_deposit": 0,
        "interest": 0.01,
        "description": "1% interest, no minimum balance"
    },
    "premium": {
        "name": "Premium",
        "min_deposit": 5000,
        "interest": 0.03,
        "description": "3% interest, requires 5,000 coin minimum"
    },
    "vip": {
        "name": "VIP",
        "min_deposit": 15000,
        "interest": 0.05,
        "description": "5% interest, requires 15,000 coin minimum"
    }
}

# ------------------ INTEREST TRACKER ------------------

def load_interest_tracker():
    try:
        with open(INTEREST_TRACKER_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_interest_tracker(data):
    with open(INTEREST_TRACKER_FILE, "w") as f:
        json.dump(data, f)

def can_collect_interest(user_id):
    data = load_interest_tracker()
    last_time = data.get(str(user_id), None)
    if last_time is None:
        return True
    last_date = datetime.strptime(last_time, "%Y-%m-%d")
    return datetime.utcnow().date() > last_date.date()

def update_interest_timestamp(user_id):
    data = load_interest_tracker()
    data[str(user_id)] = datetime.utcnow().strftime("%Y-%m-%d")
    save_interest_tracker(data)

# ------------------ DISCORD BOT ------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="-", intents=intents)

@bot.command()
async def bank(ctx):
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)

    plan = bank_data["plan"]
    deposited = bank_data["deposited"]

    if not plan:
        await ctx.send("You have no active bank plan. Use `-changeplan [plan name]` to choose one.")
        return

    plan_info = BANK_PLANS.get(plan)
    embed = discord.Embed(
        title=f"{ctx.author.name}'s Bank Account",
        color=discord.Color.green()
    )
    embed.add_field(name="Plan", value=plan_info["name"], inline=False)
    embed.add_field(name="Deposited", value=f"{deposited} coins", inline=False)
    embed.add_field(name="Interest Rate", value=f"{plan_info['interest'] * 100:.0f}%", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def deposit(ctx, amount: int):
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    plan = bank_data["plan"]

    if not plan:
        await ctx.send("You don't have a bank plan. Use `-changeplan [plan name]` first.")
        return

    balance = get_balance(user_id)
    if amount <= 0 or amount > balance:
        await ctx.send("You don't have enough coins or entered an invalid amount.")
        return

    bank_data["deposited"] += amount
    update_bank_data(user_id, bank_data)
    set_balance(user_id, balance - amount)

    await ctx.send(f"You deposited {amount} coins into your bank account.")

@bot.command()
async def withdraw(ctx, amount: int):
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    deposited = bank_data["deposited"]

    if amount <= 0 or amount > deposited:
        await ctx.send("Invalid amount or insufficient bank balance.")
        return

    bank_data["deposited"] -= amount
    update_bank_data(user_id, bank_data)

    balance = get_balance(user_id)
    set_balance(user_id, balance + amount)

    await ctx.send(f"You withdrew {amount} coins from your bank account.")

@bot.command()
async def interest(ctx):
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    plan = bank_data["plan"]

    if not plan:
        await ctx.send("You don't have a bank plan.")
        return

    if not can_collect_interest(user_id):
        await ctx.send("You have already collected your interest today.")
        return

    deposited = bank_data["deposited"]
    interest_rate = BANK_PLANS[plan]["interest"]
    earnings = int(deposited * interest_rate)

    if earnings <= 0:
        await ctx.send("No interest earned today (no funds deposited).")
        return

    update_interest_timestamp(user_id)

    balance = get_balance(user_id)
    set_balance(user_id, balance + earnings)

    await ctx.send(f"You collected {earnings} coins in interest today.")

@bot.command()
async def changeplan(ctx, new_plan: str):
    user_id = ctx.author.id
    new_plan = new_plan.lower()

    if new_plan not in BANK_PLANS:
        await ctx.send("That bank plan doesn't exist. Try `basic`, `premium`, or `vip`.")
        return

    current_data = get_bank_data(user_id)
    current_plan = current_data["plan"]
    deposited = current_data["deposited"]

    # Refund current deposited coins if any
    if deposited > 0:
        balance = get_balance(user_id)
        set_balance(user_id, balance + deposited)

    # Reset data with new plan and zero deposit
    update_bank_data(user_id, {
        "plan": new_plan,
        "deposited": 0
    })

    await ctx.send(f"You've switched to the **{BANK_PLANS[new_plan]['name']}** plan. "
                   f"Your previous deposit of {deposited} coins was refunded to your balance.")

from keep_alive import keep_alive  # Import from your separate file

keep_alive()  # Start the uptime server
bot.run(os.getenv("DISCORD_TOKEN"))  # Replace with your real bot token or use os.getenv
