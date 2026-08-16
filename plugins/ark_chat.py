import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import json
import os
import re
import ssl
from datetime import datetime
import socket
import struct

class ArkChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_config()
        self.session_id = None
        self.instance_sessions = {}
        self.last_update_ids = {}  # track last AMP update per instance
        
        if self.servers and self.amp_url:
            self.chat_loop.start()

    def cog_unload(self):
        self.chat_loop.cancel()

    def load_config(self):
        try:
            with open('configs/private.keys', 'r') as f:
                secrets = json.load(f)
            self.amp_url = secrets.get('amp_url', '').rstrip('/')
            self.amp_user = secrets.get('amp_user', '')
            self.amp_password = secrets.get('amp_password', '')
            self.rcon_password = secrets.get('rcon_password', '')
        except Exception as e:
            print(f"[ARKChat] Config error: {e}")
            self.amp_url = ''
            self.amp_user = ''
            self.amp_password = ''
            self.rcon_password = ''

        try:
            with open('configs/ark_chat.json', 'r') as f:
                data = json.load(f)
                self.servers = {
                    name: cfg for name, cfg in data.get('servers', {}).items()
                    if cfg.get('enabled') and cfg.get('channel_id') and cfg.get('instance_id')
                }
                print(f"[ARKChat] Loaded {len(self.servers)} enabled servers")
        except Exception as e:
            print(f"[ARKChat] Servers config error: {e}")
            self.servers = {}

    async def amp_login(self, session):
        try:
            url = f"{self.amp_url}/API/Core/Login"
            headers = {"Accept": "application/vnd.cubecoders-ampapi+json", "Content-Type": "application/json"}
            payload = {"username": self.amp_user, "password": self.amp_password, "token": "", "rememberMe": False}
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get('success'):
                    self.session_id = data.get('sessionID')
                    return True
                return False
        except Exception as e:
            print(f"[ARKChat] Login error: {e}")
            return False

    async def login_to_instance_proxy(self, session, instance_id):
        try:
            url = f"{self.amp_url}/API/ADSModule/Servers/{instance_id}/API/Core/Login"
            headers = {"Accept": "application/vnd.cubecoders-ampapi+json", "Content-Type": "application/json"}
            payload = {"username": self.amp_user, "password": self.amp_password, "token": "", "rememberMe": False, "SESSIONID": self.session_id}
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get('success'):
                    return data.get('sessionID')
        except Exception as e:
            print(f"[ARKChat] Proxy login error: {e}")
        return None

    async def get_console_updates(self, session, instance_id, inst_session):
        """Get console updates from AMP instance"""
        try:
            last_id = self.last_update_ids.get(instance_id, 0)
            url = f"{self.amp_url}/API/ADSModule/Servers/{instance_id}/API/Core/GetUpdates"
            headers = {"Accept": "application/vnd.cubecoders-ampapi+json", "Content-Type": "application/json"}
            payload = {"SESSIONID": inst_session, "LastID": last_id}
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                # Update last ID
                if isinstance(data, dict):
                    entries = data.get('ConsoleEntries', [])
                    if entries:
                        self.last_update_ids[instance_id] = entries[-1].get('Id', last_id)
                    return entries
        except Exception as e:
            print(f"[ARKChat] GetUpdates error: {e}")
        return []

    def parse_chat(self, line):
        """Parse ARK chat line, returns (username, message) or None"""
        pattern = r'^[\d\.]+_[\d\.]+: (?P<username>.+?) \((?:.+?)\): (?P<message>.+?)$'
        match = re.match(pattern, line.strip())
        if match:
            return match.group('username'), match.group('message')
        return None

    def parse_join_leave(self, line):
        """Parse join/leave line, returns (username, action) or None"""
        join_pattern = r'^[\d\.]+_[\d\.]+: (?P<username>.+?) \[UniqueNetId:.+?\] joined this ARK'
        leave_pattern = r'^[\d\.]+_[\d\.]+: (?P<username>.+?) \[UniqueNetId:.+?\] left this ARK'
        
        match = re.match(join_pattern, line.strip())
        if match:
            return match.group('username'), 'joined'
        
        match = re.match(leave_pattern, line.strip())
        if match:
            return match.group('username'), 'left'
        
        return None

    async def send_rcon(self, server_name, message):
        """Send message to ARK server via RCON using raw socket"""
        cfg = self.servers.get(server_name)
        if not cfg:
            return False
        try:
            host = cfg['rcon_host']
            port = cfg['rcon_port']
            password = self.rcon_password

            reader, writer = await asyncio.open_connection(host, port)

            def make_packet(req_id, pkt_type, body):
                body_bytes = body.encode('utf-8') + b'\x00\x00'
                size = 4 + 4 + len(body_bytes)
                return struct.pack('<iii', size, req_id, pkt_type) + body_bytes

            # Auth packet
            writer.write(make_packet(1, 3, password))
            await writer.drain()
            await asyncio.sleep(0.1)
            await reader.read(4096)  # Read auth response

            # Command packet
            writer.write(make_packet(2, 2, f"ServerChat {message}"))
            await writer.drain()
            await asyncio.sleep(0.1)
            await reader.read(4096)  # Read command response

            writer.close()
            await writer.wait_closed()
            print(f"[ARKChat] RCON sent to {server_name}: {message}")
            return True
        except Exception as e:
            print(f"[ARKChat] RCON error for {server_name}: {e}")
            return False

    @tasks.loop(seconds=10)
    async def chat_loop(self):
        print("[ARKChat] Loop tick")
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            
            async with aiohttp.ClientSession(connector=connector) as session:
                if not self.session_id:
                    if not await self.amp_login(session):
                        return

                for server_name, cfg in self.servers.items():
                    instance_id = cfg['instance_id']
                    channel_id = cfg['channel_id']

                    # Get or create instance session
                    inst_session = self.instance_sessions.get(instance_id)
                    if not inst_session:
                        inst_session = await self.login_to_instance_proxy(session, instance_id)
                        if inst_session:
                            self.instance_sessions[instance_id] = inst_session
                        else:
                            continue

                    # Get console updates
                    entries = await self.get_console_updates(session, instance_id, inst_session)

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        continue

                    for entry in entries:
                        line = entry.get('Contents', '')
                        if not line:
                            continue

                        # Check for chat
                        result = self.parse_chat(line)
                        if result:
                            username, message = result
                            await channel.send(f"**({username}):** {message}")
                            print(f"[ARKChat] {server_name} chat: <{username}> {message}")
                            continue

                        # Check for join/leave
                        result = self.parse_join_leave(line)
                        if result:
                            username, action = result
                            icon = "✅" if action == 'joined' else "👋"
                            await channel.send(f"{icon} **{username}** {action} {server_name}")
                            print(f"[ARKChat] {server_name}: {username} {action}")

        except Exception as e:
            import traceback
            print(f"[ARKChat] Loop error: {e}")
            print(traceback.format_exc())

    @chat_loop.before_loop
    async def before_chat_loop(self):
        await self.bot.wait_until_ready()

    async def relay_to_ark(self, message):
        """Relay Discord messages to ARK"""
        print(f"[ARKChat] relay_to_ark: {message.channel.id}")

        for server_name, cfg in self.servers.items():
            if message.channel.id == cfg['channel_id']:
                discord_msg = f"({message.author.display_name}): {message.content}"
                await self.send_rcon(server_name, discord_msg)
                print(f"[ARKChat] Discord→{server_name}: {discord_msg}")
                break

async def setup(bot):
    await bot.add_cog(ArkChat(bot))
    print("ARK chat plugin loaded")
