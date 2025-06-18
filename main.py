import os
import time
import discord
import asyncio
from typing import List, Dict, Tuple
from discord.ext import commands, tasks
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

def update_balance(user_id: int, amount: int):
    balances = load_balances()
    balances[str(user_id)] = balances.get(str(user_id), 0) + amount
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

def update_currency_price(currency_name: str, amount: int, is_buy: bool) -> int:
    """Update currency price based on market activity"""
    prices = load_currency_prices()
    stocks = load_currency_stocks()
    
    current_price = prices[currency_name]
    current_stock = stocks[currency_name]
    
    if is_buy:
        # When buying - price increases based on percentage of stock purchased
        if current_stock > 0:
            purchase_percent = (amount / current_stock) * 100
            # Price increases by purchase percentage (capped at 20% increase)
            price_increase = min(purchase_percent, 20)
            new_price = current_price * (1 + (price_increase / 100))
        else:
            # If stock is empty, apply a standard 10% increase
            new_price = current_price * 1.10
        
        # Ensure at least 1% increase
        new_price = max(new_price, current_price * 1.01)
        
        # Reduce available stock
        stocks[currency_name] -= amount
    else:
        # When selling - price decreases based on percentage of stock sold
        total_stock = stocks[currency_name] + amount  # Stock before selling
        if total_stock > 0:
            sale_percent = (amount / total_stock) * 100
            # Price decreases by sale percentage (capped at 15% decrease)
            price_decrease = min(sale_percent, 15)
            new_price = current_price * (1 - (price_decrease / 100))
        else:
            # Shouldn't happen, but just in case
            new_price = current_price * 0.95
        
        # Ensure at least 1% decrease
        new_price = min(new_price, current_price * 0.99)
        
        # Increase available stock
        stocks[currency_name] += amount
    
    # Round to nearest integer and ensure minimum price of 1
    new_price = max(1, int(round(new_price)))
    
    prices[currency_name] = new_price
    save_currency_prices(prices)
    save_currency_stocks(stocks)
    
    return new_price

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


# ------------------ TRADING ------------------


