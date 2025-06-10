import os
import discord
from discord.ext import commands, tasks
import random
import json
from threading import Thread
from flask import Flask

# ------------------ BALANCE MANAGEMENT ------------------

BALANCE_FILE = "balances.json"

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

def add_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = balances.get(str(user_id), 1000) + amount
    save_balances(balances)

# ------------------ DISCORD BOT SETUP ------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="-", intents=intents)

# ------------------ COIN FLIP VIEW ------------------

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
            await interaction.response.send_message("You don't have enough balance!", ephemeral=True)
            await self.disable_all_items()
            await interaction.message.edit(view=self)
            return

        result = random.choice(["heads", "tails"])
        won = result == user_choice

        new_balance = current_balance + self.bet_amount if won else current_balance - self.bet_amount
        set_balance(self.user_id, new_balance)
        outcome = f"🎉 It was **{result.capitalize()}**! You **won** {self.bet_amount} coins!" if won else f"😢 It was **{result.capitalize()}**. You **lost** {self.bet_amount} coins."

        self.has_responded = True
        await self.disable_all_items()
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            f"{interaction.user.mention} {outcome} Your new balance is **{new_balance} coins**."
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
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if get_balance(user_id) < amount:
        return await ctx.send("❌ Not enough balance.")

    view = CoinFlipView(user_id, amount)
    await ctx.send(f"{ctx.author.mention}, choose Heads or Tails to bet **{amount}** coins!", view=view)

# ------------------ BALANCE CHECK ------------------

@bot.command(aliases=["setbalance"])
@is_admin()
async def setbal(ctx, member: discord.Member = None, amount: int = None):
    if member and amount is not None:
        set_balance(member.id, amount)
        await ctx.send(f"✅ Set {member.display_name}'s balance to **{amount} coins**.")
    elif member is None and amount is not None:
        balances = load_balances()
        for uid in balances:
            balances[uid] = balances.get(uid, 1000) + amount
        save_balances(balances)
        await ctx.send(f"✅ Added **{amount} coins** to all known users.")
    else:
        await ctx.send("❌ Usage: `-setbal @user amount` or `-setbal amount` to add to all.")

# ------------------ ADMIN SETBAL ------------------

def is_admin():
    async def predicate(ctx):
        return discord.utils.get(ctx.author.roles, name="Admin") is not None
    return commands.check(predicate)

@bot.command(aliases=["setbalance"])
@is_admin()
async def setbal(ctx, amount: int, member: discord.Member = None):
    if member:
        set_balance(member.id, amount)
        await ctx.send(f"✅ Set {member.display_name}'s balance to {amount} coins.")
    else:
        balances = load_balances()
        for uid in balances:
            balances[uid] = balances.get(uid, 1000) + amount
        save_balances(balances)
        await ctx.send(f"✅ Added {amount} coins to all known users' balances.")

# ------------------ BLACKJACK STUB ------------------

@bot.command()
async def bj(ctx, amount: int):
    user_id = ctx.author.id
    if amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if get_balance(user_id) < amount:
        return await ctx.send("❌ Not enough balance.")
    # Future: Add Blackjack NPC logic
    await ctx.send(f"🃏 Blackjack vs NPC coming soon! You tried to bet {amount} coins.")

# ------------------ MINESWEEPER STUB ------------------

@bot.command()
async def minesweeper(ctx, amount: int):
    user_id = ctx.author.id
    if amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if get_balance(user_id) < amount:
        return await ctx.send("❌ Not enough balance.")
    await ctx.send(f"💣 Minesweeper coming soon! You tried to bet {amount} coins.")

# ------------------ DAILY ALLOWANCE ------------------

@tasks.loop(hours=24)
async def daily_allowance():
    print("Giving daily allowance...")
    balances = load_balances()
    for uid in balances:
        balances[uid] += 100
    save_balances(balances)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    daily_allowance.start()

# ------------------ KEEP ALIVE ------------------

app = Flask("")

@app.route("/")
def home():
    return "I'm alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ------------------ RUN ------------------

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
