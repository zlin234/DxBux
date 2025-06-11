import os
import time
import discord
from discord.ext import commands
import random
import json
from threading import Thread
from flask import Flask

# ------------------ FILE PATHS ------------------
BALANCE_FILE = "balances.json"
BANK_FILE = "bank_data.json"
LOAN_FILE = "loans.json"

# ------------------ CONSTANTS ------------------
MAX_LOAN_AMOUNT = 10000
LOAN_INTEREST_RATE = 0.1  # 10%
LOAN_TERM_DAYS = 7  # Must repay within 7 days

BANK_PLANS = {
    "basic": {
        "name": "Basic",
        "min_deposit": 0,
        "interest": 0.01,
        "description": "1% daily interest, no minimum balance"
    },
    "premium": {
        "name": "Premium",
        "min_deposit": 5000,
        "interest": 0.03,
        "description": "3% daily interest, requires 5,000 coin minimum"
    },
    "vip": {
        "name": "VIP",
        "min_deposit": 15000,
        "interest": 0.05,
        "description": "5% daily interest, requires 15,000 coin minimum"
    }
}

# ------------------ BALANCE MANAGEMENT ------------------
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

# ------------------ LOAN MANAGEMENT ------------------
def load_loans():
    try:
        with open(LOAN_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_loans(loans):
    with open(LOAN_FILE, "w") as f:
        json.dump(loans, f)

def get_loan_data(user_id):
    loans = load_loans()
    if str(user_id) not in loans:
        loans[str(user_id)] = {
            "amount": 0,
            "interest": 0,
            "taken_at": 0,
            "repaid": 0
        }
        save_loans(loans)
    return loans[str(user_id)]

def update_loan_data(user_id, data):
    loans = load_loans()
    loans[str(user_id)] = data
    save_loans(loans)

# ------------------ DISCORD BOT SETUP ------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="-", intents=intents)

# ------------------ BANK VIEW CLASSES ------------------
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
            f"{interaction.user.mention} You've selected the Basic bank plan! {BANK_PLANS['basic']['description']}"
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
            f"{interaction.user.mention} You've selected the Premium bank plan! {BANK_PLANS['premium']['description']}"
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
            f"{interaction.user.mention} You've selected the VIP bank plan! {BANK_PLANS['vip']['description']}"
        )

# ------------------ BANK COMMANDS ------------------
@bot.command()
async def deposit(ctx, amount: int):
    """Deposit coins into your bank account"""
    user_id = ctx.author.id
    wallet_balance = get_balance(user_id)
    bank_data = get_bank_data(user_id)
    
    if bank_data["plan"] is None:
        return await ctx.send("❌ You don't have a bank plan. Use `-bank` to select one first.")
    
    if amount <= 0:
        return await ctx.send("❌ Deposit amount must be positive.")
    if amount > wallet_balance:
        return await ctx.send("❌ You don't have that much in your wallet.")
    
    plan = BANK_PLANS[bank_data["plan"]]
    new_deposited = bank_data["deposited"] + amount
    
    if bank_data["deposited"] == 0 and new_deposited < plan["min_deposit"]:
        return await ctx.send(
            f"❌ Your {plan['name']} plan requires a minimum deposit of {plan['min_deposit']} coins.\n"
            f"Either deposit at least {plan['min_deposit']} coins or switch to a different plan with `-bank`."
        )
    
    set_balance(user_id, wallet_balance - amount)
    bank_data["deposited"] = new_deposited
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"✅ Successfully deposited {amount} coins into your bank account!\n"
        f"• New wallet balance: {wallet_balance - amount} coins\n"
        f"• Bank balance: {new_deposited} coins\n"
        f"• Plan: {plan['name']} ({plan['interest']*100}% daily interest)"
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
    
    plan = BANK_PLANS[bank_data["plan"]]
    if (bank_data["deposited"] - amount) < plan["min_deposit"]:
        return await ctx.send(
            f"❌ You must maintain at least {plan['min_deposit']} coins deposited for your plan.\n"
            "Consider switching to a different plan with `-bank` or withdrawing less."
        )
    
    current_balance = get_balance(user_id)
    set_balance(user_id, current_balance + amount)
    bank_data["deposited"] -= amount
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"✅ Successfully withdrew {amount} coins from your bank account.\n"
        f"• New wallet balance: {current_balance + amount} coins\n"
        f"• Bank balance: {bank_data['deposited']} coins"
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
    days_passed = max(1, int((current_time - last_claim) / 86400))
    
    interest_rate = BANK_PLANS[bank_data["plan"]]["interest"]
    principal = bank_data["deposited"]
    total_interest = 0
    
    for _ in range(days_passed):
        daily_interest = principal * interest_rate
        total_interest += daily_interest
        principal += daily_interest
    
    bank_data["pending_interest"] += total_interest
    bank_data["last_interest_claim"] = current_time
    update_bank_data(user_id, bank_data)
    
    await ctx.send(
        f"⏳ You've accumulated {int(total_interest)} coins in interest over {days_passed} day(s).\n"
        f"Use `-claim` to add it to your bank balance!"
    )

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
        f"💰 Successfully claimed {int(interest_to_add)} coins in interest!\n"
        f"Your new bank balance is {bank_data['deposited']} coins."
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
            f"{ctx.author.mention}, your current bank plan is {current_plan['name']}.\n"
            f"• {current_plan['description']}\n"
            f"• Deposited: {bank_data['deposited']} coins\n"
        )
        
        if bank_data["pending_interest"] > 0:
            message += f"• Pending interest: 🎁 {int(bank_data['pending_interest'])} coins (use `-claim`)\n"
        
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

