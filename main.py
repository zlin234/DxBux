import os
import time
import discord
from discord.ext import commands
import random
import json
from threading import Thread
from flask import Flask
import re

# ------------------ BALANCE MANAGEMENT ------------------

BALANCE_FILE = "balances.json"
BANK_FILE = "bank_data.json"

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

# Bank plans with interest rates and minimum balances
BANK_PLANS = {
    "basic": {
        "name": "Basic",
        "min_deposit": 0,
        "interest": 0.01,  # 1% daily interest
        "description": "1% daily interest, no minimum balance"
    },
    "premium": {
        "name": "Premium",
        "min_deposit": 5000,
        "interest": 0.03,  # 3% daily interest
        "description": "3% daily interest, requires 5,000 coin minimum"
    },
    "vip": {
        "name": "VIP",
        "min_deposit": 15000,
        "interest": 0.05,  # 5% daily interest
        "description": "5% daily interest, requires 15,000 coin minimum"
    }
}

# ------------------ DISCORD BOT SETUP ------------------

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="-", intents=intents)

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
    """Claim your daily interest from the bank"""
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    
    if bank_data["plan"] is None:
        return await ctx.send("❌ You don't have a bank plan. Use `-bank` to get started.")
    
    if bank_data["deposited"] == 0:
        return await ctx.send("❌ You don't have any coins deposited to earn interest.")
    
    current_time = time.time()
    last_claim = bank_data["last_interest_claim"]
    
    # Calculate how many days have passed (minimum 1)
    days_passed = max(1, int((current_time - last_claim) / 86400))  # 86400 seconds = 1 day
    
    # Calculate interest for each day (compounding)
    interest_rate = BANK_PLANS[bank_data["plan"]]["interest"]
    principal = bank_data["deposited"]
    total_interest = 0
    
    for _ in range(days_passed):
        daily_interest = principal * interest_rate
        total_interest += daily_interest
        principal += daily_interest
    
    # Add to pending interest
    bank_data["pending_interest"] += total_interest
    bank_data["last_interest_claim"] = current_time
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"⏳ You've accumulated **{int(total_interest)} coins** in interest over {days_passed} day(s).\n"
        f"Use `-claim` to add it to your bank balance!"
    )

# Add this new command to claim the interest
@bot.command()
async def claim(ctx):
    """Claim your accumulated interest"""
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    
    if bank_data["pending_interest"] <= 0:
        return await ctx.send("❌ You don't have any pending interest to claim.")
    
    interest_to_add = bank_data["pending_interest"]
    bank_data["deposited"] += interest_to_add
    bank_data["pending_interest"] = 0
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"💰 Successfully claimed **{int(interest_to_add)} coins** in interest!\n"
        f"Your new bank balance is **{bank_data['deposited']} coins**."
    )

@bot.command()
async def bank(ctx):
    """View or change your bank plan"""
    user_id = ctx.author.id
    bank_data = get_bank_data(user_id)
    
    if bank_data["plan"] is None:
        view = BankPlanView(user_id)
        await ctx.send(
            f"{ctx.author.mention}, you currently have no bank plan. Select one below:",
            view=view
        )
    else:
        current_plan = BANK_PLANS[bank_data["plan"]]
        message = (
            f"{ctx.author.mention}, your current bank plan is **{current_plan['name']}**.\n"
            f"• {current_plan['description']}\n"
            f"• Deposited: {bank_data['deposited']} coins\n"
        )
        
        if bank_data["pending_interest"] > 0:
            message += f"• Pending interest: 🎁 {int(bank_data['pending_interest'])} coins (use `-claim`)\n"
        
        # Calculate time until next interest
        if bank_data["last_interest_claim"] > 0:
            next_interest = bank_data["last_interest_claim"] + 86400 - time.time()
            if next_interest > 0:
                hours = int(next_interest // 3600)
                minutes = int((next_interest % 3600) // 60)
                message += f"• Next interest in: ⏳ {hours}h {minutes}m\n"
            else:
                message += "• Interest available now! (use `-interest`)\n"
        
        message += "\nTo change your plan, use `-bank` again."
        await ctx.send(message)

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
    
    await ctx.send(
        f"**{member.display_name}'s balances:**\n"
        f"• Wallet: 💰 **{balance} coins**\n"
        f"• Bank: 🏦 **{bank_data['deposited']} coins** ({plan_name})"
    )

# ------------------ ADMIN CHECK DECORATOR ------------------

def is_admin():
    async def predicate(ctx):
        admin_role = discord.utils.get(ctx.guild.roles, name="carrot")
        if admin_role in ctx.author.roles:
            return True
        await ctx.send("❌ You need the Admin role to use this command.")
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
    """Export all user balances and bank data"""
    balances = load_balances()
    bank_data = load_bank_data()
    
    output = []
    # Combine user IDs from both files
    all_user_ids = set(balances.keys()) | set(bank_data.keys())
    
    for user_id in all_user_ids:
        wallet = balances.get(user_id, 1000)  # Default to 1000 if not found
        b_data = bank_data.get(user_id, {"plan": None, "deposited": 0})
        plan = b_data["plan"] or "None"
        deposited = b_data["deposited"]
        # Use pipe (|) as delimiter instead of colon
        output.append(f"{user_id}|{wallet}|{plan}|{deposited}")
    
    data = "\n".join(output)
    # Use a code block with specific language to prevent formatting issues
    await ctx.send(f"```data\n{data}```")

@bot.command()
@is_admin()
async def setall(ctx, *, data: str):
    """Import all user balances and bank data"""
    # Remove code block markers if present
    if data.startswith('```') and data.endswith('```'):
        data = data[3:-3].strip()
        # Remove optional language specifier
        if data.startswith('data\n'):
            data = data[5:]
    
    lines = data.split('\n')
    balances = {}
    bank_data = {}
    
    for line in lines:
        if not line.strip():
            continue
            
        # Split using pipe delimiter
        parts = line.split('|')
        if len(parts) != 4:
            continue
            
        try:
            user_id = parts[0].strip()
            wallet = int(parts[1].strip())
            plan = parts[2].strip()
            deposited = int(parts[3].strip())
            
            # Add to balances
            balances[user_id] = wallet
            
            # Add to bank data
            bank_data[user_id] = {
                "plan": None if plan.lower() == "none" else plan,
                "deposited": deposited
            }
        except ValueError:
            continue
    
    # Save the data
    save_balances(balances)
    save_bank_data(bank_data)
    
    await ctx.send(f"✅ Successfully imported data for {len(balances)} users!")

# ------------------ GAME STUBS ------------------

@bot.command()
async def bj(ctx, amount: int):
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")
    # TODO: Implement blackjack logic here
    await ctx.send(f"Blackjack is not implemented yet, but you tried to bet {amount} coins!")

@bot.command()
async def minesweeper(ctx, amount: int):
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")
    # TODO: Implement minesweeper logic here
    await ctx.send(f"Minesweeper is not implemented yet, but you tried to bet {amount} coins!")

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
