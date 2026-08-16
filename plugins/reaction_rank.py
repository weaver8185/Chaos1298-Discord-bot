import discord
from discord.ext import commands
import json
import os

CONFIG_FILE = 'reaction_rank_config.json'
STATS_FILE = 'reaction_rank_stats.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "enabled": True,
        "games": []
    }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_stats(stats):
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

async def setup(bot):
    config = load_config()
    
    if not config.get('enabled'):
        print("Reaction rank plugin disabled", flush=True)
        return
    
    print(f"Reaction rank plugin loaded with {len(config.get('games', []))} games", flush=True)
    
    @bot.event
    async def on_reaction_add(reaction, user):
        if user.bot or not config.get('enabled'):
            return
        
        # Find which game this notification channel belongs to
        game = None
        for g in config.get('games', []):
            if g.get('notification_channel_id') == reaction.message.channel.id:
                if str(reaction.emoji) == g.get('emoji'):
                    game = g
                    break
        
        if not game:
            return
        
        stats = load_stats()
        user_id = str(user.id)
        game_name = game.get('name')
        
        if user_id not in stats:
            stats[user_id] = {}
        
        if game_name not in stats[user_id]:
            stats[user_id][game_name] = {'reactions': 0, 'has_role': False}
        
        stats[user_id][game_name]['reactions'] += 1
        reactions = stats[user_id][game_name]['reactions']
        reactions_needed = game.get('reactions_needed', 1)
        
        # Check if user qualifies for the rank
        if reactions >= reactions_needed and not stats[user_id][game_name]['has_role']:
            role_id = game.get('role_id')
            if role_id and role_id != 0:
                try:
                    guild = reaction.message.guild
                    member = await guild.fetch_member(user.id)
                    role = guild.get_role(role_id)
                    if role and role not in member.roles:
                        await member.add_roles(role)
                        stats[user_id][game_name]['has_role'] = True
                        print(f"✓ Gave {user} {game_name} rank ({reactions} reactions)", flush=True)
                except Exception as e:
                    print(f"Error assigning role: {e}", flush=True)
        
        save_stats(stats)
    
    @bot.event
    async def on_reaction_remove(reaction, user):
        if user.bot or not config.get('enabled'):
            return
        
        # Find which game this notification channel belongs to
        game = None
        for g in config.get('games', []):
            if g.get('notification_channel_id') == reaction.message.channel.id:
                if str(reaction.emoji) == g.get('emoji'):
                    game = g
                    break
        
        if not game:
            return
        
        stats = load_stats()
        user_id = str(user.id)
        game_name = game.get('name')
        
        if user_id not in stats or game_name not in stats[user_id]:
            return
        
        stats[user_id][game_name]['reactions'] -= 1
        if stats[user_id][game_name]['reactions'] < 0:
            stats[user_id][game_name]['reactions'] = 0
        
        reactions = stats[user_id][game_name]['reactions']
        reactions_needed = game.get('reactions_needed', 1)
        
        # Remove role if reactions fall below threshold
        if reactions < reactions_needed and stats[user_id][game_name]['has_role']:
            role_id = game.get('role_id')
            if role_id and role_id != 0:
                try:
                    guild = reaction.message.guild
                    member = await guild.fetch_member(user.id)
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        await member.remove_roles(role)
                        stats[user_id][game_name]['has_role'] = False
                        print(f"✗ Removed {user} {game_name} rank ({reactions} reactions)", flush=True)
                except Exception as e:
                    print(f"Error removing role: {e}", flush=True)
        
        save_stats(stats)
    
    @bot.tree.command(name='create-rank-widget')
    async def create_widget(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admin only!", ephemeral=True)
            return
        
        config = load_config()
        games = config.get('games', [])
        
        if not games:
            await interaction.response.send_message("❌ No games configured!", ephemeral=True)
            return
        
        # Create embed
        embed = discord.Embed(
            title="🎮 Rank Access",
            description="React to get access to game channels:",
            color=discord.Color.blue()
        )
        
        for game in games:
            embed.add_field(
                name=f"{game.get('emoji')} {game.get('name')}",
                value="Click to get access",
                inline=True
            )
        
        # Send message
        msg = await interaction.channel.send(embed=embed)
        
        # Add reactions
        for game in games:
            try:
                await msg.add_reaction(game.get('emoji'))
            except Exception as e:
                print(f"Error adding reaction: {e}", flush=True)
        
        await interaction.response.send_message(f"✓ Widget created! Message ID: {msg.id}", ephemeral=True)
    
    @bot.tree.command(name='massrank')
    @discord.app_commands.describe(game="Game name", role="Role to give")
    async def mass_rank(interaction: discord.Interaction, game: str, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admin only!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        config = load_config()
        game_config = None
        for g in config.get('games', []):
            if g.get('name').lower() == game.lower():
                game_config = g
                break
        
        if not game_config:
            await interaction.followup.send(f"❌ Game '{game}' not found in config!", ephemeral=True)
            return
        
        stats = load_stats()
        count = 0
        
        # Give rank to all members with the role
        async for member in interaction.guild.fetch_members():
            if role in member.roles:
                user_id = str(member.id)
                if user_id not in stats:
                    stats[user_id] = {}
                
                stats[user_id][game] = {
                    'reactions': game_config.get('reactions_needed', 1),
                    'has_role': True
                }
                count += 1
        
        save_stats(stats)
        await interaction.followup.send(f"✓ Gave {game} rank to {count} members!", ephemeral=True)
    
    @bot.tree.command(name='myrank')
    @discord.app_commands.describe(game="Game name (optional)")
    async def my_rank(interaction: discord.Interaction, game: str = None):
        stats = load_stats()
        user_id = str(interaction.user.id)
        
        if user_id not in stats:
            await interaction.response.send_message("You have no ranks yet!", ephemeral=True)
            return
        
        user_stats = stats[user_id]
        
        embed = discord.Embed(title="Your Ranks", color=discord.Color.blue())
        
        if game:
            # Show specific game rank
            if game not in user_stats:
                await interaction.response.send_message(f"You have no {game} rank!", ephemeral=True)
                return
            
            game_stats = user_stats[game]
            embed.title = f"{game} Rank"
            embed.add_field(name="Reactions", value=str(game_stats['reactions']))
            embed.add_field(name="Status", value="✓ Ranked" if game_stats['has_role'] else "Unranked")
        else:
            # Show all ranks
            for game_name, game_stats in user_stats.items():
                status = "✓" if game_stats['has_role'] else "✗"
                embed.add_field(
                    name=f"{status} {game_name}",
                    value=f"{game_stats['reactions']} reaction(s)",
                    inline=True
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name='leaderboard')
    @discord.app_commands.describe(game="Game name")
    async def leaderboard(interaction: discord.Interaction, game: str):
        stats = load_stats()
        
        # Get top 10 for this game
        game_ranks = []
        for user_id, user_games in stats.items():
            if game in user_games:
                game_ranks.append((user_id, user_games[game]['reactions']))
        
        if not game_ranks:
            await interaction.response.send_message(f"No {game} ranks yet!", ephemeral=True)
            return
        
        game_ranks.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(title=f"{game} Leaderboard", color=discord.Color.gold())
        
        text = ""
        for i, (user_id, reactions) in enumerate(game_ranks[:10], 1):
            text += f"{i}. <@{user_id}> - {reactions} reaction(s)\n"
        
        embed.description = text or "No data"
        await interaction.response.send_message(embed=embed)