# ------------------ LOAN COMMANDS ------------------
@bot.command()
async def loan(ctx, amount: int):
    """Take out a loan from the bank"""
    user_id = ctx.author.id
    loan_data = get_loan_data(user_id)
    current_balance = get_balance(user_id)
    
    if loan_data["amount"] > 0 and loan_data["repaid"] < loan_data["amount"] + loan_data["interest"]:
        owed = (loan_data["amount"] + loan_data["interest"]) - loan_data["repaid"]
        return await ctx.send(
            f"❌ You already have an outstanding loan of {owed} coins!\n"
            f"Use `-repay` to pay it back first."
        )
    
    if amount <= 0:
        return await ctx.send("❌ Loan amount must be positive.")
    if amount > MAX_LOAN_AMOUNT:
        return await ctx.send(f"❌ Maximum loan amount is {MAX_LOAN_AMOUNT} coins.")
    
    interest = int(amount * LOAN_INTEREST_RATE)
    total_to_repay = amount + interest
    
    loan_data["amount"] = amount
    loan_data["interest"] = interest
    loan_data["taken_at"] = time.time()
    loan_data["repaid"] = 0
    update_loan_data(user_id, loan_data)
    
    set_balance(user_id, current_balance + amount)
    
    await ctx.send(
        f"✅ You've taken out a loan of {amount} coins!\n"
        f"• Interest: {interest} coins (10%)\n"
        f"• Total to repay: {total_to_repay} coins\n"
        f"• Due within: {LOAN_TERM_DAYS} days\n\n"
        f"Use `-repay <amount>` to pay back your loan."
    )

@bot.command()
async def repay(ctx, amount: int):
    """Repay your loan"""
    user_id = ctx.author.id
    loan_data = get_loan_data(user_id)
    current_balance = get_balance(user_id)
    
    if loan_data["amount"] == 0 or loan_data["repaid"] >= loan_data["amount"] + loan_data["interest"]:
        return await ctx.send("❌ You don't have any active loans.")
    
    if amount <= 0:
        return await ctx.send("❌ Repayment amount must be positive.")
    if amount > current_balance:
        return await ctx.send("❌ You don't have enough coins to make this payment.")
    
    total_owed = (loan_data["amount"] + loan_data["interest"]) - loan_data["repaid"]
    
    if amount > total_owed:
        return await ctx.send(f"❌ You only owe {total_owed} coins.")
    
    set_balance(user_id, current_balance - amount)
    loan_data["repaid"] += amount
    update_loan_data(user_id, loan_data)
    
    remaining = (loan_data["amount"] + loan_data["interest"]) - loan_data["repaid"]
    
    if remaining <= 0:
        message = "🎉 Congratulations! You've fully repaid your loan!"
        loan_data["amount"] = 0
        loan_data["interest"] = 0
        loan_data["taken_at"] = 0
        loan_data["repaid"] = 0
        update_loan_data(user_id, loan_data)
    else:
        message = f"Remaining balance: {remaining} coins"
    
    await ctx.send(
        f"✅ Successfully repaid {amount} coins!\n"
        f"{message}"
    )

