import discord
from discord.ext import commands
import random

# Assuming your bot & balance functions are defined as before

class CoinFlipView(discord.ui.View):
    def __init__(self, user_id: int, bet_amount: int):
        super().__init__(timeout=30)  # buttons timeout after 30 seconds
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

        await self.disable_all_items()
        await interaction.message.edit(view=self)

        await interaction.response.send_message(
            f"{interaction.user.mention} {outcome} Your new balance is **{new_balance} coins**."
        )

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your coin flip!", ephemeral=True)
        await self.update_balance_and_send_result(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary)
    async def tails_button(self, button: discord.ui.Button, interaction: discord.Interaction):
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
