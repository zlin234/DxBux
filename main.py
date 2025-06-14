import os
import time
import discord
import asyncio
from typing import List, Dict, Tuple
from discord.ext import commands
import random
import json
from threading import Thread
from flask import Flask
import re
from datetime import datetime, timedelta
from discord.ext.commands import cooldown, BucketType, CommandOnCooldown

# ------------------ BALANCE MANAGEMENT ------------------

def format_time_until(timestamp):
    remaining = timestamp - time.time()
    if remaining <= 0:
        return "now"

    hours = int(remaining // 3600)
    minutes = int((remaining % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

BALANCE_FILE = "balances.json"
BANK_FILE = "bank_data.json"
LOANS_FILE = "loans.json"
ALLOWANCE_FILE = "allowance.json"
SHOP_ITEMS_FILE = "shop_items.json"
INVENTORY_FILE = "inventories.json"
ROB_PROTECTION_FILE = "rob_protection.json"
ROB_HISTORY_FILE = "rob_history.json"
CURRENCY_STOCKS_FILE = "currency_stocks.json"
CURRENCY_PRICES_FILE = "currency_prices.json"
WHEEL_SECTIONS = [
    {"name": "100x", "multiplier": 100, "color": 0xFF0000, "weight": 2},  # ~2.5%
    {"name": "10x", "multiplier": 10, "color": 0x00FF00, "weight": 8},    # ~10%
    {"name": "5x", "multiplier": 5, "color": 0x0000FF, "weight": 10},     # ~12.5%
    {"name": "2x", "multiplier": 2, "color": 0xFFFF00, "weight": 10},     # ~18.75%
    {"name": "1.5x", "multiplier": 1.5, "color": 0xFF00FF, "weight": 15}, # ~25%
    {"name": "1.0x", "multiplier": 1, "color": 0xFF00FF, "weight": 30},   # ~18.75%
    {"name": "0.5x", "multiplier": 0.5, "color": 0x00FFFF, "weight": 25},  # ~10%
]
PLINKO_ROWS = 7
PLINKO_WIDTH = 13  # Should be odd number
PLINKO_MULTIPLIERS = {
    0: 0.0,   # <- 0x
    1: 0.5,
    2: 0.5,
    3: 1.0,
    4: 1.0,
    5: 1.5,
    6: 2.0,   # <- center, best payout
    7: 1.5,
    8: 1.0,
    9: 1.0,
    10: 0.5,
    11: 0.5,
    12: 0.0   # <- 0x
}
BANK_PLANS = {
    "basic": {
        "name": "Basic",
        "min_deposit": 0,
        "interest": 0.01,  # 1% daily interest
        "description": "1% daily interest, no minimum balance",
        "requirements": "No minimum"  # Add this
    },
    "premium": {
        "name": "Premium",
        "min_deposit": 5000,
        "interest": 0.03,  # 3% daily interest
        "description": "3% daily interest, requires 5,000 coin minimum",
        "requirements": "5,000 coin minimum"  # Add this
    },
    "vip": {
        "name": "VIP",
        "min_deposit": 15000,
        "interest": 0.05,  # 5% daily interest
        "description": "5% daily interest, requires 15,000 coin minimum",
        "requirements": "15,000 coin minimum"  # Add this
    }
}


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
    return balances.get(str(user_id), 1000)  # Default 1000 coins if new user

def set_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = amount
    save_balances(balances)

# ------------------ STOCK MANAGEMENT ------------------

def load_currency_stocks():
    try:
        with open(CURRENCY_STOCKS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        stocks = {"BobBux": 10000, "DxBux": 10000, "Gold": 10000}
        save_currency_stocks(stocks)
        return stocks

def save_currency_stocks(stocks):
    with open(CURRENCY_STOCKS_FILE, "w") as f:
        json.dump(stocks, f)

def load_currency_prices():
    try:
        with open(CURRENCY_PRICES_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        prices = {"BobBux": 500, "DxBux": 750, "Gold": 1000}
        save_currency_prices(prices)
        return prices

def save_currency_prices(prices):
    with open(CURRENCY_PRICES_FILE, "w") as f:
        json.dump(prices, f)

def update_currency_price(currency_name, amount_purchased=0):
    prices = load_currency_prices()
    
    if amount_purchased > 0:
        # More aggressive price scaling for unlimited economy
        price_increase = min(50, 0.5 * amount_purchased)  # Max 50% increase per transaction
        prices[currency_name] = int(prices[currency_name] * (1 + price_increase/100))
    
    # Daily volatility
    daily_change = random.uniform(0.95, 1.05)  # ±5% daily change
    prices[currency_name] = max(10, int(prices[currency_name] * daily_change))
    
    save_currency_prices(prices)
    return prices[currency_name]

def load_inventories():
    try:
        with open(INVENTORY_FILE, "r") as f:
            inventories = json.load(f)
    except FileNotFoundError:
        inventories = {}
    
    for user_id, inv in inventories.items():
        for currency in ["BobBux", "DxBux", "Gold"]:
            if currency not in inv:
                inv[currency] = 0
                
    return inventories

def get_inventory(user_id):
    inventories = load_inventories()
    user_inv = inventories.get(str(user_id), {})
    
    for currency in ["BobBux", "DxBux", "Gold"]:
        if currency not in user_inv:
            user_inv[currency] = 0
    
    return user_inv

# ------------------ LOAN MANAGEMENT ------------------

def load_loans():
    try:
        with open(LOANS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_loans(loans):
    with open(LOANS_FILE, "w") as f:
        json.dump(loans, f)

def get_loan(user_id):
    loans = load_loans()
    return loans.get(str(user_id), None)

def create_loan(user_id, amount, interest_rate=0.1, duration_days=7):
    loans = load_loans()
    due_date = datetime.now() + timedelta(days=duration_days)
    loans[str(user_id)] = {
        "amount": amount,
        "interest_rate": interest_rate,
        "due_date": due_date.timestamp(),
        "created_at": datetime.now().timestamp(),
        "repaid": False
    }
    save_loans(loans)
    return loans[str(user_id)]

def repay_loan(user_id):
    loans = load_loans()
    if str(user_id) not in loans:
        return False
    loans[str(user_id)]["repaid"] = True
    save_loans(loans)
    return True

# ------------------ ALLOWANCE MANAGEMENT ------------------

def load_allowances():
    try:
        with open(ALLOWANCE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_allowances(allowances):
    with open(ALLOWANCE_FILE, "w") as f:
        json.dump(allowances, f)

def can_claim_allowance(user_id):
    allowances = load_allowances()
    user_data = allowances.get(str(user_id), {"last_claim": 0})
    current_time = time.time()
    return current_time - user_data["last_claim"] >= 1800  # 30 minutes in seconds

def update_allowance_claim(user_id):
    allowances = load_allowances()
    if str(user_id) not in allowances:
        allowances[str(user_id)] = {"last_claim": 0}
    allowances[str(user_id)]["last_claim"] = time.time()
    save_allowances(allowances)

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
            "deposited": 0,
            "last_interest_claim": 0,
            "pending_interest": 0
        }
        save_bank_data(bank_data)
    return bank_data[str(user_id)]

def update_bank_data(user_id, data):
    bank_data = load_bank_data()
    bank_data[str(user_id)] = data
    save_bank_data(bank_data)

# ------------------ DISCORD BOT SETUP ------------------

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="-", intents=intents)

# ------------------ LOAN COMMANDS ------------------

@bot.command()
async def loan(ctx, amount: int):
    """Take out a loan (10% interest, due in 7 days)"""
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    
    # Check for existing loan
    existing_loan = get_loan(user_id)
    if existing_loan and not existing_loan["repaid"]:
        due_date = datetime.fromtimestamp(existing_loan["due_date"])
        return await ctx.send(
            f"❌ You already have an outstanding loan of {existing_loan['amount']} coins!\n"
            f"Due by: {due_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Use `-repayloan` to repay it first."
        )
    
    # Validate amount
    if amount <= 0:
        return await ctx.send("❌ Loan amount must be positive.")
    if amount > 10000:
        return await ctx.send("❌ Maximum loan amount is 10,000 coins.")
    
    # Create loan and give money
    loan_data = create_loan(user_id, amount)
    set_balance(user_id, current_balance + amount)
    
    due_date = datetime.fromtimestamp(loan_data["due_date"])
    await ctx.send(
        f"✅ You've taken out a loan of **{amount} coins**!\n"
        f"• Interest rate: 10%\n"
        f"• Total to repay: **{int(amount * 1.1)} coins**\n"
        f"• Due by: {due_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Use `-repayloan` to repay it before the due date to avoid penalties!"
    )

@bot.command()
async def repayloan(ctx):
    """Repay your outstanding loan"""
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    loan_data = get_loan(user_id)
    
    if not loan_data or loan_data["repaid"]:
        return await ctx.send("❌ You don't have any active loans to repay.")
    
    total_to_repay = int(loan_data["amount"] * (1 + loan_data["interest_rate"]))
    
    if current_balance < total_to_repay:
        return await ctx.send(
            f"❌ You need **{total_to_repay} coins** to repay your loan, but only have **{current_balance} coins**."
        )
    
    # Check if loan is overdue
    is_overdue = datetime.now().timestamp() > loan_data["due_date"]
    if is_overdue:
        penalty = int(total_to_repay * 0.2)  # 20% penalty
        total_to_repay += penalty
        await ctx.send(
            f"⚠️ Your loan is overdue! A 20% penalty of {penalty} coins has been added.\n"
            f"New total to repay: **{total_to_repay} coins**"
        )
    
    # Deduct money and mark as repaid
    set_balance(user_id, current_balance - total_to_repay)
    repay_loan(user_id)
    
    await ctx.send(
        f"✅ You've successfully repaid your loan of **{loan_data['amount']} coins** "
        f"plus **{int(loan_data['amount'] * loan_data['interest_rate'])} coins** interest!\n"
        f"• New balance: **{current_balance - total_to_repay} coins**"
    )

@bot.command()
async def myloan(ctx):
    """Check your current loan status"""
    user_id = ctx.author.id
    loan_data = get_loan(user_id)
    
    if not loan_data or loan_data["repaid"]:
        return await ctx.send("You don't have any active loans.")
    
    created_date = datetime.fromtimestamp(loan_data["created_at"])
    due_date = datetime.fromtimestamp(loan_data["due_date"])
    time_left = due_date - datetime.now()
    
    total_to_repay = int(loan_data["amount"] * (1 + loan_data["interest_rate"]))
    
    message = (
        f"**Loan Details:**\n"
        f"• Amount borrowed: **{loan_data['amount']} coins**\n"
        f"• Interest rate: **10%**\n"
        f"• Total to repay: **{total_to_repay} coins**\n"
        f"• Taken on: {created_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"• Due by: {due_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    
    if datetime.now().timestamp() > loan_data["due_date"]:
        penalty = int(total_to_repay * 0.2)
        message += (
            f"⚠️ **OVERDUE!** 20% penalty applies: **{penalty} coins**\n"
            f"New total to repay: **{total_to_repay + penalty} coins**\n"
        )
    else:
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        message += f"• Time remaining: **{hours}h {minutes}m**\n"
    
    message += "\nUse `-repayloan` to repay your loan."
    await ctx.send(message)


# ------------------ ALLOWANCE COMMANDS ------------------

@bot.command()
async def allowance(ctx):
    """Claim your 100 coin allowance (every 30 minutes)"""
    user_id = ctx.author.id
    
    if can_claim_allowance(user_id):
        current_balance = get_balance(user_id)
        set_balance(user_id, current_balance + 100)
        update_allowance_claim(user_id)
        await ctx.send(
            f"💰 You've claimed your **100 coin** allowance!\n"
            f"• New balance: **{current_balance + 100} coins**\n"
            f"• Next allowance available in 30 minutes."
        )
    else:
        allowances = load_allowances()
        last_claim = allowances.get(str(user_id), {}).get("last_claim", 0)
        next_claim = last_claim + 1800  # 30 minutes in seconds
        time_left = next_claim - time.time()
        
        if time_left > 0:
            minutes = int(time_left // 60)
            seconds = int(time_left % 60)
            await ctx.send(
                f"⏳ You can claim your next allowance in **{minutes}m {seconds}s**.\n"
                f"Type `-allowance` then to get 100 coins!"
            )
        else:
            await ctx.send("Something went wrong. Try again!")




#-------------------ROB/TAX/DONATE---------------------

@bot.command()
@commands.cooldown(1, 60, BucketType.user)  # 1-minute cooldown
async def rob(ctx, member: discord.Member):
    try:
        if member.id == ctx.author.id:
            embed = discord.Embed(
                title="⚠️ Invalid Target",
                description="You can't rob yourself.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # Check for protection
        protection_data = load_rob_protection()
        if str(member.id) in protection_data and protection_data[str(member.id)] > 0:
            protection_data[str(member.id)] -= 1
            save_rob_protection(protection_data)
            embed = discord.Embed(
                title="🔒 Robbery Blocked!",
                description=f"{member.mention} is protected by a padlock.",
                color=discord.Color.dark_purple()
            )
            embed.add_field(name="🛡️ Protections Left", value=str(protection_data[str(member.id)]), inline=True)
            embed.set_footer(text="Better luck next time...")
            return await ctx.send(embed=embed)

        victim_balance = get_balance(member.id)
        robber_balance = get_balance(ctx.author.id)

        if victim_balance <= 0:
            embed = discord.Embed(
                title="🚫 No Coins to Steal",
                description=f"{member.mention} has nothing to steal.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # Record robbery in history
        rob_history = load_rob_history()
        rob_history[str(ctx.author.id)] = {
            "victim_id": member.id,
            "timestamp": time.time()
        }
        save_rob_history(rob_history)

        stolen_amount = random.randint(1, int(victim_balance * 0.4))
        set_balance(member.id, victim_balance - stolen_amount)
        set_balance(ctx.author.id, robber_balance + stolen_amount)

        embed = discord.Embed(
            title="💰 Robbery Successful!",
            description=f"{ctx.author.mention} just robbed {member.mention}!",
            color=discord.Color.green()
        )
        embed.add_field(name="💸 Amount Stolen", value=f"{stolen_amount} coins", inline=True)
        embed.set_footer(text="Use your loot wisely...")

        await ctx.send(embed=embed)

    except CommandOnCooldown as e:
        seconds = round(e.retry_after)
        embed = discord.Embed(
            title="⏳ Cooldown Active",
            description=f"You're robbing too fast! Try again in `{seconds} seconds`.",
            color=discord.Color.orange()
        )
        return await ctx.send(embed=embed)

    
@bot.command()
async def tax(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        embed = discord.Embed(
            title="⚠️ Invalid Action",
            description="You can't tax yourself.",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed)

    rich_id = ctx.author.id
    victim_id = member.id

    rich_balance = get_balance(rich_id)
    victim_balance = get_balance(victim_id)

    if victim_balance <= 0:
        embed = discord.Embed(
            title="🚫 No Coins",
            description=f"{member.mention} has no coins to be taxed.",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed)

    taxed_amount = int(victim_balance * 0.25)
    tax_cost = taxed_amount

    if rich_balance < tax_cost:
        embed = discord.Embed(
            title="💸 Not Enough Funds",
            description="You don't have enough coins to tax this user.",
            color=discord.Color.orange()
        )
        return await ctx.send(embed=embed)

    # Transfer logic
    set_balance(rich_id, rich_balance - tax_cost - taxed_amount)
    set_balance(victim_id, victim_balance - taxed_amount)

    embed = discord.Embed(
        title="🏛️ Taxation Successful",
        color=discord.Color.gold()
    )
    embed.add_field(name="👤 Target", value=member.mention, inline=True)
    embed.add_field(name="💰 Taxed From Them", value=f"{taxed_amount} coins", inline=True)
    embed.add_field(name="💸 Cost to You", value=f"{tax_cost} coins", inline=True)
    embed.set_footer(text="Economy Tax Command")

    await ctx.send(embed=embed)



@bot.command()
async def donate(ctx, member: discord.Member, amount: int):
    """Donate coins to another user."""
    sender_id = ctx.author.id
    recipient_id = member.id

    if member.bot:
        return await ctx.send("❌ You can't donate to bots.")
    if sender_id == recipient_id:
        return await ctx.send("❌ You can't donate to yourself.")
    if amount <= 0:
        return await ctx.send("❌ Donation amount must be greater than 0.")

    sender_balance = get_balance(sender_id)
    recipient_balance = get_balance(recipient_id)

    if sender_balance < amount:
        return await ctx.send("❌ You don't have enough coins to donate.")

    set_balance(sender_id, sender_balance - amount)
    set_balance(recipient_id, recipient_balance + amount)

    await ctx.send(f"✅ {ctx.author.mention} donated {amount} coins to {member.mention}!")


# ------------------ BANK COMMANDS ------------------

class BankPlanView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        
    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True
            
    @discord.ui.button(label="Basic", style=discord.ButtonStyle.primary)
    async def basic_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your bank selection!", ephemeral=True)
            
        bank_data = get_bank_data(self.user_id)
        bank_data["plan"] = "basic"
        update_bank_data(self.user_id, bank_data)
        
        await self.disable_all_items()
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            f"{interaction.user.mention} You've selected the **Basic** bank plan! {BANK_PLANS['basic']['description']}"
        )

    @discord.ui.button(label="Premium", style=discord.ButtonStyle.secondary)
    async def premium_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your bank selection!", ephemeral=True)
            
        bank_data = get_bank_data(self.user_id)
        bank_data["plan"] = "premium"
        update_bank_data(self.user_id, bank_data)
        
        await self.disable_all_items()
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            f"{interaction.user.mention} You've selected the **Premium** bank plan! {BANK_PLANS['premium']['description']}"
        )

    @discord.ui.button(label="VIP", style=discord.ButtonStyle.success)
    async def vip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your bank selection!", ephemeral=True)
            
        bank_data = get_bank_data(self.user_id)
        bank_data["plan"] = "vip"
        update_bank_data(self.user_id, bank_data)
        
        await self.disable_all_items()
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            f"{interaction.user.mention} You've selected the **VIP** bank plan! {BANK_PLANS['vip']['description']}"
        )

@bot.command()
async def deposit(ctx, amount: int):
    """Deposit coins into your bank account"""
    user_id = ctx.author.id
    wallet_balance = get_balance(user_id)
    bank_data = get_bank_data(user_id)
    
    # Check if user has a bank plan
    if bank_data["plan"] is None:
        return await ctx.send("❌ You don't have a bank plan. Use `-bank` to select one first.")
    
    # Validate the amount
    if amount <= 0:
        return await ctx.send("❌ Deposit amount must be positive.")
    if amount > wallet_balance:
        return await ctx.send("❌ You don't have that much in your wallet.")
    
    # Get the bank plan details
    plan = BANK_PLANS[bank_data["plan"]]
    
    # Calculate new deposited amount
    new_deposited = bank_data["deposited"] + amount
    
    # Check if this meets the minimum for the plan (only if they had nothing deposited before)
    if bank_data["deposited"] == 0 and new_deposited < plan["min_deposit"]:
        return await ctx.send(
            f"❌ Your **{plan['name']}** plan requires a minimum deposit of {plan['min_deposit']} coins.\n"
            f"Either deposit at least {plan['min_deposit']} coins or switch to a different plan with `-bank`."
        )
    
    # Update balances
    set_balance(user_id, wallet_balance - amount)
    bank_data["deposited"] = new_deposited
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"✅ Successfully deposited **{amount} coins** into your bank account!\n"
        f"• New wallet balance: **{wallet_balance - amount} coins**\n"
        f"• Bank balance: **{new_deposited} coins**\n"
        f"• Plan: **{plan['name']}** ({plan['interest']*100}% daily interest)"
    )

@bot.command()
async def withdraw(ctx, amount: int):
    """Withdraw coins from your bank account"""
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    
    if bank_data["plan"] is None:
        return await ctx.send("You currently have no bank plan. Use `-bank` to get started.")
    
    if amount <= 0:
        return await ctx.send("❌ Withdrawal amount must be positive.")
    if amount > bank_data["deposited"]:
        return await ctx.send("❌ You don't have that much deposited in your bank account.")
    
    # Check if withdrawal would go below minimum for plan
    plan = BANK_PLANS[bank_data["plan"]]
    if (bank_data["deposited"] - amount) < plan["min_deposit"]:
        return await ctx.send(
            f"❌ You must maintain at least {plan['min_deposit']} coins deposited for your plan.\n"
            "Consider switching to a different plan with `-bank` or withdrawing less."
        )
    
    # Update balances
    current_balance = get_balance(user_id)
    set_balance(user_id, current_balance + amount)
    bank_data["deposited"] -= amount
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"✅ Successfully withdrew **{amount} coins** from your bank account.\n"
        f"• New wallet balance: **{current_balance + amount} coins**\n"
        f"• Bank balance: **{bank_data['deposited']} coins**"
    )

@bot.command()
async def interest(ctx):
    """Claim your accumulated interest (24h cooldown)"""
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    
    if bank_data["plan"] is None:
        return await ctx.send("❌ You don't have a bank plan. Use `-bank` to get started.")
    
    if bank_data["deposited"] == 0:
        return await ctx.send("❌ You don't have any coins deposited to earn interest.")
    
    current_time = time.time()
    last_claim = bank_data.get("last_interest_claim", 0)
    
    # Check if 24h cooldown has passed
    if current_time - last_claim < 86400:
        remaining = 86400 - (current_time - last_claim)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return await ctx.send(f"⌛ Come back in **{hours}h {minutes}m** to claim more interest!")
    
    # Calculate how many full days passed since last claim
   # Calculate how many full days passed since last claim
    if "last_interest_claim" not in bank_data:
        days_passed = 1
    else:
        days_passed = min(30, int((current_time - last_claim) / 86400))
        if days_passed < 1:
            days_passed = 1

    
    # Calculate COMPOUNDED interest for all missed days
    interest_rate = BANK_PLANS[bank_data["plan"]]["interest"]
    principal = bank_data["deposited"]
    total_interest = 0
    
    for _ in range(days_passed):
        daily_interest = principal * interest_rate
        total_interest += daily_interest
        principal += daily_interest  # Compounding effect
    
    # Update bank data
    bank_data["deposited"] = principal  # Update with compounded amount
    bank_data["last_interest_claim"] = current_time
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"💰 **+{int(total_interest):,} coins** (Interest over {days_passed} day{'s' if days_passed > 1 else ''})\n"
        f"🏦 New deposited amount: **{int(principal):,} coins**"
    )

@bot.command()
async def bank(ctx):
    """Manage your bank account and select plans"""
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    
    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Bank Account",
        color=discord.Color.blue()
    )
    
    if bank_data["plan"]:
        current_plan = BANK_PLANS[bank_data["plan"]]
        embed.add_field(
            name="Current Plan",
            value=f"**{current_plan['name']}**\n{current_plan['description']}",
            inline=False
        )
        embed.add_field(
            name="Account Status",
            value=(
                f"• Deposited: {bank_data['deposited']:,} coins\n"
                f"• Interest Rate: {current_plan['interest']*100}% daily\n"
                f"• Next Interest: {format_time_until(bank_data['last_interest_claim'] + 86400)}"
            ),
            inline=False
        )
    else:
        embed.description = "You don't have an active bank plan yet!"
    
    embed.add_field(
        name="Available Plans",
        value="\n".join(
            f"• **{plan['name']}**: {plan['interest']*100}% daily (Min: {plan['min_deposit']:,} coins)"
            for plan in BANK_PLANS.values()
        ),
        inline=False
    )
    
    # Always show BankPlanView so user can select/change plans anytime
    view = BankPlanView(user_id)
    
    await ctx.send(
        embed=embed,
        view=view,
        content=f"{ctx.author.mention}, here's your bank information:"
    )


# ------------------ SHOP COMMANDS ------------------

def load_shop_items():
    try:
        with open(SHOP_ITEMS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # Default shop items
        default_items = {
            "padlock": {
                "name": "Padlock",
                "price": 500,
                "description": "Protects against 5 robbery attempts (stacks)",
                "max_stack": 10
            },
            "phone": {
                "name": "Phone",
                "price": 1000,
                "description": "Call police to arrest recent robbers (last 5 minutes)",
                "max_stack": 1
            }
        }
        save_shop_items(default_items)
        return default_items

def save_shop_items(shop_items):
    with open(SHOP_ITEMS_FILE, "w") as f:
        json.dump(shop_items, f)

def load_inventories():
    try:
        with open(INVENTORY_FILE, "r") as f:
            inventories = json.load(f)
    except FileNotFoundError:
        inventories = {}
    
    for user_id, inv in inventories.items():
        for currency in ["BobBux", "DxBux", "Gold"]:
            if currency not in inv:
                inv[currency] = 0
                
    return inventories

def save_inventories(inventories):
    with open(INVENTORY_FILE, "w") as f:
        json.dump(inventories, f)

def load_rob_protection():
    try:
        with open(ROB_PROTECTION_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_rob_protection(protection_data):
    with open(ROB_PROTECTION_FILE, "w") as f:
        json.dump(protection_data, f)

def load_rob_history():
    try:
        with open(ROB_HISTORY_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_rob_history(history_data):
    with open(ROB_HISTORY_FILE, "w") as f:
        json.dump(history_data, f)

def get_inventory(user_id):
    inventories = load_inventories()
    user_inv = inventories.get(str(user_id), {})
    
    for currency in ["BobBux", "DxBux", "Gold"]:
        if currency not in user_inv:
            user_inv[currency] = 0
    
    return user_inv

def add_to_inventory(user_id, item_name, quantity=1):
    inventories = load_inventories()
    user_inv = inventories.get(str(user_id), {})
    
    # Remove max_stack check for currencies
    if item_name in ["BobBux", "DxBux", "Gold"]:
        user_inv[item_name] = user_inv.get(item_name, 0) + quantity
    else:
        # Keep existing logic for other items
        max_stack = load_shop_items().get(item_name, {}).get("max_stack", 1)
        current_qty = user_inv.get(item_name, 0)
        if current_qty + quantity > max_stack:
            return False
    
    inventories[str(user_id)] = user_inv
    save_inventories(inventories)
    return True

def remove_from_inventory(user_id, item_name, quantity=1):
    inventories = load_inventories()
    user_inv = inventories.get(str(user_id), {})
    
    current_qty = user_inv.get(item_name, 0)
    if current_qty < quantity:
        return False  # Not enough items
    
    user_inv[item_name] = current_qty - quantity
    if user_inv[item_name] <= 0:
        del user_inv[item_name]
    
    inventories[str(user_id)] = user_inv
    save_inventories(inventories)
    return True


class QuantitySelect(discord.ui.Select):
    def __init__(self, item_id, max_stack, *args, **kwargs):
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(1, max_stack + 1)
        ]
        super().__init__(placeholder="Quantity", options=options, row=0, *args, **kwargs)
        self.item_id = item_id
        self.selected_quantity = 1

    async def callback(self, interaction: discord.Interaction):
        self.selected_quantity = int(self.values[0])
        self.view.selected_quantities[self.item_id] = self.selected_quantity
        await interaction.response.defer()

class ShopItemRow(discord.ui.View):
    def __init__(self, user_id, item_id, item_data):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.item_id = item_id
        self.item_data = item_data

        # ✅ This fixes the "AttributeError"
        self.selected_quantities = {}

        # Quantity dropdown
        self.quantity_select = QuantitySelect(item_id, item_data.get("max_stack", 1))
        self.add_item(self.quantity_select)

        # Buy button
        self.add_item(ShopBuyButton(item_id, item_data, self.quantity_select))


class ShopBuyButton(discord.ui.Button):
    def __init__(self, item_id, item_data, quantity_select):
        super().__init__(label=f"Buy {item_data['name']}", style=discord.ButtonStyle.green)
        self.item_id = item_id
        self.item_data = item_data
        self.quantity_select = quantity_select

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.user_id:
            return await interaction.response.send_message("❌ This UI isn't for you.", ephemeral=True)

        quantity = self.quantity_select.selected_quantity
        total_price = self.item_data["price"] * quantity
        user_id = interaction.user.id
        balance = get_balance(user_id)
        max_stack = self.item_data.get("max_stack", 1)

        # Check balance
        if balance < total_price:
            return await interaction.response.send_message(
                f"❌ You need {total_price} coins to buy {quantity}x {self.item_data['name']}, "
                f"but only have {balance} coins.",
                ephemeral=True
            )

        # Check stack limit
        user_inv = get_inventory(user_id)
        current_qty = user_inv.get(self.item_id, 0)
        if current_qty + quantity > max_stack:
            return await interaction.response.send_message(
                f"❌ You can only hold {max_stack} of {self.item_data['name']} (you have {current_qty}).",
                ephemeral=True
            )

        # Process purchase
        set_balance(user_id, balance - total_price)
        add_to_inventory(user_id, self.item_id, quantity)
        await interaction.response.send_message(
            f"✅ Purchased {quantity}x {self.item_data['name']} for {total_price} coins!", ephemeral=True
        )

@bot.command()
async def shop(ctx):
    """View and buy items from the shop with quantity selection"""
    shop_items = load_shop_items()
    await ctx.send(embed=discord.Embed(
        title="🛒 Shop",
        description="Select a quantity then press Buy!",
        color=discord.Color.green()
    ))

    for item_id, item_data in shop_items.items():
        view = ShopItemRow(ctx.author.id, item_id, item_data)
        embed = discord.Embed(
            title=item_data["name"],
            description=f"{item_data['description']}\nPrice: {item_data['price']} coins",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed, view=view)


class UseItemDropdown(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id
        self.user_inv = get_inventory(user_id)

        # Get all usable items from shop data
        shop_items = load_shop_items()
        usable_items = {item_id: item_data for item_id, item_data in shop_items.items() 
                       if item_data.get("usable", False)}  # Add "usable": true to shop items

        options = []
        
        # Check for each usable item if user has it
        for item_id, item_data in usable_items.items():
            if self.user_inv.get(item_id, 0) > 0:
                emoji = "🔒" if item_id == "padlock" else "📱"
                options.append(discord.SelectOption(
                    label=item_data["name"],
                    value=item_id,
                    description=item_data["description"],
                    emoji=emoji
                ))

        if not options:
            options.append(discord.SelectOption(
                label="No usable items",
                value="none",
                description="Buy some items first",
                emoji="❌"
            ))

        super().__init__(
            placeholder="Select item to use",
            min_values=1,
            max_values=1,
            options=options
        )



class UseItemView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.selected_item = None
        self.selected_quantity = 1

        self.add_item(UseItemDropdown(user_id))
        self.add_item(UseQuantitySelect(10))

    @discord.ui.button(label="Use Item", style=discord.ButtonStyle.green, row=2)
    async def use_item_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This menu is not for you.", ephemeral=True)

        item = self.selected_item
        quantity = self.selected_quantity

        if not item or item == "none":
            return await interaction.response.send_message("❌ No item selected.", ephemeral=True)

        user_inv = get_inventory(self.user_id)
        if item not in user_inv:
            return await interaction.response.send_message("❌ You don't have this item anymore.", ephemeral=True)

        # --- PADLOCK HANDLING ---
        if item == "padlock":
            if user_inv[item] < quantity:
                return await interaction.response.send_message(
                    f"❌ You only have {user_inv[item]} padlocks, but tried to use {quantity}.", ephemeral=True
                )
            protection_data = load_rob_protection()
            current_protection = protection_data.get(str(self.user_id), 0)
            protection_data[str(self.user_id)] = current_protection + (5 * quantity)
            save_rob_protection(protection_data)
            remove_from_inventory(self.user_id, "padlock", quantity)
            return await interaction.response.send_message(
                f"🔒 You used {quantity} padlock(s), adding {5 * quantity} protections.\n"
                f"🛡️ Total protections: **{protection_data[str(self.user_id)]}**", ephemeral=False
            )

        # --- PHONE HANDLING ---
        elif item == "phone":
            if user_inv[item] < 1:
                return await interaction.response.send_message("❌ You don't have a phone.", ephemeral=True)

            rob_history = load_rob_history()
            recent_robbers = []
            for robber_id, rob_data in rob_history.items():
                if time.time() - rob_data["timestamp"] <= 300:
                    recent_robbers.append((robber_id, rob_data["victim_id"]))

            remove_from_inventory(self.user_id, "phone")
            arrests = 0
            for robber_id, victim_id in recent_robbers:
                if str(victim_id) == str(self.user_id):
                    robber_balance = get_balance(int(robber_id))
                    fine = min(robber_balance, 1000)
                    if fine > 0:
                        set_balance(int(robber_id), robber_balance - fine)
                        set_balance(self.user_id, get_balance(self.user_id) + fine)
                        arrests += 1

            if arrests > 0:
                return await interaction.response.send_message(f"🚨 You arrested {arrests} robber(s) and claimed fines!", ephemeral=False)
            else:
                return await interaction.response.send_message("🚨 No recent robbers had robbed you.", ephemeral=False)

@bot.command()
async def use(ctx):
    """Use an item from your inventory via UI"""
    user_id = ctx.author.id
    user_inv = get_inventory(user_id)

    if not any(i in user_inv for i in ["padlock", "phone"]):
        return await ctx.send("❌ You don't have any usable items right now.")

    view = UseItemView(user_id)
    embed = discord.Embed(
        title="🎒 Use an Item",
        description="Select an item and quantity, then click **Use Item** to activate it.",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed, view=view)



# --------------------STOCK----------------------

@bot.command()
async def stock(ctx):
    """Trade currencies in the stock market"""
    view = StockMarketView(ctx.author.id)
    embed = discord.Embed(
        title="📈 Stock Market",
        description="Select an action, currency, and amount to trade",
        color=discord.Color.gold()
    )
    
    prices = load_currency_prices()
    
    for currency in ["BobBux", "DxBux", "Gold"]:
        embed.add_field(
            name=f"{currency}",
            value=f"Price: {prices[currency]} coins",
            inline=True
        )
    
    embed.set_footer(text=f"Your balance: {get_balance(ctx.author.id)} coins")
    view.message = await ctx.send(embed=embed, view=view)

class StockMarketView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.action = None
        self.currency = None
        self.amount = 1
        self.message = None
        
        # Initialize dropdowns with default options
        self.action_dropdown = discord.ui.Select(
            placeholder="Select Action",
            options=[
                discord.SelectOption(label="Buy", value="buy", emoji="🛒"),
                discord.SelectOption(label="Sell", value="sell", emoji="💰")
            ],
            row=0
        )
        self.action_dropdown.callback = self.action_select
        self.add_item(self.action_dropdown)
        
        self.currency_dropdown = discord.ui.Select(
            placeholder="Select Currency",
            options=[
                discord.SelectOption(label="BobBux", value="BobBux", emoji="🔵"),
                discord.SelectOption(label="DxBux", value="DxBux", emoji="🟢"),
                discord.SelectOption(label="Gold", value="Gold", emoji="🟡")
            ],
            row=1,
            disabled=True
        )
        self.currency_dropdown.callback = self.currency_select
        self.add_item(self.currency_dropdown)
        
        self.amount_dropdown = discord.ui.Select(
            placeholder="Select Amount",
            options=[discord.SelectOption(label="1", value="1")],  # Default option
            row=2,
            disabled=True
        )
        self.amount_dropdown.callback = self.amount_select
        self.add_item(self.amount_dropdown)
        
        self.confirm_button = discord.ui.Button(
            label="Confirm Trade",
            style=discord.ButtonStyle.green,
            row=3,
            disabled=True,
            emoji="✅"
        )
        self.confirm_button.callback = self.confirm_trade
        self.add_item(self.confirm_button)

    async def update_ui_state(self, interaction: discord.Interaction):
        """Update UI components based on current selections"""
        self.currency_dropdown.disabled = self.action is None
        self.amount_dropdown.disabled = self.currency is None
        self.confirm_button.disabled = not (self.action and self.currency and self.amount)
        
        if interaction.response.is_done():
            await interaction.followup.edit_message(self.message.id, view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def action_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        
        self.action = interaction.data['values'][0]
        await self.update_ui_state(interaction)
        await interaction.followup.send(f"Selected action: **{self.action.capitalize()}**", ephemeral=True)

    async def currency_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        
        self.currency = interaction.data['values'][0]
        
        # Update amount options based on available funds/inventory
        user_balance = get_balance(self.user_id)
        user_inv = get_inventory(self.user_id)
        prices = load_currency_prices()
        
        if self.action == "buy":
            max_affordable = user_balance // prices[self.currency]
        else:  # sell
            max_affordable = user_inv.get(self.currency, 0)
        
        # Update amount dropdown
        self.amount_dropdown.options = []
        amounts = [1, 5, 10, 25, 50, 100]
        
        for amount in amounts:
            if amount <= max_affordable:
                self.amount_dropdown.options.append(
                    discord.SelectOption(label=str(amount), value=str(amount))
                )
        
        if max_affordable > 0 and (max_affordable > 100 or max_affordable not in amounts):
            self.amount_dropdown.options.append(
                discord.SelectOption(label=f"Max ({max_affordable})", value="max")
            )
        
        if self.amount_dropdown.options:
            self.amount = int(self.amount_dropdown.options[0].value)
        else:
            self.amount = 0
        
        await self.update_ui_state(interaction)
        await interaction.followup.send(f"Selected currency: **{self.currency}**", ephemeral=True)

    async def amount_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        
        selected = interaction.data['values'][0]
        if selected == "max":
            prices = load_currency_prices()
            user_balance = get_balance(self.user_id)
            user_inv = get_inventory(self.user_id)
            
            if self.action == "buy":
                self.amount = user_balance // prices[self.currency]
            else:  # sell
                self.amount = user_inv.get(self.currency, 0)
        else:
            self.amount = int(selected)
        
        await self.update_ui_state(interaction)
        await interaction.followup.send(f"Selected amount: **{self.amount}**", ephemeral=True)

    async def confirm_trade(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        
        prices = load_currency_prices()
        user_balance = get_balance(self.user_id)
        user_inv = get_inventory(self.user_id)
        
        if self.action == "buy":
            total_cost = prices[self.currency] * self.amount
            if user_balance < total_cost:
                return await interaction.response.send_message(
                    f"❌ You need {total_cost} coins but only have {user_balance}!",
                    ephemeral=True
                )
            
            # Execute buy
            set_balance(self.user_id, user_balance - total_cost)
            add_to_inventory(self.user_id, self.currency, self.amount)
            new_price = update_currency_price(self.currency, self.amount)
            
            await interaction.response.send_message(
                f"✅ Purchased {self.amount} {self.currency} for {total_cost} coins!\n"
                f"• New price: {new_price} coins\n"
                f"• Your balance: {user_balance - total_cost} coins\n"
                f"• Now own: {user_inv.get(self.currency, 0) + self.amount} {self.currency}"
            )
        
        elif self.action == "sell":
            current_owned = user_inv.get(self.currency, 0)
            if current_owned < self.amount:
                return await interaction.response.send_message(
                    f"❌ You only have {current_owned} {self.currency}!",
                    ephemeral=True
                )
            
            sell_price = int(prices[self.currency] * 0.9)  # 10% market fee
            total_earned = sell_price * self.amount
            
            # Execute sell
            set_balance(self.user_id, user_balance + total_earned)
            remove_from_inventory(self.user_id, self.currency, self.amount)
            update_currency_price(self.currency, -self.amount)  # Negative amount for selling
            
            await interaction.response.send_message(
                f"✅ Sold {self.amount} {self.currency} for {total_earned} coins!\n"
                f"• Current price: {prices[self.currency]} coins\n"
                f"• Your balance: {user_balance + total_earned} coins\n"
                f"• Remaining: {current_owned - self.amount} {self.currency}"
            )
        
        # Disable all components after trade
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)


# ------------------ WHEEL/BLACKJACK ------------------

def get_wheel_stats(user_id: int) -> Dict:
    try:
        with open("wheel_stats.json", "r") as f:
            all_stats = json.load(f)
            return all_stats.get(str(user_id), {"spins": 0, "total_won": 0, "biggest_win": 0})
    except FileNotFoundError:
        return {"spins": 0, "total_won": 0, "biggest_win": 0}

def update_wheel_stats(user_id: int, amount_won: int):
    try:
        with open("wheel_stats.json", "r") as f:
            all_stats = json.load(f)
    except FileNotFoundError:
        all_stats = {}
    
    user_stats = all_stats.get(str(user_id), {"spins": 0, "total_won": 0, "biggest_win": 0})
    user_stats["spins"] += 1
    user_stats["total_won"] += amount_won
    if amount_won > user_stats["biggest_win"]:
        user_stats["biggest_win"] = amount_won
    
    all_stats[str(user_id)] = user_stats
    
    with open("wheel_stats.json", "w") as f:
        json.dump(all_stats, f)

# Add this class for Blackjack
class BlackjackGame:
    def __init__(self, player_id: int, bet: int):
        self.player_id = player_id
        self.bet = bet
        self.deck = self.create_deck()
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
        self.outcome = ""
        self.payout = 0
        
        # Deal initial cards
        self.player_hand.append(self.draw_card())
        self.dealer_hand.append(self.draw_card())
        self.player_hand.append(self.draw_card())
        self.dealer_hand.append(self.draw_card())
    
    @staticmethod
    def create_deck() -> List[Dict]:
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['♥', '♦', '♣', '♠']
        deck = [{'rank': rank, 'suit': suit} for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck
    
    def draw_card(self) -> Dict:
        return self.deck.pop()
    
    def calculate_hand_value(self, hand: List[Dict]) -> int:
        value = 0
        aces = 0
        
        for card in hand:
            rank = card['rank']
            if rank in ['J', 'Q', 'K']:
                value += 10
            elif rank == 'A':
                value += 11
                aces += 1
            else:
                value += int(rank)
        
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
            
        return value
    
    def hit(self):
        if not self.game_over:
            self.player_hand.append(self.draw_card())
            if self.calculate_hand_value(self.player_hand) > 21:
                self.stand()
    
    def stand(self):
        if not self.game_over:
            self.game_over = True
            player_value = self.calculate_hand_value(self.player_hand)
            dealer_value = self.calculate_hand_value(self.dealer_hand)
            
            # Dealer draws until 17 or higher
            while dealer_value < 17 and player_value <= 21:
                self.dealer_hand.append(self.draw_card())
                dealer_value = self.calculate_hand_value(self.dealer_hand)
            
            # Determine outcome
            if player_value > 21:
                self.outcome = "Bust! You went over 21."
                self.payout = 0
            elif dealer_value > 21:
                self.outcome = "Dealer busts! You win!"
                self.payout = self.bet * 2
            elif player_value > dealer_value:
                self.outcome = f"You win! {player_value} vs {dealer_value}"
                self.payout = self.bet * 2
            elif player_value == dealer_value:
                self.outcome = f"Push! {player_value} vs {dealer_value}"
                self.payout = self.bet
            else:
                self.outcome = f"You lose! {player_value} vs {dealer_value}"
                self.payout = 0
    
    def get_hand_as_string(self, hand: List[Dict], hide_first: bool = False) -> str:
        if hide_first:
            return f"?? {hand[1]['rank']}{hand[1]['suit']}"
        return " ".join(f"{card['rank']}{card['suit']}" for card in hand)
    
    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(title="Blackjack", color=0x00FF00)
        
        dealer_value = "??" if not self.game_over else self.calculate_hand_value(self.dealer_hand)
        embed.add_field(
            name=f"Dealer's Hand ({dealer_value})",
            value=self.get_hand_as_string(self.dealer_hand, not self.game_over),
            inline=False
        )
        
        player_value = self.calculate_hand_value(self.player_hand)
        embed.add_field(
            name=f"Your Hand ({player_value})",
            value=self.get_hand_as_string(self.player_hand),
            inline=False
        )
        
        if self.game_over:
            embed.add_field(
                name="Result",
                value=f"{self.outcome}\nPayout: {self.payout} coins",
                inline=False
            )
            embed.color = 0xFF0000 if self.payout < self.bet else 0x00FF00
        
        embed.set_footer(text=f"Bet: {self.bet} coins")
        return embed

# Add this view for Blackjack
class BlackjackView(discord.ui.View):
    def __init__(self, game: BlackjackGame):
        super().__init__(timeout=60)
        self.game = game
    
    async def update_message(self, interaction: discord.Interaction):
        embed = self.game.get_embed()
        if self.game.game_over:
            await interaction.response.edit_message(embed=embed, view=None)
            # Update player's balance
            current_balance = get_balance(self.game.player_id)
            set_balance(self.game.player_id, current_balance - self.game.bet + self.game.payout)
        else:
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.player_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        self.game.hit()
        await self.update_message(interaction)
    
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.player_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        self.game.stand()
        await self.update_message(interaction)

# Add this view for Wheel
class WheelView(discord.ui.View):
    def __init__(self, user_id: int, bet: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.bet = bet
        self.spinning = False

    @discord.ui.button(label="Spin Wheel!", style=discord.ButtonStyle.primary, emoji="🎡")
    async def spin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your spin!", ephemeral=True)

        if self.spinning:
            return await interaction.response.send_message("Wheel is already spinning!", ephemeral=True)

        self.spinning = True
        button.disabled = True
        await interaction.message.edit(view=self)

        await interaction.response.defer()

        total_weight = sum(section["weight"] for section in WHEEL_SECTIONS)
        selected = random.choices(WHEEL_SECTIONS, weights=[s["weight"] for s in WHEEL_SECTIONS], k=1)[0]

        message = await interaction.followup.send("Spinning the wheel... 🎡")

        for _ in range(5):
            temp_selection = random.choice(WHEEL_SECTIONS)
            embed = discord.Embed(
                title="Wheel of Fortune",
                description=f"Bet: {self.bet} coins",
                color=temp_selection["color"]
            )
            embed.add_field(
                name="Result",
                value=f"Landed on: **{temp_selection['name']}**\n"
                      f"Payout: {int(self.bet * temp_selection['multiplier'])} coins",
                inline=False
            )
            await message.edit(embed=embed)
            await asyncio.sleep(0.5)

        winnings = int(self.bet * selected["multiplier"])
        embed = discord.Embed(
            title="Wheel of Fortune",
            description=f"Bet: {self.bet} coins",
            color=selected["color"]
        )
        embed.add_field(
            name="Final Result",
            value=f"Landed on: **{selected['name']}**\n"
                  f"Payout: {winnings} coins",
            inline=False
        )

        current_balance = get_balance(self.user_id)
        set_balance(self.user_id, current_balance - self.bet + winnings)
        update_wheel_stats(self.user_id, winnings)

        stats = get_wheel_stats(self.user_id)
        embed.add_field(
            name="Your Wheel Stats",
            value=f"Total spins: {stats['spins']}\n"
                  f"Total won: {stats['total_won']} coins\n"
                  f"Biggest win: {stats['biggest_win']} coins",
            inline=False
        )

        await message.edit(embed=embed)
        await interaction.message.delete()

# Replace the stub BJ command with this implementation
@bot.command(aliases=["blackjack"])
async def bj(ctx, amount: int):
    """Play a game of Blackjack"""
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")
    
    game = BlackjackGame(user_id, amount)
    view = BlackjackView(game)
    
    embed = game.get_embed()
    await ctx.send(embed=embed, view=view)

# Add this new wheel command
@bot.command(aliases=["spin"])
async def wheel(ctx, amount: int):
    """Spin the wheel of fortune with your bet"""
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")
    
    # Show wheel sections
    embed = discord.Embed(
        title="Wheel of Fortune",
        description=f"Bet: {amount} coins\n\n"
                   "Possible outcomes:",
        color=0x7289DA
    )
    
    for section in WHEEL_SECTIONS:
        embed.add_field(
            name=section["name"],
            value=f"{section['multiplier']}x payout",
            inline=True
        )
    
    view = WheelView(user_id, amount)
    await ctx.send(embed=embed, view=view)

# Add this command to check wheel stats
@bot.command()
async def wheelstats(ctx, member: discord.Member = None):
    """Check your wheel spin statistics"""
    user = member or ctx.author
    stats = get_wheel_stats(user.id)
    
    embed = discord.Embed(
        title=f"{user.display_name}'s Wheel Stats",
        color=0x7289DA
    )
    embed.add_field(name="Total Spins", value=stats["spins"], inline=True)
    embed.add_field(name="Total Won", value=f"{stats['total_won']} coins", inline=True)
    embed.add_field(name="Biggest Win", value=f"{stats['biggest_win']} coins", inline=True)
    
    await ctx.send(embed=embed)

# ------------------ PLINKO ------------------


def create_tilted_board() -> list:
    board = []
    for row in range(PLINKO_ROWS):
        line = []
        for col in range(PLINKO_WIDTH):
            if col % 2 == row % 2:
                line.append("🟡")  # Peg
            else:
                line.append("⬛")  # Empty space
        board.append(line)
    board.append(["🔳" if i in PLINKO_MULTIPLIERS else "⬛" for i in range(PLINKO_WIDTH)])
    return board

def render_tilted_board(board: list, ball_pos: tuple = None) -> str:
    display = [row.copy() for row in board]
    if ball_pos:
        row, col = ball_pos
        if 0 <= row < len(display) and 0 <= col < len(display[0]):
            display[row][col] = "🔴"
    return "\n".join("".join(r) for r in display)

@bot.command()
async def plinko(ctx, amount: int):
    user_id = ctx.author.id
    balance = get_balance(user_id)

    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if balance < amount:
        return await ctx.send("❌ You don't have enough coins.")

    board = create_tilted_board()
    col = PLINKO_WIDTH // 2
    message = await ctx.send(f"**Plinko Ball Drop!**\n{render_tilted_board(board, (0, col))}")

    for row in range(PLINKO_ROWS):
        await asyncio.sleep(0.2)
        move = random.choice([-1, 1])
        col = max(0, min(col + move, PLINKO_WIDTH - 1))
        await message.edit(content=f"**Plinko Ball Drop!**\n{render_tilted_board(board, (row + 1, col))}")

    # Final outcome
    multiplier = PLINKO_MULTIPLIERS.get(col, 0)
    winnings = int(amount * multiplier)
    set_balance(user_id, balance - amount + winnings)

    await asyncio.sleep(0.5)
    await message.edit(content=f"**Plinko Ball Drop!**\n{render_tilted_board(board, (PLINKO_ROWS, col))}\n\n"
                               f"🎯 Landed in slot {col + 1} ({multiplier}x)\n"
                               f"💰 You won **{winnings} coins**!")

# ------------------ COIN FLIP BUTTONS ------------------

class CoinFlipView(discord.ui.View):
    def __init__(self, user_id: int, bet_amount: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.has_responded = False

    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def update_balance_and_send_result(self, interaction: discord.Interaction, user_choice: str):
        if self.has_responded:
            await interaction.response.send_message("You already flipped!", ephemeral=True)
            return

        current_balance = get_balance(self.user_id)

        if self.bet_amount > current_balance:
            await interaction.response.send_message("You don't have enough balance for this bet!", ephemeral=True)
            await self.disable_all_items()
            await interaction.message.edit(view=self)
            return

        result = random.choice(["heads", "tails"])

        if result == user_choice:
            new_balance = current_balance + self.bet_amount
            outcome = f"🎉 It was **{result.capitalize()}**! You **won** {self.bet_amount} coins!"
        else:
            new_balance = current_balance - self.bet_amount
            outcome = f"😢 It was **{result.capitalize()}**. You **lost** {self.bet_amount} coins."

        set_balance(self.user_id, new_balance)
        self.has_responded = True
        bank_data = get_bank_data(self.user_id)  # Get bank data

        await self.disable_all_items()
        await interaction.message.edit(view=self)

        # Updated message format
        await interaction.response.send_message(
            f"{interaction.user.mention} {outcome}\n"
            f"• Wallet: **{new_balance} coins**\n"
            f"• Bank: **{bank_data['deposited']} coins**"
        )

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your coin flip!", ephemeral=True)
        await self.update_balance_and_send_result(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary)
    async def tails_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your coin flip!", ephemeral=True)
        await self.update_balance_and_send_result(interaction, "tails")

@bot.command()
async def cf(ctx, amount: int):
    user_id = ctx.author.id
    current_balance = get_balance(user_id)

    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")

    view = CoinFlipView(user_id, amount)
    await ctx.send(f"{ctx.author.mention}, choose Heads or Tails to flip the coin and bet **{amount}** coins!", view=view)

# ------------------ BALANCE CHECK COMMANDS ------------------

@bot.command(aliases=["balance"])
async def bal(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    balance = get_balance(member.id)
    bank_data = get_bank_data(member.id)
    plan_name = BANK_PLANS[bank_data['plan']]['name'] if bank_data['plan'] else 'No plan'
    
    # Check for active loan
    loan_data = get_loan(member.id)
    loan_info = ""
    if loan_data and not loan_data["repaid"]:
        due_date = datetime.fromtimestamp(loan_data["due_date"])
        loan_info = f"\n• Loan: ⚠️ **{loan_data['amount']} coins** (due {due_date.strftime('%Y-%m-%d')})"
    
    await ctx.send(
        f"**{member.display_name}'s balances:**\n"
        f"• Wallet: 💰 **{balance} coins**\n"
        f"• Bank: 🏦 **{bank_data['deposited']} coins** ({plan_name})"
        f"{loan_info}"
    )

@bot.command(aliases=["lb"])
async def leaderboard(ctx, type: str = "wallet"):
    """Show the wealth leaderboard (wallet, bank, or total)"""
    valid_types = ["wallet", "bank", "total"]
    if type.lower() not in valid_types:
        return await ctx.send(f"❌ Invalid type. Use: {', '.join(valid_types)}")

    balances = load_balances()
    bank_data = load_bank_data()

    # Prepare leaderboard data
    lb_data = []
    for user_id, balance in balances.items():
        bank_amount = bank_data.get(user_id, {}).get("deposited", 0)
        if type == "wallet":
            amount = balance
        elif type == "bank":
            amount = bank_amount
        else:  # total
            amount = balance + bank_amount

        # Try to get member name
        try:
            member = await ctx.guild.fetch_member(int(user_id))
            name = member.display_name
        except:
            name = f"User {user_id}"

        lb_data.append((name, amount))

    # Sort and get top 10
    lb_data.sort(key=lambda x: x[1], reverse=True)
    top_10 = lb_data[:10]

    # Create embed
    embed = discord.Embed(
        title=f"🏆 {type.capitalize()} Balance Leaderboard",
        color=discord.Color.gold()
    )

    for i, (name, amount) in enumerate(top_10, 1):
        embed.add_field(
            name=f"{i}. {name}",
            value=f"{amount:,} coins",
            inline=False
        )

    # Add current user's position if not in top 10
    current_user_id = str(ctx.author.id)
    if current_user_id in balances:
        current_pos = next(
            (i+1 for i, (uid, _) in enumerate(lb_data) if uid == ctx.author.display_name),
            len(lb_data)
        )
        current_amount = next(
            (amt for uid, amt in lb_data if uid == ctx.author.display_name),
            0
        )
        
        if current_pos > 10:
            embed.add_field(
                name=f"Your Position: #{current_pos}",
                value=f"{current_amount:,} coins",
                inline=False
            )

    await ctx.send(embed=embed)

# ------------------ ADMIN CHECK DECORATOR ------------------

def is_admin():
    async def predicate(ctx):
        allowed_user_id = 1077532065093922876  # Replace with your Discord user ID
        if ctx.author.id == allowed_user_id:
            return True
        await ctx.send("❌ You are not authorized to use this command.")
        return False
    return commands.check(predicate)

# ------------------ ADMIN COMMANDS ------------------

@bot.command(aliases=["setbalance", "setbal"])
@is_admin()
async def admin_setbal(ctx, member: discord.Member, amount: int):
    if amount < 0:
        return await ctx.send("❌ Balance cannot be negative.")
    set_balance(member.id, amount)
    await ctx.send(f"✅ Set {member.display_name}'s wallet balance to **{amount} coins**.")

@bot.command()
@is_admin()
async def checkall(ctx):
    """Export all user data including unlimited currencies"""
    balances = load_balances()
    bank_data = load_bank_data()
    loans = load_loans()
    inventories = load_inventories()
    currency_prices = load_currency_prices()
    
    output = ["=== MARKET DATA ==="]
    for currency in ["BobBux", "DxBux", "Gold"]:
        # Show price with INF for unlimited supply
        output.append(f"MARKET|{currency}|{currency_prices[currency]}|INF")  
    
    output.append("\n=== USER DATA ===")
    all_user_ids = set(balances.keys()) | set(bank_data.keys()) | set(loans.keys()) | set(inventories.keys())
    
    for user_id in all_user_ids:
        wallet = balances.get(user_id, 1000)
        b_data = bank_data.get(user_id, {"plan": None, "deposited": 0})
        plan = b_data["plan"] or "None"
        deposited = b_data["deposited"]
        
        loan_info = loans.get(user_id, {})
        has_loan = "Y" if loan_info and not loan_info.get("repaid", True) else "N"
        
        inv_info = inventories.get(user_id, {})
        # Ensure all currencies are included with exact quantities
        for currency in ["BobBux", "DxBux", "Gold"]:
            if currency not in inv_info:
                inv_info[currency] = 0
        
        # Format inventory with currencies first
        inv_parts = []
        for currency in ["BobBux", "DxBux", "Gold"]:
            inv_parts.append(f"{currency}:{inv_info.get(currency, 0)}")
        # Add other items
        inv_parts.extend(f"{k}:{v}" for k,v in inv_info.items() if k not in ["BobBux", "DxBux", "Gold"])
        
        inv_str = ",".join(inv_parts) if inv_parts else "None"
        
        output.append(f"{user_id}|{wallet}|{plan}|{deposited}|{has_loan}|{inv_str}")
    
    # Split into chunks if too long
    chunk_size = 1900
    chunks = []
    current_chunk = ""
    
    for line in output:
        if len(current_chunk) + len(line) + 1 > chunk_size:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += "\n" + line if current_chunk else line
    
    if current_chunk:
        chunks.append(current_chunk)
    
    for chunk in chunks:
        await ctx.send(f"```{chunk}```")

@bot.command()
@is_admin()
async def setall(ctx, *, data: str):
    """Import all user data with unlimited currencies"""
    if data.startswith('```') and data.endswith('```'):
        data = data[3:-3].strip()
    
    lines = data.split('\n')
    balances = {}
    bank_data = {}
    loans = {}
    inventories = {}
    currency_prices = load_currency_prices()  # Start with current prices
    
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if line == "=== MARKET DATA ===":
            current_section = "market"
            continue
        elif line == "=== USER DATA ===":
            current_section = "user"
            continue
        
        if current_section == "market":
            if line.startswith("MARKET|"):
                parts = line.split('|')
                if len(parts) >= 3:  # Only need currency and price
                    currency = parts[1]
                    try:
                        currency_prices[currency] = int(parts[2])
                        # Ignore stock quantity (parts[3]) since unlimited
                    except (ValueError, KeyError):
                        continue
        
        elif current_section == "user":
            parts = line.split('|')
            if len(parts) >= 5:
                try:
                    user_id = parts[0].strip()
                    wallet = int(float(parts[1].strip()))  # Handle scientific notation
                    plan = parts[2].strip()
                    deposited = float(parts[3].strip())
                    has_loan = parts[4].strip().upper() == "Y"
                    inventory = parts[5].strip() if len(parts) > 5 else "None"
                    
                    balances[user_id] = wallet
                    bank_data[user_id] = {
                        "plan": None if plan.lower() == "none" else plan.lower(),
                        "deposited": deposited,
                        "last_interest_claim": 0,
                        "pending_interest": 0
                    }
                    
                    if has_loan:
                        loans[user_id] = {
                            "amount": 1000,
                            "interest_rate": 0.1,
                            "due_date": (datetime.now() + timedelta(days=7)).timestamp(),
                            "created_at": datetime.now().timestamp(),
                            "repaid": False
                        }
                    
                    # Process inventory with exact quantities
                    inv_items = {}
                    if inventory.lower() != "none":
                        for item_str in inventory.split(','):
                            if ':' in item_str:
                                item_name, quantity = item_str.split(':')
                                try:
                                    inv_items[item_name.strip()] = int(quantity)
                                except ValueError:
                                    continue
                    
                    # Ensure all currencies exist with their exact values
                    for currency in ["BobBux", "DxBux", "Gold"]:
                        if currency not in inv_items:
                            # Only set to 0 if not explicitly provided
                            if not any(c in inventory for c in ["BobBux", "DxBux", "Gold"]):
                                inv_items[currency] = 0
                    
                    inventories[user_id] = inv_items
                
                except (ValueError, IndexError) as e:
                    print(f"Error processing line: {line} - {e}")
                    continue
    
    # Save all data (without stock limits)
    save_balances(balances)
    save_bank_data(bank_data)
    save_loans(loans)
    save_inventories(inventories)
    save_currency_prices(currency_prices)
    
    # Create detailed response
    embed = discord.Embed(
        title="✅ Data Import Complete",
        description="Successfully imported unlimited currency economy",
        color=discord.Color.green()
    )
    
    # Count currency holders
    currency_holders = {
        "BobBux": sum(1 for inv in inventories.values() if inv.get("BobBux", 0) > 0),
        "DxBux": sum(1 for inv in inventories.values() if inv.get("DxBux", 0) > 0),
        "Gold": sum(1 for inv in inventories.values() if inv.get("Gold", 0) > 0)
    }
    
    embed.add_field(
        name="User Data",
        value=f"• {len(balances)} balances\n• {len(bank_data)} bank accounts\n• {len(loans)} loans",
        inline=False
    )
    
    embed.add_field(
        name="Currency Holders",
        value=f"• BobBux: {currency_holders['BobBux']}\n• DxBux: {currency_holders['DxBux']}\n• Gold: {currency_holders['Gold']}",
        inline=True
    )
    
    embed.add_field(
        name="Current Prices",
        value=f"• BobBux: {currency_prices['BobBux']}\n• DxBux: {currency_prices['DxBux']}\n• Gold: {currency_prices['Gold']}",
        inline=True
    )
    
    await ctx.send(embed=embed)

# ------------------ KEEP ALIVE (FLASK) ------------------

app = Flask("")

@app.route("/")
def home():
    return "I'm alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ------------------ RUN BOT ------------------

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