@bot.command(aliases=["loaninfo"])
async def myloan(ctx):
    """Check your current loan status"""
    user_id = ctx.author.id
    loan_data = get_loan_data(user_id)
    
    if loan_data["amount"] == 0 or loan_data["repaid"] >= loan_data["amount"] + loan_data["interest"]:
        return await ctx.send("You don't have any active loans.")
    
    total_owed = loan_data["amount"] + loan_data["interest"]
    repaid = loan_data["repaid"]
    remaining = total_owed - repaid
    
    taken_at = loan_data["taken_at"]
    due_date = taken_at + (LOAN_TERM_DAYS * 86400)
    time_left = due_date - time.time()
    
    if time_left <= 0:
        time_msg = "⚠️ PAST DUE!"
    else:
        hours = int(time_left // 3600)
        minutes = int((time_left % 3600) // 60)
        time_msg = f"Due in: {hours}h {minutes}m"
    
    await ctx.send(
        f"**{ctx.author.display_name}'s Loan Status**\n"
        f"• Original amount: {loan_data['amount']} coins\n"
        f"• Interest: {loan_data['interest']} coins (10%)\n"
        f"• Total repaid: {repaid} coins\n"
        f"• Remaining: {remaining} coins\n"
        f"• {time_msg}\n\n"
        f"Use `-repay <amount>` to make a payment."
    )

# ------------------ ADMIN COMMANDS ------------------
def is_admin():
    async def predicate(ctx):
        admin_role = discord.utils.get(ctx.guild.roles, name="carrot")
        if admin_role in ctx.author.roles:
            return True
        await ctx.send("❌ You need the Admin role to use this command.")
        return False
    return commands.check(predicate)

@bot.command(aliases=["setbalance", "setbal"])
@is_admin()
async def admin_setbal(ctx, member: discord.Member, amount: int):
    if amount < 0:
        return await ctx.send("❌ Balance cannot be negative.")
    set_balance(member.id, amount)
    await ctx.send(f"✅ Set {member.display_name}'s wallet balance to {amount} coins.")

@bot.command()
@is_admin()
async def checkall(ctx):
    """Export all user balances and bank data"""
    balances = load_balances()
    bank_data = load_bank_data()
    loans = load_loans()
    
    output = []
    all_user_ids = set(balances.keys()) | set(bank_data.keys()) | set(loans.keys())
    
    for user_id in all_user_ids:
        wallet = balances.get(user_id, 1000)
        b_data = bank_data.get(user_id, {"plan": None, "deposited": 0})
        plan = b_data["plan"] or "None"
        deposited = b_data["deposited"]
        l_data = loans.get(user_id, {"amount": 0, "repaid": 0})
        output.append(f"{user_id}|{wallet}|{plan}|{deposited}|{l_data['amount']}|{l_data['repaid']}")
    
    data = "\n".join(output)
    await ctx.send(f"```data\n{data}```")

@bot.command()
@is_admin()
async def setall(ctx, *, data: str):
    """Import all user balances and bank data"""
    if data.startswith('```') and data.endswith('```'):
        data = data[3:-3].strip()
        if data.startswith('data\n'):
            data = data[5:]
    
    lines = data.split('\n')
    balances = {}
    bank_data = {}
    loans = {}
    
    for line in lines:
        if not line.strip():
            continue
            
        parts = line.split('|')
        if len(parts) != 6:
            continue
            
        try:
            user_id = parts[0].strip()
            wallet = int(parts[1].strip())
            plan = parts[2].strip()
            deposited = int(parts[3].strip())
            loan_amount = int(parts[4].strip())
            loan_repaid = int(parts[5].strip())
            
            balances[user_id] = wallet
            
            bank_data[user_id] = {
                "plan": None if plan.lower() == "none" else plan,
                "deposited": deposited
            }
            
            loans[user_id] = {
                "amount": loan_amount,
                "repaid": loan_repaid
            }
        except ValueError:
            continue
    
    save_balances(balances)
    save_bank_data(bank_data)
    save_loans(loans)
    
    await ctx.send(f"✅ Successfully imported data for {len(balances)} users!")

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