@bot.command()
async def trade(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        return await ctx.send("You can't trade with yourself.")
    await ctx.send(f"{ctx.author.mention} is starting a trade with {member.mention}...")
    await ctx.send("Please select what you want to offer:", view=TradeOfferView(ctx.author, member))


# --- Trade UI ---

class TradeOfferView(discord.ui.View):
    def __init__(self, initiator, recipient):
        super().__init__(timeout=120)
        self.initiator = initiator
        self.recipient = recipient
        self.offered_items = {}  # item_name: quantity
        self.offered_coins = 0

    @discord.ui.select(
        placeholder="Select items to offer", min_values=1, max_values=5,
        options=[
            discord.SelectOption(label="BobBux", value="BobBux"),
            discord.SelectOption(label="DxBux", value="DxBux"),
            discord.SelectOption(label="Gold", value="Gold"),
            discord.SelectOption(label="Phone", value="Phone"),
            discord.SelectOption(label="Padlock", value="Padlock"),
        ]
    )
    async def select_items(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user != self.initiator:
            return await interaction.response.send_message("You can't modify this trade.", ephemeral=True)

        # Set default quantity = 1 for all selected items
        self.offered_items = {item: 1 for item in select.values}
        await interaction.response.send_message(
            f"Selected items: {', '.join(select.values)}. Use 'Set Quantities' button to edit amounts.",
            ephemeral=True
        )

    @discord.ui.button(label="Set Quantities", style=discord.ButtonStyle.primary)
    async def set_quantities(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.initiator:
            return await interaction.response.send_message("You can't modify this trade.", ephemeral=True)

        if not self.offered_items:
            return await interaction.response.send_message("Please select items first.", ephemeral=True)

        # Open modal with inputs for each selected item
        await interaction.response.send_modal(SetQuantitiesModal(self))


    @discord.ui.button(label="Add Coins", style=discord.ButtonStyle.blurple)
    async def add_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.initiator:
            return await interaction.response.send_message("You can't modify this trade.", ephemeral=True)
        await interaction.response.send_modal(CoinModal(self))

    @discord.ui.button(label="Confirm Offer", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.initiator:
            return await interaction.response.send_message("You can't confirm this trade.", ephemeral=True)

        # Optionally verify quantities > 0
        for qty in self.offered_items.values():
            if qty <= 0:
                return await interaction.response.send_message("Quantities must be positive.", ephemeral=True)

        await interaction.message.edit(content="What do you want in return from the recipient?", view=TradeRequestView(
            self.initiator, self.recipient, self.offered_items, self.offered_coins
        ))

class SetQuantitiesModal(discord.ui.Modal, title="Set Quantities for Offered Items"):
    def __init__(self, trade_view: TradeOfferView):
        super().__init__()
        self.trade_view = trade_view

        # Dynamically create a TextInput for each item selected
        for item in self.trade_view.offered_items.keys():
            default_value = str(self.trade_view.offered_items[item])
            self.add_item(
                discord.ui.TextInput(
                    label=f"Quantity for {item}",
                    default=default_value,
                    placeholder="Enter quantity",
                    required=True,
                    style=discord.TextStyle.short,
                    max_length=5
                )
            )

    async def on_submit(self, interaction: discord.Interaction):
        # Read quantities from text inputs, validate and update
        new_quantities = {}
        try:
            for item, text_input in zip(self.trade_view.offered_items.keys(), self.children):
                val = int(text_input.value)
                if val <= 0:
                    raise ValueError(f"Quantity for {item} must be positive")
                new_quantities[item] = val
        except ValueError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)

        self.trade_view.offered_items = new_quantities
        await interaction.response.send_message(
            f"Updated quantities: {', '.join(f'{k}: {v}' for k,v in new_quantities.items())}",
            ephemeral=True
        )


class CoinModal(discord.ui.Modal, title="Enter coins to offer"):
    amount = discord.ui.TextInput(label="Coins", placeholder="Amount to offer", required=True)

    def __init__(self, view_ref):
        super().__init__()
        self.view_ref = view_ref

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.amount.value)
            if value <= 0:
                raise ValueError
            balance = get_balance(self.view_ref.initiator.id)
            if value > balance:
                return await interaction.response.send_message("You don't have enough coins.", ephemeral=True)
            self.view_ref.offered_coins = value
            await interaction.response.send_message(f"Offering {value} coins.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Enter a valid positive number.", ephemeral=True)


class TradeRequestView(discord.ui.View):
    def __init__(self, initiator, recipient, offered_items, offered_coins):
        super().__init__(timeout=120)
        self.initiator = initiator
        self.recipient = recipient
        self.offered_items = offered_items
        self.offered_coins = offered_coins
        self.requested_items = {}
        self.requested_coins = 0

    @discord.ui.select(
        placeholder="What do you want in return?", min_values=1, max_values=5,
        options=[
            discord.SelectOption(label="BobBux"),
            discord.SelectOption(label="DxBux"),
            discord.SelectOption(label="Gold"),
            discord.SelectOption(label="Phone"),
            discord.SelectOption(label="Padlock"),
        ]
    )
    async def want_items(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user != self.initiator:
            return await interaction.response.send_message("You can't modify this trade.", ephemeral=True)

        self.requested_items = {item: 1 for item in select.values}
        await interaction.response.send_message(f"Requested: {', '.join(select.values)} (default 1)", ephemeral=True)

    @discord.ui.button(label="Request Coins", style=discord.ButtonStyle.blurple)
    async def request_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.initiator:
            return await interaction.response.send_message("You can't modify this trade.", ephemeral=True)
        await interaction.response.send_modal(RequestCoinModal(self))

    @discord.ui.button(label="Send Trade Request", style=discord.ButtonStyle.success)
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.initiator:
            return await interaction.response.send_message("Only the initiator can send this trade.", ephemeral=True)

        embed = discord.Embed(
            title="Trade Offer",
            description=f"{self.initiator.mention} wants to trade with you.",
            color=discord.Color.blue()
        )
        embed.add_field(name="They offer", value=f"{self.offered_items} + {self.offered_coins} coins", inline=False)
        embed.add_field(name="They want", value=f"{self.requested_items} + {self.requested_coins} coins", inline=False)

        view = TradeAcceptView(
            self.initiator, self.recipient,
            self.offered_items, self.offered_coins,
            self.requested_items, self.requested_coins
        )

        await interaction.channel.send(
            f"{self.recipient.mention}, you have a new trade request!",
            embed=embed,
            view=view
        )


class RequestCoinModal(discord.ui.Modal, title="Enter coins to request"):
    amount = discord.ui.TextInput(label="Coins", placeholder="Amount to request", required=True)

    def __init__(self, view_ref):
        super().__init__()
        self.view_ref = view_ref

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.amount.value)
            if value <= 0:
                raise ValueError
            self.view_ref.requested_coins = value
            await interaction.response.send_message(f"Requesting {value} coins.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Enter a valid positive number.", ephemeral=True)


class TradeAcceptView(discord.ui.View):
    def __init__(self, user1, user2, offer1_items, offer1_coins, want_items, want_coins):
        super().__init__(timeout=60)
        self.user1 = user1
        self.user2 = user2
        self.offer1_items = offer1_items
        self.offer1_coins = offer1_coins
        self.want_items = want_items
        self.want_coins = want_coins

    @discord.ui.button(label="Accept ✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user2:
            return await interaction.response.send_message("You're not the recipient!", ephemeral=True)

        inv1 = get_inventory(self.user1.id)
        inv2 = get_inventory(self.user2.id)
        bal1 = get_balance(self.user1.id)
        bal2 = get_balance(self.user2.id)

        for item, qty in self.offer1_items.items():
            if inv1.get(item, 0) < qty:
                return await interaction.response.send_message("Initiator doesn't have enough items.", ephemeral=True)

        for item, qty in self.want_items.items():
            if inv2.get(item, 0) < qty:
                return await interaction.response.send_message("Recipient doesn't have requested items.", ephemeral=True)

        if bal1 < self.offer1_coins or bal2 < self.want_coins:
            return await interaction.response.send_message("Not enough coins for the trade.", ephemeral=True)

        # Execute item trade
        for item, qty in self.offer1_items.items():
            inv1[item] -= qty
            inv2[item] = inv2.get(item, 0) + qty

        for item, qty in self.want_items.items():
            inv2[item] -= qty
            inv1[item] = inv1.get(item, 0) + qty

        # Execute coin trade
        update_balance(self.user1.id, -self.offer1_coins)
        update_balance(self.user2.id, self.offer1_coins)
        update_balance(self.user2.id, -self.want_coins)
        update_balance(self.user1.id, self.want_coins)

        save_inventories({str(self.user1.id): inv1, str(self.user2.id): inv2})
        await interaction.message.edit(content="✅ Trade completed successfully!", view=None)

    @discord.ui.button(label="Decline ❌", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user2:
            return await interaction.response.send_message("You're not the recipient!", ephemeral=True)
        await interaction.message.edit(content="❌ Trade was declined.", view=None)



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


class InterestView(discord.ui.View):
    def __init__(self, ctx, user_id):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.user_id = user_id
        self.bank_data = None
        self.claimed = False
        self.days_passed = 1
        self.total_interest = 0
        self.total_return_percent = 0
        self.message = None

    async def initialize(self):
        self.bank_data = get_bank_data(self.user_id)

    def create_embed(self):
        deposited = int(self.bank_data["deposited"])
        plan = self.bank_data["plan"]
        rate = BANK_PLANS[plan]["interest"] * 100 if plan else 0

        embed = discord.Embed(title="💰 Interest Summary", color=discord.Color.green())
        embed.set_author(name=self.ctx.author.display_name,
                         icon_url=self.ctx.author.display_avatar.url)

        embed.add_field(name="Deposited", value=f"**{deposited:,} coins**", inline=False)
        embed.add_field(name="Daily Interest Rate", value=f"**{rate:.2f}%**", inline=False)

        if self.claimed:
            embed.add_field(name="Days Passed", value=f"**{self.days_passed}**", inline=False)
            embed.add_field(name="Total Interest Gained", value=f"**+{int(self.total_interest):,} coins**", inline=False)
            embed.add_field(name="New Balance", value=f"**{int(self.bank_data['deposited']):,} coins**", inline=False)
            embed.add_field(name="Effective Total Return", value=f"**{self.total_return_percent:.2f}%**", inline=False)
            embed.set_footer(text="✅ Interest successfully claimed!")
        else:
            embed.set_footer(text="Click below to claim your interest.")

        return embed

    @discord.ui.button(label="Claim Interest", style=discord.ButtonStyle.green)
    async def claim_interest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This isn't your interest panel.", ephemeral=True)

        current_time = time.time()
        last_claim = self.bank_data.get("last_interest_claim")

        if last_claim and current_time - last_claim < 86400:
            remaining = 86400 - (current_time - last_claim)
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return await interaction.response.send_message(
                f"⌛ Come back in **{hours}h {minutes}m** to claim more interest!",
                ephemeral=True
            )

        self.days_passed = max(1, min(30, int((current_time - last_claim) // 86400))) if last_claim else 1

        rate = BANK_PLANS[self.bank_data["plan"]]["interest"]
        base = self.bank_data["deposited"]
        principal = base
        total = 0

        for _ in range(self.days_passed):
            interest = principal * rate
            total += interest
            principal += interest

        self.bank_data["deposited"] = int(principal)
        self.bank_data["last_interest_claim"] = current_time
        update_bank_data(self.user_id, self.bank_data)

        self.claimed = True
        self.total_interest = total
        self.total_return_percent = (total / base) * 100 if base else 0

        button.disabled = True
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

@bot.command()
async def interest(ctx):
    """Claim interest on your bank deposits"""
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)

    if bank_data["plan"] is None:
        return await ctx.send("❌ You don't have a bank plan. Use `-bank` to get started.")

    if bank_data["deposited"] == 0:
        return await ctx.send("❌ You don't have any coins deposited to earn interest.")

    view = InterestView(ctx, user_id)
    await view.initialize()

    message = await ctx.send(embed=view.create_embed(), view=view)
    view.message = message
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
            shop_items = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        shop_items = {
            "padlock": {
                "name": "Padlock",
                "price": 500,
                "description": "Protects against 5 robbery attempts (stacks)",
                "max_stack": 10,
                "usable": True
            },
            "phone": {
                "name": "Phone",
                "price": 1000,
                "description": "Call police to arrest recent robbers (last 5 minutes)",
                "max_stack": 1,
                "usable": True
            },
            "midas_touch": {
                "name": "Midas's Touch",
                "price": 5000,
                "description": "Turns 100 coins into 100 gold every 5 minutes (limited edition)",
                "max_stack": 1,
                "usable": False,
                "limited_edition": True,
                "available_until": time.time() + 3600  # Available for 1 hour after launch
            }
        }
        save_shop_items(shop_items)
    
    # Ensure all items have required fields
    for item_id, item_data in shop_items.items():
        item_data.setdefault("usable", False)
        item_data.setdefault("max_stack", 1)
        item_data.setdefault("limited_edition", False)
    
    return shop_items

def save_shop_items(shop_items):
    with open(SHOP_ITEMS_FILE, "w") as f:
        json.dump(shop_items, f)

def load_inventories():
    try:
        with open(INVENTORY_FILE, "r") as f:
            data = json.load(f)
            # Convert old format to new format if needed
            inventories = {}
            shop_items = load_shop_items().keys()
            
            for user_id, items in data.items():
                if isinstance(items, list):  # Old format
                    new_items = {}
                    for item in items:
                        if isinstance(item, dict) and "name" in item:
                            new_items[item["name"]] = item.get("quantity", 1)
                        elif isinstance(item, str):
                            new_items[item] = new_items.get(item, 0) + 1
                    inventories[user_id] = new_items
                else:
                    inventories[user_id] = items
                    
                # Ensure all shop items exist
                for item_id in shop_items:
                    if item_id not in inventories[user_id]:
                        inventories[user_id][item_id] = 0
                        
            return inventories
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def add_to_inventory(user_id, item_name, quantity=1):
    inventories = load_inventories()
    user_inv = inventories.setdefault(str(user_id), {})
    
    # Initialize if doesn't exist
    if item_name not in user_inv:
        user_inv[item_name] = 0
        
    # Check max stack for non-currency items
    if item_name not in ["BobBux", "DxBux", "Gold"]:
        shop_items = load_shop_items()
        max_stack = shop_items.get(item_name, {}).get("max_stack", 1)
        if user_inv[item_name] + quantity > max_stack:
            return False
    
    user_inv[item_name] += quantity
    save_inventories(inventories)
    return True

def remove_from_inventory(user_id, item_name, quantity=1):
    inventories = load_inventories()
    user_inv = inventories.get(str(user_id), {})
    
    if item_name not in user_inv or user_inv[item_name] < quantity:
        return False
    
    user_inv[item_name] -= quantity
    if user_inv[item_name] <= 0:
        user_inv[item_name] = 0  # Keep the key but set to 0
    
    save_inventories(inventories)
    return True


def save_inventories(inventories):
    with open(INVENTORY_FILE, "w") as f:
        json.dump(inventories, f, indent=4)

def load_rob_protection():
    try:
        with open(ROB_PROTECTION_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_rob_protection(protection_data):
    with open(ROB_PROTECTION_FILE, "w") as f:
        json.dump(protection_data, f, indent=4)

def load_rob_history():
    try:
        with open(ROB_HISTORY_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_rob_history(history_data):
    with open(ROB_HISTORY_FILE, "w") as f:
        json.dump(history_data, f, indent=4)

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
    current_time = time.time()
    
    # Filter out limited edition items that are expired
    available_items = {
        k: v for k, v in shop_items.items() 
        if not v.get("limited_edition", False) or v.get("available_until", 0) > current_time
    }
    
    await ctx.send(embed=discord.Embed(
        title="🛒 Shop",
        description="Select a quantity then press Buy!",
        color=discord.Color.green()
    ))

    for item_id, item_data in available_items.items():
        view = ShopItemRow(ctx.author.id, item_id, item_data)
        embed = discord.Embed(
            title=item_data["name"],
            description=f"{item_data['description']}\nPrice: {item_data['price']} coins",
            color=discord.Color.blurple()
        )
        
        # Show time remaining for limited edition items
        if item_id == "midas_touch":
            time_left = item_data["available_until"] - current_time
            if time_left > 0:
                minutes = int(time_left // 60)
                seconds = int(time_left % 60)
                embed.add_field(
                    name="⏳ Limited Time Offer",
                    value=f"Available for: {minutes}m {seconds}s",
                    inline=False
                )
        
        await ctx.send(embed=embed, view=view)


class UseItemDropdown(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id
        self.user_inv = get_inventory(user_id)
        shop_items = load_shop_items()
        
        options = []
        for item_id, item_data in shop_items.items():
            if item_data.get("usable", False) and self.user_inv.get(item_id, 0) > 0:
                emoji = "🔒" if item_id == "padlock" else "📱"
                options.append(discord.SelectOption(
                    label=f"{item_data['name']} (x{self.user_inv[item_id]})",
                    value=item_id,
                    emoji=emoji
                ))
        
        if not options:
            options.append(discord.SelectOption(
                label="No usable items",
                value="none",
                description="Buy items from the shop first"
            ))

        super().__init__(
            placeholder="Select item to use",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_item = self.values[0]
        await interaction.response.defer()

class UseQuantitySelect(discord.ui.Select):
    def __init__(self, max_amount: int, row: int = 1):
        options = [discord.SelectOption(label=str(i), value=str(i)) for i in range(1, max_amount + 1)]
        super().__init__(
            placeholder="Select quantity",
            min_values=1,
            max_values=1,
            options=options,
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_quantity = int(self.values[0])
        await interaction.response.defer()


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

class StockMarketView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.action = None
        self.currency = None
        self.amount = 1
        self.message = None
        
    async def update_message(self, interaction: discord.Interaction = None):
        prices = load_currency_prices()
        stocks = load_currency_stocks()
        user_balance = get_balance(self.user_id)
        user_inv = get_inventory(self.user_id)
        
        embed = discord.Embed(title="📈 Stock Market", color=discord.Color.gold())
        
        # Show current selections at the top
        if self.action and self.currency:
            embed.description = (
                f"**Selected Action:** {self.action.upper()}\n"
                f"**Selected Currency:** {self.currency}\n"
                f"**Selected Amount:** {self.amount}\n\n"
                f"Current Price: {prices[self.currency]} coins"
            )
        
        for currency in ["BobBux", "DxBux", "Gold"]:
            price_change = ""
            # You might want to track previous prices to show % changes
            embed.add_field(
                name=f"{currency}",
                value=(
                    f"Price: {prices[currency]} coins\n"
                    f"Stock: {stocks[currency]}\n"
                    f"You own: {user_inv.get(currency, 0)}\n"
                    f"{price_change}"
                ),
                inline=True
            )
        
        embed.set_footer(text=f"Your balance: {user_balance} coins")
        
        if interaction and interaction.response.is_done():
            await interaction.followup.edit_message(self.message.id, embed=embed, view=self)
        elif interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, row=3)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
    
        if not self.action or not self.currency or not self.amount:
            return await interaction.response.send_message("Please complete all selections before confirming.", ephemeral=True)
    
        prices = load_currency_prices()
        stocks = load_currency_stocks()
        user_balance = get_balance(self.user_id)
        user_inv = get_inventory(self.user_id)
    
        currency = self.currency
        price = prices[currency]
        stock = stocks[currency]
        amount = self.amount
        total_price = price * amount

        if self.action == "buy":
            if total_price > user_balance:
                return await interaction.response.send_message("You don't have enough coins.", ephemeral=True)
            if amount > stock:
                return await interaction.response.send_message("Not enough stock available.", ephemeral=True)

            # Buy logic with price update
            new_price = update_currency_price(currency, amount, is_buy=True)
            set_balance(self.user_id, user_balance - total_price)
            user_inv[currency] = user_inv.get(currency, 0) + amount

        elif self.action == "sell":
            if user_inv.get(currency, 0) < amount:
                return await interaction.response.send_message("You don't have enough to sell.", ephemeral=True)

            # Sell logic with price update
            new_price = update_currency_price(currency, amount, is_buy=False)
            set_balance(self.user_id, user_balance + (price * amount))
            user_inv[currency] -= amount

        # Save results
        inventories = load_inventories()
        inventories[str(self.user_id)] = user_inv
        save_inventories(inventories)

        await interaction.response.send_message(
            f"✅ You {self.action}ed {amount} {currency} for {total_price} coins.\n"
            f"New {currency} price: {new_price} coins (was {price})",
            ephemeral=True
        )
        await self.update_message()


    @discord.ui.select(
        placeholder="Select Action (Buy/Sell)",
        options=[discord.SelectOption(label="Buy", value="buy"), discord.SelectOption(label="Sell", value="sell")],
        row=0
    )
    async def action_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        self.action = select.values[0]
        await self.update_message(interaction)
        # Send confirmation of selection
        await interaction.followup.send(f"You selected to **{self.action}**", ephemeral=True)
    
    @discord.ui.select(
        placeholder="Select Currency",
        options=[
            discord.SelectOption(label="BobBux", value="BobBux", description="Volatile market"), 
            discord.SelectOption(label="DxBux", value="DxBux", description="Stable growth"),
            discord.SelectOption(label="Gold", value="Gold", description="Premium currency")
        ],
        row=1
    )
    async def currency_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        self.currency = select.values[0]
        await self.update_message(interaction)
        # Send confirmation of selection
        await interaction.followup.send(f"You selected **{self.currency}**", ephemeral=True)
    
    @discord.ui.select(
        placeholder="Select Amount",
        options=[discord.SelectOption(label=str(i), value=str(i)) for i in [1, 5, 10, 25, 50, 100, "Max"]],
        row=2
    )
    async def amount_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        
        selected = select.values[0]
        if selected == "Max":
            prices = load_currency_prices()
            user_balance = get_balance(self.user_id)
            user_inv = get_inventory(self.user_id)
            
            if self.action == "buy":
                max_possible = min(
                    user_balance // prices[self.currency],
                    load_currency_stocks()[self.currency]
                )
            else:  # sell
                max_possible = user_inv.get(self.currency, 0)
            
            self.amount = max_possible if max_possible > 0 else 1
        else:
            self.amount = int(selected)
            
        await self.update_message(interaction)
        # Send confirmation of selection
        await interaction.followup.send(f"Amount set to **{self.amount}**", ephemeral=True)

@bot.command()
async def stock(ctx):
    """Open the stock market interface"""
    view = StockMarketView(ctx.author.id)
    embed = discord.Embed(
        title="📈 Stock Market",
        description="Select an action, currency, and amount to trade",
        color=discord.Color.gold()
    )
    
    prices = load_currency_prices()
    stocks = load_currency_stocks()
    
    for currency in ["BobBux", "DxBux", "Gold"]:
        embed.add_field(
            name=f"{currency}",
            value=f"Price: {prices[currency]} coins\nStock: {stocks[currency]}",
            inline=True
        )
    
    embed.set_footer(text=f"Your balance: {get_balance(ctx.author.id)} coins")
    view.message = await ctx.send(embed=embed, view=view)

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
    member = member or ctx.author
    view = BalanceView(member.id, ctx)
    await view.initialize()
    await view.send_initial_message(ctx)

class BalanceView(discord.ui.View):
    def __init__(self, user_id: int, ctx):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.ctx = ctx
        self.member = None
        self.current_mode = "wallet"
        self.message = None

    async def initialize(self):
        self.member = self.ctx.guild.get_member(self.user_id)
        if not self.member:
            try:
                self.member = await self.ctx.guild.fetch_member(self.user_id)
            except discord.NotFound:
                self.member = await bot.fetch_user(self.user_id)

    async def send_initial_message(self, ctx):
        embed = self.create_embed()
        self.message = await ctx.send(embed=embed, view=self)

    def create_embed(self):
        # Dummy data - replace with actual data fetching
        balance = get_balance(self.user_id)
        bank_data = get_bank_data(self.user_id)
        inventory = get_inventory(self.user_id)

        embed = discord.Embed(color=discord.Color.blue())

        avatar_url = getattr(self.member.avatar, "url", self.member.default_avatar.url)
        embed.set_author(name=f"{self.member.display_name}'s Balance", icon_url=avatar_url)

        if self.current_mode == "wallet":
            embed.title = "💰 Wallet Balance"
            embed.description = f"**{balance:,} coins**"
            loan_data = get_loan(self.user_id)
            if loan_data and not loan_data["repaid"]:
                due_date = datetime.fromtimestamp(loan_data["due_date"])
                embed.add_field(
                    name="⚠️ Active Loan",
                    value=f"{loan_data['amount']:,} coins (due {due_date.strftime('%Y-%m-%d')})",
                    inline=False
                )
        elif self.current_mode == "bank":
            plan = bank_data['plan']
            plan_name = BANK_PLANS[plan]['name'] if plan else 'No plan'
            interest = BANK_PLANS[plan]['interest'] * 100 if plan else 0
            embed.title = "🏦 Bank Balance"
            embed.description = (
                f"**{bank_data['deposited']:,} coins**\n"
                f"*Plan: {plan_name}*\n"
                f"*Interest: {interest}% daily*"
            )
        elif self.current_mode == "currency":
            prices = load_currency_prices()
            embed.title = "💎 Currency Holdings"
            for currency in ["BobBux", "DxBux", "Gold"]:
                value = inventory.get(currency, 0)
                embed.add_field(
                    name=currency,
                    value=f"Amount: **{value:,}**\nValue: **{value * prices[currency]:,} coins**",
                    inline=True
                )

        return embed

    @discord.ui.button(label="Wallet", style=discord.ButtonStyle.primary, custom_id="wallet", row=0)
    async def wallet_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This isn't your balance!", ephemeral=True)
        self.current_mode = "wallet"
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Bank", style=discord.ButtonStyle.secondary, custom_id="bank", row=0)
    async def bank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This isn't your balance!", ephemeral=True)
        self.current_mode = "bank"
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Currency", style=discord.ButtonStyle.secondary, custom_id="currency", row=0)
    async def currency_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This isn't your balance!", ephemeral=True)
        self.current_mode = "currency"
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


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
        bank_amount = bank_data.get(str(user_id), {}).get("deposited", 0)
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

        lb_data.append((user_id, name, amount))  # Store user_id along with name and amount

    # Sort and get top 10
    lb_data.sort(key=lambda x: x[2], reverse=True)  # Sort by amount (index 2)
    top_10 = lb_data[:10]

    # Create embed
    embed = discord.Embed(
        title=f"🏆 {type.capitalize()} Balance Leaderboard",
        color=discord.Color.gold()
    )

    for i, (_, name, amount) in enumerate(top_10, 1):
        embed.add_field(
            name=f"{i}. {name}",
            value=f"{amount:,} coins",
            inline=False
        )

    # Add current user's position if not in top 10
    current_user_id = str(ctx.author.id)
    current_pos = None
    current_amount = 0
    
    # Find the current user's position
    for i, (user_id, _, amount) in enumerate(lb_data, 1):
        if user_id == current_user_id:
            current_pos = i
            current_amount = amount
            break

    if current_pos and current_pos > 10:
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
    """Export all user data including current stock levels and event gold"""
    def safe_convert(value):
        """Convert values safely handling scientific notation and large numbers"""
        try:
            if isinstance(value, str) and 'e' in value.lower():
                return int(float(value))
            return int(value)
        except (ValueError, TypeError):
            return 0

    balances = load_balances()
    bank_data = load_bank_data()
    loans = load_loans()
    inventories = load_inventories()
    currency_prices = load_currency_prices()
    currency_stocks = load_currency_stocks()
    
    # Load event balances
    try:
        with open("event_balances.json", "r") as f:
            event_balances = json.load(f)
    except FileNotFoundError:
        event_balances = {}

    output = ["=== MARKET DATA ==="]
    for currency in ["BobBux", "DxBux", "Gold"]:
        price = safe_convert(currency_prices.get(currency, 0))
        stock = safe_convert(currency_stocks.get(currency, 0))
        output.append(f"MARKET|{currency}|{price}|{stock}")

    output.append("\n=== USER DATA ===")
    all_user_ids = set(balances.keys()) | set(bank_data.keys()) | set(loans.keys()) | set(inventories.keys()) | set(event_balances.keys())

    for user_id in all_user_ids:
        wallet = safe_convert(balances.get(user_id, 1000))
        
        b_data = bank_data.get(user_id, {"plan": None, "deposited": 0})
        plan = b_data["plan"] or "None"
        deposited = safe_convert(b_data["deposited"])

        loan_info = loans.get(user_id, {})
        has_loan = "Y" if loan_info and not loan_info.get("repaid", True) else "N"

        inv_info = inventories.get(user_id, {})
        # Ensure all standard currencies exist in inventory
        for currency in ["BobBux", "DxBux", "Gold"]:
            if currency not in inv_info:
                inv_info[currency] = 0

        event_gold = safe_convert(event_balances.get(user_id, 0))

        inv_parts = []
        # Add standard currencies first
        for currency in ["BobBux", "DxBux", "Gold"]:
            inv_parts.append(f"{currency}:{safe_convert(inv_info.get(currency, 0))}")
        
        # Add other inventory items
        inv_parts.extend(
            f"{k}:{safe_convert(v)}" 
            for k, v in inv_info.items() 
            if k not in ["BobBux", "DxBux", "Gold"]
        )

        # Add event gold to inventory string
        inv_parts.append(f"EventGold:{event_gold}")

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

    for i, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            chunk = f"=== PART {i}/{len(chunks)} ===\n{chunk}"
        await ctx.send(f"```{chunk}```")

@bot.command()
@is_admin()
async def setall(ctx, *, data: str = None):
    """Import all user data including stock-aware currencies and event gold
    Usage: 
    - Paste the data directly after the command
    - Or attach a .txt file with the data
    """
    # Check for file attachment if no text data provided
    if data is None and ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith('.txt'):
            return await ctx.send("❌ Please upload a .txt file")
        
        try:
            file_content = await attachment.read()
            data = file_content.decode('utf-8')
        except Exception as e:
            return await ctx.send(f"❌ Error reading file: {e}")
    
    # If still no data, show help
    if data is None:
        return await ctx.send("❌ Please provide data either as text or in a .txt file attachment")

    # Clean the input data
    if data.startswith('```') and data.endswith('```'):
        data = data[3:-3].strip()

    lines = data.split('\n')
    balances = {}
    bank_data = {}
    loans = {}
    inventories = {}
    event_balances = {}
    currency_prices = load_currency_prices()
    currency_stocks = load_currency_stocks()

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

        if current_section == "market" and line.startswith("MARKET|"):
            parts = line.split('|')
            if len(parts) >= 4:
                currency = parts[1]
                try:
                    currency_prices[currency] = int(parts[2])
                    currency_stocks[currency] = int(parts[3])
                except (ValueError, KeyError):
                    continue

        elif current_section == "user":
            parts = line.split('|')
            if len(parts) >= 6:
                try:
                    user_id = parts[0].strip()
                    wallet = int(float(parts[1].strip()))
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

                    inv_items = {}
                    event_gold_amount = 0

                    if inventory.lower() != "none":
                        for item_str in inventory.split(','):
                            if ':' in item_str:
                                item_name, quantity = item_str.split(':')
                                item_name = item_name.strip()
                                quantity = quantity.strip()
                                try:
                                    if item_name.lower() == "eventgold":
                                        event_gold_amount = int(quantity)
                                    else:
                                        inv_items[item_name] = int(quantity)
                                except ValueError:
                                    continue

                    # Ensure all currencies exist in inventory
                    for currency in ["BobBux", "DxBux", "Gold"]:
                        if currency not in inv_items:
                            inv_items[currency] = 0

                    inventories[user_id] = inv_items
                    event_balances[user_id] = event_gold_amount

                except (ValueError, IndexError) as e:
                    print(f"Error processing line: {line} - {e}")
                    continue

    # Save all data
    save_balances(balances)
    save_bank_data(bank_data)
    save_loans(loans)
    save_inventories(inventories)
    save_currency_prices(currency_prices)
    save_currency_stocks(currency_stocks)
    
    # Save event balances
    with open("event_balances.json", "w") as f:
        json.dump(event_balances, f, indent=4)

    # Create success embed
    embed = discord.Embed(
        title="✅ Data Import Complete",
        description="Successfully imported economy data including stocks and event gold",
        color=discord.Color.green()
    )

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

#------------------ EVENTS ------------------------


def add_event_gold(user_id, amount):
    try:
        with open("event_balances.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    user_id = str(user_id)
    data[user_id] = data.get(user_id, 0) + amount

    with open("event_balances.json", "w") as f:
        json.dump(data, f, indent=4)


class GreedGloryView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.gold_collected = 0
        self.round = 1

    @discord.ui.button(label="Go Deeper 🔽", style=discord.ButtonStyle.primary)
    async def go_deeper(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("🚫 This is not your game!", ephemeral=True)
            return

        # 25% trap chance
        if random.random() < 0.10:
            await interaction.response.edit_message(embed=discord.Embed(
                title="💀 Trapped!",
                description=f"A trap was triggered! You lost **{self.gold_collected} event gold**.",
                color=discord.Color.red()
            ), view=None)
            return

        earned = random.randint(150, 700)
        self.gold_collected += earned
        self.round += 1

        embed = discord.Embed(
            title=f"🪙 Round {self.round}",
            description=(
                f"You found **{earned} event gold!**\n"
                f"Total collected: **{self.gold_collected} event gold**\n\n"
                "Do you risk it for more, or take what you’ve got?"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Trap chance: 10% per round")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Take Gold 💸", style=discord.ButtonStyle.success)
    async def take_gold(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("🚫 This is not your game!", ephemeral=True)
            return

        add_event_gold(self.user_id, self.gold_collected)

        embed = discord.Embed(
            title="🏆 You Escaped!",
            description=f"You escaped with **{self.gold_collected} event gold!**",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)

@bot.command()
async def eventbal(ctx):
    try:
        with open("event_balances.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    user_id = str(ctx.author.id)
    event_gold = data.get(user_id, 0)

    embed = discord.Embed(
        title="🏅 Event Gold Balance",
        description=f"You currently have **{event_gold} event gold**.",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

EVENT_SHOP = {
    "Golden Sword": 10000,
    "Golden Dice": 5000,
    "Golden Price Tag": 8000
}

def add_item(user_id, item_name, quantity):
    try:
        with open("inventories.json", "r") as f:
            inventories = json.load(f)
    except FileNotFoundError:
        inventories = {}

    user_id = str(user_id)
    if user_id not in inventories:
        inventories[user_id] = {}

    inventories[user_id][item_name] = inventories[user_id].get(item_name, 0) + quantity

    with open("inventories.json", "w") as f:
        json.dump(inventories, f, indent=4)
class EventShopView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.add_item(EventShopDropdown(user_id))

class EventShopDropdown(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = [
            discord.SelectOption(label=item, description=f"{cost} event gold")
            for item, cost in EVENT_SHOP.items()
        ]
        super().__init__(placeholder="Choose an item to buy", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("🚫 This isn't your shop!", ephemeral=True)
            return

        item = self.values[0]
        cost = EVENT_SHOP[item]

        # Load event balances
        try:
            with open("event_balances.json", "r") as f:
                event_data = json.load(f)
        except FileNotFoundError:
            event_data = {}

        user_id = str(self.user_id)
        user_gold = event_data.get(user_id, 0)

        if user_gold < cost:
            await interaction.response.send_message(
                f"❌ Not enough event gold! You need {cost}, but have {user_gold}.",
                ephemeral=True
            )
            return

        # Deduct event gold and add item
        event_data[user_id] = user_gold - cost
        with open("event_balances.json", "w") as f:
            json.dump(event_data, f, indent=4)

        add_item(user_id, item, 1)

        await interaction.response.send_message(
            f"✅ You bought **{item}** for **{cost} event gold**!", ephemeral=True
        )

@bot.command()
async def eventshop(ctx):
    embed = discord.Embed(
        title="🛒 Event Shop",
        description="Spend your event gold on exclusive items!",
        color=discord.Color.orange()
    )
    for name, cost in EVENT_SHOP.items():
        embed.add_field(name=name, value=f"{cost} event gold", inline=False)

    view = EventShopView(ctx.author.id)
    await ctx.send(embed=embed, view=view)

@bot.command()
async def event(ctx):
    embed = discord.Embed(
        title="💰 Greed or Glory!",
        description=(
            "You enter the Vault of Midas...\n"
            "Each step earns more event gold, but one trap and it's all gone.\n\n"
            "Choose: Go deeper for more riches, or escape with what you have."
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="Trap chance: 10% per round")
    view = GreedGloryView(user_id=ctx.author.id)
    await ctx.send(embed=embed, view=view)


#------------------BACKGROUND TASKS------------------------

def restock_all_currencies(amount=100, max_stock=10000):
    stocks = load_currency_stocks()
    for currency in stocks:
        stocks[currency] = min(stocks[currency] + amount, max_stock)
    save_currency_stocks(stocks)
    print("[StockMarket] Stock increased by", amount)

@tasks.loop(minutes=10)
async def stock_restock_task():
    restock_all_currencies()
@tasks.loop(minutes=5)
async def process_midas_touch():
    inventories = load_inventories()
    currency_prices = load_currency_prices()
    
    for user_id, inv in inventories.items():
        if inv.get("midas_touch", 0) > 0:  # Check if user has the item
            balance = get_balance(int(user_id))
            if balance >= 100:
                # Deduct coins and add gold
                set_balance(int(user_id), balance - 100)
                inv["Gold"] = inv.get("Gold", 0) + 100
                
                # Track conversions in the inventory
                inv["midas_converted"] = inv.get("midas_converted", 0) + 100
                
    save_inventories(inventories)

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    restock_all_currencies()  # Instant restock on startup
    if not stock_restock_task.is_running():
        stock_restock_task.start()
    if not process_midas_touch.is_running():
        process_midas_touch.start()

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
