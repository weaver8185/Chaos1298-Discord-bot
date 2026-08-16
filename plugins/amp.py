import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import json
import os
from datetime import datetime
import subprocess

class AmpStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_config()
        self.load_servers()
        self.status_message_id = None
        self.load_message_id()
        self.session_id = None
        self.instance_sessions = {}  # instance_id -> session_id
        
        if self.status_channel_id and self.servers and self.amp_password:
            self.status_loop.start()

    def cog_unload(self):
        self.status_loop.cancel()

    def load_config(self):
        try:
            with open('configs/private.keys', 'r') as f:
                secrets = json.load(f)
            self.amp_url = secrets.get('amp_url', '').rstrip('/')
            self.amp_user = secrets.get('amp_user', '')
            self.amp_password = secrets.get('amp_password', '')
            self.status_channel_id = secrets.get('amp_status_channel_id', 0)
        except Exception as e:
            print(f"[AMP] Config error: {e}")

    def load_servers(self):
        try:
            with open('configs/amp_servers.json', 'r') as f:
                data = json.load(f)
                self.servers = {s['id']: s for s in data.get('servers', [])}
                print(f"[AMP] Loaded {len(self.servers)} servers")
        except Exception as e:
            print(f"[AMP] Servers error: {e}")
            self.servers = {}

    def load_message_id(self):
        if os.path.exists('configs/amp_message_id.json'):
            try:
                with open('configs/amp_message_id.json', 'r') as f:
                    data = json.load(f)
                    self.status_message_id = data.get('message_id')
            except:
                pass

    def save_message_id(self):
        if self.status_message_id:
            with open('configs/amp_message_id.json', 'w') as f:
                json.dump({'message_id': self.status_message_id}, f)

    def check_if_updating(self, server_name):
        try:
            result = subprocess.run(
                ['pgrep', '-f', f'steamcmd.*{server_name}'],
                capture_output=True, timeout=2
            )
            return result.returncode == 0
        except:
            return False

    async def amp_login(self, session):
        try:
            url = f"{self.amp_url}/API/Core/Login"
            headers = {"Accept": "application/vnd.cubecoders-ampapi+json", "Content-Type": "application/json"}
            payload = {"username": self.amp_user, "password": self.amp_password, "token": "", "rememberMe": False}
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get('success'):
                    self.session_id = data.get('sessionID')
                    print("[AMP] Login OK")
                    return True
                return False
        except Exception as e:
            print(f"[AMP] Login error: {e}")
            return False

    async def login_to_instance_proxy(self, session, instance_id):
        """Login via controller proxy to get a per-instance session"""
        try:
            url = f"{self.amp_url}/API/ADSModule/Servers/{instance_id}/API/Core/Login"
            headers = {"Accept": "application/vnd.cubecoders-ampapi+json", "Content-Type": "application/json"}
            payload = {
                "username": self.amp_user,
                "password": self.amp_password,
                "token": "",
                "rememberMe": False,
                "SESSIONID": self.session_id
            }
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get('success'):
                    return data.get('sessionID')
        except Exception as e:
            print(f"[AMP] Proxy login error for {instance_id}: {e}")
        return None

    async def get_instance_status_proxy(self, session, instance_id, inst_session):
        """Get live status via proxy using instance session"""
        try:
            url = f"{self.amp_url}/API/ADSModule/Servers/{instance_id}/API/Core/GetStatus"
            headers = {"Accept": "application/vnd.cubecoders-ampapi+json", "Content-Type": "application/json"}
            payload = {"SESSIONID": inst_session}
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return await resp.json()
        except Exception as e:
            print(f"[AMP] GetStatus proxy error: {e}")
        return None

    async def get_instances(self, session):
        try:
            url = f"{self.amp_url}/API/ADSModule/GetInstances"
            headers = {"Accept": "application/vnd.cubecoders-ampapi+json", "Content-Type": "application/json"}
            payload = {"SESSIONID": self.session_id, "ForceIncludeSelf": True}
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if isinstance(data, dict) and data.get('success'):
                    result = data.get('result', [])
                    return result if isinstance(result, list) else []
                elif isinstance(data, list):
                    return data
                return []
        except Exception as e:
            print(f"[AMP] GetInstances error: {e}")
            return []

    async def fetch_live_status(self, session, instances):
        for item in instances:
            if not isinstance(item, dict) or 'AvailableInstances' not in item:
                continue

            for inst in item.get('AvailableInstances', []):
                fname = inst.get('FriendlyName', '')
                app_state = inst.get('AppState', -1)
                instance_id = inst.get('InstanceID', '')

                if app_state == -1 or fname not in self.servers or not instance_id:
                    continue

                self.servers[fname]['app_state'] = app_state

                if app_state != 20:
                    self.servers[fname]['players'] = '0'
                    continue

                # Get or create instance session
                inst_session = self.instance_sessions.get(instance_id)
                if not inst_session:
                    inst_session = await self.login_to_instance_proxy(session, instance_id)
                    if inst_session:
                        self.instance_sessions[instance_id] = inst_session
                    else:
                        print(f"[AMP] Could not get session for {fname}")
                        continue

                # Get live status
                status = await self.get_instance_status_proxy(session, instance_id, inst_session)
                if not status:
                    self.instance_sessions.pop(instance_id, None)
                    continue

                # Handle expired session
                if 'Title' in status and 'Unauthorized' in status.get('Title', ''):
                    self.instance_sessions.pop(instance_id, None)
                    inst_session = await self.login_to_instance_proxy(session, instance_id)
                    if inst_session:
                        self.instance_sessions[instance_id] = inst_session
                        status = await self.get_instance_status_proxy(session, instance_id, inst_session)

                if not status:
                    continue

                metrics = status.get('Metrics', {})
                au = metrics.get('Active Users', {})
                if isinstance(au, dict):
                    raw = au.get('RawValue', 0)
                    max_val = au.get('MaxValue', 70)
                    self.servers[fname]['players'] = str(raw)
                    self.servers[fname]['max_players'] = str(max_val)
                    print(f"[AMP] {fname}: {raw}/{max_val} players")

    def build_embed(self, instances=None):
        embed = discord.Embed(
            title="🖥️ AMP Server Status",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )

        for server_id, server in self.servers.items():
            updating = self.check_if_updating(server_id)
            app_state = server.get('app_state', -1)
            players = server.get('players', '0')
            max_players = server.get('max_players', '70')
            name = server['name']

            if updating:
                icon = "🟣"
                status_text = "Updating..."
            elif app_state == 20:
                icon = "🟢"
                status_text = f"Players: {players}/{max_players}"
            elif app_state in (10, 5):
                icon = "🟡"
                status_text = "Starting..."
            else:
                icon = "🔴"
                status_text = "Offline"

            embed.add_field(name=f"{icon} {name}", value=status_text, inline=False)

        embed.set_footer(text="Auto-updating every 60s")
        return embed

    @tasks.loop(seconds=60)
    async def status_loop(self):
        print("[AMP] Loop tick")
        print(f"[AMP] Channel ID: {self.status_channel_id}")
        try:
            channel = self.bot.get_channel(self.status_channel_id)
            print(f"[AMP] Channel: {channel}")
            if not channel:
                print("[AMP] Channel not found!")
                return

            print("[AMP] Opening session")
            import ssl
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            async with aiohttp.ClientSession(connector=connector) as session:
                print("[AMP] Session opened")
                if not self.session_id:
                    print("[AMP] Logging in")
                    if not await self.amp_login(session):
                        print("[AMP] Login failed!")
                        return
                print("[AMP] Getting instances")
                instances = await self.get_instances(session)
                print(f"[AMP] Got {len(instances)} instances")
                await self.fetch_live_status(session, instances)
                print("[AMP] Live status fetched")

            embed = self.build_embed(instances)

            if self.status_message_id:
                try:
                    msg = await channel.fetch_message(self.status_message_id)
                    await msg.edit(embed=embed)
                except:
                    msg = await channel.send(embed=embed)
                    self.status_message_id = msg.id
                    self.save_message_id()
            else:
                msg = await channel.send(embed=embed)
                self.status_message_id = msg.id
                self.save_message_id()
        except Exception as e:
            import traceback
            print(f"[AMP] Loop error: {e}")
            print(traceback.format_exc())

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="ampstatus", description="Get AMP server status")
    async def ampstatus(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        async with aiohttp.ClientSession() as session:
            if not self.session_id:
                await self.amp_login(session)
            instances = await self.get_instances(session)
            await self.fetch_live_status(session, instances)
        await interaction.followup.send(embed=self.build_embed(instances))

    @app_commands.command(name="amplogin", description="Test AMP login")
    async def amplogin(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiohttp.ClientSession() as session:
            if await self.amp_login(session):
                await interaction.followup.send("✅ Login OK")
            else:
                await interaction.followup.send("❌ Login failed")

    @app_commands.command(name="amptest", description="Show AMP server states")
    async def amptest(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiohttp.ClientSession() as session:
                if not self.session_id:
                    await self.amp_login(session)
                instances = await self.get_instances(session)

            msg = "**AMP Server States:**\n"
            for item in instances:
                if isinstance(item, dict) and 'AvailableInstances' in item:
                    for server in item.get('AvailableInstances', []):
                        fname = server.get('FriendlyName', 'N/A')
                        state = server.get('AppState', '?')
                        iid = server.get('InstanceID', 'N/A')
                        msg += f"• `{fname}` State={state} ID={iid[:8]}...\n"

            await interaction.followup.send(msg[:1500])
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    @app_commands.command(name="ampdump", description="Debug AMP data")
    async def ampdump(self, interaction: discord.Interaction):
        lines = [f"• {s['name']}: {s.get('players', '0')}/{s.get('max_players', '70')} (state={s.get('app_state', '?')})" for s in self.servers.values()]
        server_list = "\n".join(lines)
        await interaction.response.send_message(f"**{len(self.servers)} Servers:**\n{server_list}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AmpStatus(bot))
    print("AMP status plugin loaded")
