import discord, time, tempfile, os, shutil, json
import regex as re
from discord.ext import commands
from Cogs import Settings, DisplayName, Utils, Nullify, PickList, Message, DL

def setup(bot):
	# Add the bot and deps
	settings = bot.get_cog("Settings")
	bot.add_cog(Responses(bot, settings))

class Responses(commands.Cog):

	# Init with the bot reference, and a reference to the settings var
	def __init__(self, bot, settings):
		self.bot = bot
		self.settings = settings
		global Utils, DisplayName
		Utils = self.bot.get_cog("Utils")
		DisplayName = self.bot.get_cog("DisplayName")
		# Regex values
		self.regexUserName = re.compile(r"\[\[user\]\]",         re.IGNORECASE)
		self.regexUserPing = re.compile(r"\[\[atuser\]\]",       re.IGNORECASE)
		self.regexServer   = re.compile(r"\[\[server\]\]",       re.IGNORECASE)
		self.regexHere     = re.compile(r"\[\[here\]\]",         re.IGNORECASE)
		self.regexEveryone = re.compile(r"\[\[everyone\]\]",     re.IGNORECASE)
		self.regexDelete   = re.compile(r"\[\[delete\]\]",       re.IGNORECASE)
		self.regexMute     = re.compile(r"\[\[mute:?\d*\]\]",    re.IGNORECASE)
		self.regexRoleMent = re.compile(r"\[\[(m_role|role_m):\d+\]\]",re.IGNORECASE)
		self.regexUserMent = re.compile(r"\[\[(m_user|user_m):\d+\]\]",re.IGNORECASE)
		self.regexKick     = re.compile(r"\[\[kick\]\]",         re.IGNORECASE)
		self.regexBan      = re.compile(r"\[\[ban\]\]",          re.IGNORECASE)
		self.regexSuppress = re.compile(r"\[\[suppress\]\]",     re.IGNORECASE)
		self.toggle_ur     = re.compile(r"\[\[t_ur:[\d,]+\]\]",  re.IGNORECASE)
		self.add_ur        = re.compile(r"\[\[add_ur:[\d,]+\]\]",re.IGNORECASE)
		self.set_ur        = re.compile(r"\[\[set_ur:\d+\]\]",   re.IGNORECASE)
		self.rem_ur        = re.compile(r"\[\[rem_ur:[\d,]+\]\]",re.IGNORECASE)
		self.react_ur      = re.compile(r"\[\[react_ur:.*\]\]",  re.IGNORECASE)
		self.toggle_r      = re.compile(r"\[\[t_r:[\d,]+\]\]",   re.IGNORECASE)
		self.add_r         = re.compile(r"\[\[add_r:[\d,]+\]\]", re.IGNORECASE)
		self.rem_r         = re.compile(r"\[\[rem_r:[\d,]+\]\]", re.IGNORECASE)
		self.react_r       = re.compile(r"\[\[react_r:.*\]\]",   re.IGNORECASE)
		self.in_chan       = re.compile(r"\[\[in:[\d,]+\]\]",    re.IGNORECASE)
		self.out_chan      = re.compile(r"\[\[out:(\d,?|dm?,?|pm?,?|o(r|rig|rigin|riginal)?,?)+\]\]",re.IGNORECASE)
		self.match_time    = 0.025

	async def _get_response(self, ctx, message, check_chan=True):
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return {}
		# Check for matching response triggers here
		content = message.replace("\n"," ") # Remove newlines for better matching
		response = {}
		start_time = time.perf_counter_ns()
		for trigger in message_responses:
			check_time = time.perf_counter_ns()
			try:
				if not re.fullmatch(trigger, content, timeout=self.match_time):
					continue
			except TimeoutError:
				response["catastrophies"] = response.get("catastrophies",[])+[trigger]
				continue
			response["matched"] = trigger
			response["match_time_ms"] = (time.perf_counter_ns()-check_time)/1000000
			response["total_time_ms"] = (time.perf_counter_ns()-start_time)/1000000
			# Got a full match - build the message, send it and bail
			m = message_responses[trigger]
			# Let's check for a channel - and make sure we're searching there
			try:
				channel_list = [int(x) for x in self.in_chan.search(m).group(0).replace("]]","").split(":")[-1].split(",") if x]
				check_channels = [x for x in map(self.bot.get_channel,channel_list) if x]
			except:
				check_channels = []
			response["channels"] = check_channels
			if check_chan and check_channels and not ctx.channel in check_channels: # Need to be in the right channel, no match
				continue
			# Let's check for output channels
			output_channels = []
			try:
				for x in self.out_chan.search(m).group(0).replace("]]","").split(":")[-1].split(","):
					if not x: continue # Skip empty entries
					if x.isdigit(): # Got a channel id
						check_channel = self.bot.get_channel(int(x))
						if check_channel and not check_channel in output_channels:
							output_channels.append(check_channel)
					elif x.lower().startswith("o") and not ctx.channel in output_channels: # Got the original channel
						output_channels.append(ctx.channel)
					elif not ctx.author in output_channels: # dm/pm/etc
						output_channels.append(ctx.author)
			except:
				pass
			if not output_channels: output_channels = [ctx.channel] # Ensure the original if none resolved
			response["outputs"] = output_channels
			if self.regexDelete.search(m): response["delete"] = True
			if self.regexSuppress.search(m): response["suppress"] = True
			action = "ban" if self.regexBan.search(m) else "kick" if self.regexKick.search(m) else "mute" if self.regexMute.search(m) else None
			if action:
				response["action"] = action
				if action == "mute":
					# Let's get the mute time - if any
					try: response["mute_time"] = int(self.regexMute.search(m).group(0).replace("]]","").split(":")[-1])
					except: pass
			m = re.sub(self.regexUserName, "{}".format(DisplayName.name(ctx.author)), m)
			m = re.sub(self.regexUserPing, "{}".format(ctx.author.mention), m)
			m = re.sub(self.regexServer,   "{}".format(Nullify.escape_all(ctx.guild.name)), m)
			m = re.sub(self.regexHere,     "@here", m)
			m = re.sub(self.regexEveryone, "@everyone", m)
			d = re.compile("\\d+")
			mentions = {
				"user": {
					"list":self.regexUserMent.finditer(m),
					"func":ctx.guild.get_member
				},
				"role": {
					"list":self.regexRoleMent.finditer(m),
					"func":ctx.guild.get_role
				}
			}
			for t in mentions:
				if not "func" in mentions[t]: continue # borken
				func = mentions[t]["func"]
				for mention in mentions[t].get("list",[]):
					# Convert the id to a member - make sure that resolves, then replace
					try:
						check_id = int(d.search(mention.group(0)).group(0))
						resolved = func(check_id)
						assert resolved
					except:
						continue # Broken, or didn't resolve
					m = m.replace(mention.group(0),resolved.mention)
			user_role_add = []
			user_role_rem = []
			# Walk the user role options if any - use the following priority: toggle -> add -> rem -> set
			if any((x.search(m) for x in (self.toggle_ur,self.add_ur,self.rem_ur,self.set_ur))):
				# We have at least one match - get some default values
				one_role = self.settings.getServerStat(ctx.guild,"OnlyOneUserRole",True)
				ur_block = self.settings.getServerStat(ctx.guild,"UserRoleBlock",[])
			for c in (self.toggle_ur,self.add_ur,self.set_ur,self.rem_ur):
				ur = c.search(m)
				if not ur: continue
				# Got one - let's verify it's valid, and apply if needed
				if Utils.is_bot_admin(ctx) or not ctx.author.id in ur_block: # Not blocked - keep going
					ur_list = [x.get("ID",0) for x in self.settings.getServerStat(ctx.guild,"UserRoles",[])]
					# Got a match - let's verify they're valid, and apply if needed
					roles = []
					for x in ur.group(0).replace("]]","").split(":")[-1].split(","):
						if not x: continue # Skip empty entries
						if x.isdigit(): # Got a role id
							check_role = ctx.guild.get_role(int(x))
							if check_role and check_role.id in ur_list and not check_role in roles:
								roles.append(check_role)
					for role in roles:
						local = c # Initialize for multiple roles
						if local == self.toggle_ur:
							local = self.rem_ur if role in ctx.author.roles else self.add_ur
						if one_role and local == self.add_ur:
							local = self.set_ur # Force set instead of add
						if local == self.add_ur and not role in ctx.author.roles and not role in user_role_add: # Add it
							user_role_add.append(role)
						elif local == self.rem_ur and role in ctx.author.roles and not role in user_role_rem: # Remove it
							user_role_rem.append(role)
						elif local == self.set_ur: # Remove all user roles *but* this one
							user_role_rem = [x for x in map(ctx.guild.get_role,ur_list) if x and x in ctx.author.roles and x.id!=role.id]
							user_role_add = [] if role in ctx.author.roles else [role]
			# Set up helper function for resolving emojis
			def check_emojis(e_search,m,add_list,rem_list):
				emojis_resolved = []
				try:
					emoji_string = ":".join(e_search.search(m).group(0).replace("]]","").split(":")[1:])
					emojis = [x.strip() for x in emoji_string.split(",")]
					for emoji in emojis:
						if all((x in emoji for x in (":","<",">"))): # Assume custom
							try: emoji = self.bot.get_emoji(int(emoji.strip("<>").split(":")[-1]))
							except: emoji = None
						else: # Assume standard emoji
							try:
								e_check = emoji.split()[0] # Split on white space, and get only the first
								# Hack to see if the passed char is unicode
								emoji = e_check if str(e_check.encode("unicode-escape"))[2] == "\\" else None
							except: emoji = None
						emojis_resolved.append(emoji)
				except: pass
				# See what we need to add
				reactions = []
				if add_list and emojis_resolved and emojis_resolved[0]:
					reactions.append(emojis_resolved[0])
				if rem_list and len(emojis_resolved)>1 and emojis_resolved[1]:
					reactions.append(emojis_resolved[1])
				if not add_list and not rem_list and len(emojis_resolved)>2 and emojis_resolved[2]:
					reactions.append(emojis_resolved[2])
				return reactions
			# Set our user role reactions
			user_role_react = [] #check_emojis(self.react_ur,m,user_role_add,user_role_rem)
			# Retain the added and removed user roles
			if user_role_add: response["user_roles_added"] = user_role_add
			if user_role_rem: response["user_roles_removed"] = user_role_rem
			if user_role_react: response["user_roles_react"] = user_role_react
			# Let's go through the regular non-UserRole roles
			role_add = []
			role_rem = []
			role_react = []
			# Iterate the regular roles if any: toggle -> add -> rem
			for c in (self.toggle_r,self.add_r,self.rem_r):
				r = c.search(m)
				if not r: continue
				# Got a match - let's verify they're valid, and apply if needed
				roles = []
				for x in r.group(0).replace("]]","").split(":")[-1].split(","):
					if not x: continue # Skip empty entries
					if x.isdigit(): # Got a role id
						check_role = ctx.guild.get_role(int(x))
						if check_role and not check_role in roles and not check_role.permissions.administrator:
							roles.append(check_role)
				for role in roles:
					local = c # Iniitialize for multiple roles
					if local == self.toggle_r:
						local = self.rem_r if role in ctx.author.roles else self.add_r
					if local == self.add_r and not role in ctx.author.roles and not any((role in x for x in (role_add,user_role_add))): # Add it
						role_add.append(role)
					elif local == self.rem_r and role in ctx.author.roles and not any((role in x for x in (role_rem,user_role_rem))): # Remove it
						role_rem.append(role)
			# Set our role reactions
			role_react = check_emojis(self.react_r,m,role_add,role_rem)
			# Retain the added and removed roles
			if role_add: response["roles_added"] = role_add
			if role_rem: response["roles_removed"] = role_rem
			if role_react: response["roles_react"] = role_react
			# Strip out leftovers from delete, ban, kick, mute, suppress, and the user role options
			for sub in (
				self.regexDelete,
				self.regexBan,
				self.regexKick,
				self.regexMute,
				self.regexSuppress,
				self.toggle_ur,
				self.add_ur,
				self.set_ur,
				self.rem_ur,
				self.react_ur,
				self.toggle_r,
				self.add_r,
				self.rem_r,
				self.react_r,
				self.in_chan,
				self.out_chan
			):
				m = re.sub(sub,"",m)
			response["message"] = m
			break
		if not "total_time_ms" in response: # Get the total time to check
			response["total_time_ms"] = (time.perf_counter_ns()-start_time)/1000000
		return response

	@commands.Cog.listener()
	async def on_message(self, message):
		# Gather exclusions - no bots, no dms, and don't check if running a command
		if message.author.bot: return
		if not message.guild: return
		ctx = await self.bot.get_context(message)
		if ctx.command: return
		# Gather the response info - if any
		response = await self._get_response(ctx,message.content)
		if not response.get("matched"): return
		# See if we're admin/bot-admin - and bail if suppressed
		if Utils.is_bot_admin(ctx) and response.get("suppress"): return
		# Walk punishments in order of severity (ban -> kick -> mute)
		if response.get("action") in ("ban","kick"):
			action = ctx.guild.ban if response["action"] == "ban" else ctx.guild.kick
			await action(ctx.author,reason="Response trigger matched")
		elif response.get("action") == "mute":
			mute = self.bot.get_cog("Mute")
			mute_time = None if not response.get("mute_time") else int(time.time())+response["mute_time"]
			if mute: await mute._mute(ctx.author,ctx.guild,cooldown=mute_time)
		# Check if we need to delete the message
		if response.get("delete"):
			try: await message.delete()
			except: pass # RIP - couldn't delete that one, I guess
		if response.get("message","").strip(): # Don't send an empty message, or one with just whitespace
			for output in response.get("outputs",[]):
				# Try to send the response to all defined outputs
				try: await output.send(response["message"],allowed_mentions=discord.AllowedMentions.all())
				except: continue
		# Check for role changes
		roles_added = response.get("user_roles_added",[])+response.get("roles_added",[])
		roles_removed = response.get("user_roles_removed",[])+response.get("roles_removed",[])
		if roles_added:
			self.settings.role.add_roles(ctx.author, roles_added)
		if roles_removed:
			self.settings.role.rem_roles(ctx.author, roles_removed)
		reactions = response.get("user_roles_react",[])+response.get("roles_react",[])
		if reactions and not response.get("delete"): # Only react if we're not deleting the message
			for reaction in reactions:
				try: await message.add_reaction(reaction)
				except: pass

	def _check_roles(self, ctx, response):
		for r in (self.toggle_r,self.add_r,self.rem_r):
			r_search = r.search(response)
			if not r_search: continue # No match
			roles = [] # Gather any valid roles
			for x in r_search.group(0).replace("]]","").split(":")[-1].split(","):
				if not x: continue # Skip empty entries
				if x.isdigit(): # Got a role id
					check_role = ctx.guild.get_role(int(x))
					if check_role and not check_role in roles:
						roles.append(check_role)
			# Walk the roles gathered - check if any are admin, or >= our top role
			for role in roles:
				# Disallow admin roles in this functionality
				if role.permissions.administrator:
					return None
				# Got a role - let's see if the ctx.author has a role equal to or higher than it
				if ctx.author.top_role <= role:
					return False
		return True

	@commands.command()
	async def addresponse(self, ctx, regex_trigger = None, *, response = None):
		"""Adds a new response for the regex trigger - or updates the response if the trigger exists already.  If the trigger has spaces, it must be wrapped in quotes (bot-admin only).
		
		Value substitutions:
		
		[[user]]      = sender's name
		[[server]]    = server name

		Mention options:

		[[atuser]]    = sender mention
		[[m_role:id]] = role mention where id is the role id
		[[m_user:id]] = user mention where id is the user id
		[[here]]      = @here ping
		[[everyone]]  = @everyone ping

		Standard user behavioral flags (do not apply to admin/bot-admin):

		[[delete]]    = delete the original message
		[[ban]]       = bans the message author
		[[kick]]      = kicks the message author
		[[mute]]      = mutes the author indefinitely
		[[mute:#]]    = mutes the message author for # seconds
		[[in:id]]     = locks the check to the comma-delimited channel ids passed
		[[out:id]]    = sets the output targets to the comma-delimited channel ids passed
		                - can also accept "dm" to dm the author, and "original" to send in
						  the original channel where the response was triggered

		User role options (roles must be setup per the UserRole cog):

		[[t_ur:id]]   = add or remove the user role based on whether the author has it
		[[add_ur:id]] = add the user role if the author does not have it
		[[rem_ur:id]] = remove the user role if the author has it
		[[set_ur:id]] = same as above, but removes any other user roles the author has
		[[react_ur:add,rem,nochange]] = reactions to apply to the author's message when roles are
										added, removed, or no change happens (the bot must be on
										the server the emoji originates from)

		(id = the role id)
		* If multiple role options are passed, they are processed in the order above
		* t_r, add_r, rem_r, and react_r have the same functionality as above, but without the UserRole requirement

		Admin/bot-admin behavioral flags:

		[[suppress]] = suppresses output for admin/bot-admin author matches
		
		Example:  $addresponse "(?i)(hello there|\\btest\\b).*" [[atuser]], this is a test!
		
		This would look for a message starting with the whole word "test" or "hello there" (case-insensitive) and respond by pinging the user and saying "this is a test!"
		"""

		if not await Utils.is_bot_admin_reply(ctx): return
		if not regex_trigger or not response: return await ctx.send("Usage: `{}addresponse regex_trigger response`".format(ctx.prefix))
		# Ensure the regex is valid
		try: re.compile(regex_trigger)
		except Exception as e: return await ctx.send(Nullify.escape_all(str(e)))
		# Make sure we're not allowing admin roles or equal/higher role manipulation
		roles_check = self._check_roles(ctx,response)
		if not roles_check:
			return await ctx.send("You cannot manage {} with this command!".format(
				"admin roles" if roles_check is None else "roles equal to or higher than your top role"
			))
		# Save the trigger and response
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		context = "Updated" if regex_trigger in message_responses else "Added new"
		message_responses[regex_trigger] = response
		self.settings.setServerStat(ctx.guild, "MessageResponses", message_responses)
		return await ctx.send("{} response trigger!".format(context))

	@commands.command()
	async def edittrigger(self, ctx, response_index = None, *, regex_trigger = None):
		"""Edits the regex trigger for the passed index.  The triggers passed here do not require quotes if there are spaces (bot-admin only)."""

		if not await Utils.is_bot_admin_reply(ctx): return
		if not regex_trigger or not response_index: return await ctx.send("Usage: `{}edittrigger response_index regex_trigger`".format(ctx.prefix))
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		# Ensure the passed index is valid
		try:
			response_index = int(response_index)
			assert 0 < response_index <= len(message_responses)
		except:
			return await ctx.send("You need to pass a valid integer from 1 to {:,}.\nYou can get a numbered list with `{}responses`".format(len(message_responses),ctx.prefix))
		# Ensure the regex is valid
		try: re.compile(regex_trigger)
		except Exception as e: return await ctx.send(Nullify.escape_all(str(e)))
		# Update the response
		ordered_responses = {}
		for index,key in enumerate(message_responses,start=1):
			ordered_responses[regex_trigger if index==response_index else key] = message_responses[key]
		self.settings.setServerStat(ctx.guild,"MessageResponses",ordered_responses)
		return await ctx.send("Updated response trigger at index {:,}!".format(response_index))

	@commands.command()
	async def editresponse(self, ctx, response_index = None, *, response = None):
		"""Edits the response for the passed index.  The response passed here does not require quotes if there are spaces (bot-admin only).
		
		Value substitutions:
		
		[[user]]      = sender's name
		[[server]]    = server name

		Mention options:

		[[atuser]]    = sender mention
		[[m_role:id]] = role mention where id is the role id
		[[m_user:id]] = user mention where id is the user id
		[[here]]      = @here ping
		[[everyone]]  = @everyone ping

		Standard user behavioral flags (do not apply to admin/bot-admin):

		[[delete]]    = delete the original message
		[[ban]]       = bans the message author
		[[kick]]      = kicks the message author
		[[mute]]      = mutes the author indefinitely
		[[mute:#]]    = mutes the message author for # seconds
		[[in:id]]     = locks the check to the comma-delimited channel ids passed
		[[out:id]]    = sets the output targets to the comma-delimited channel ids passed
		                - can also accept "dm" to dm the author, and "original" to send in
						  the original channel where the response was triggered

		User role options (roles must be setup per the UserRole cog):

		[[t_ur:id]]   = add or remove the user role based on whether the author has it
		[[add_ur:id]] = add the user role if the author does not have it
		[[rem_ur:id]] = remove the user role if the author has it
		[[set_ur:id]] = same as above, but removes any other user roles the author has
		[[react_ur:add,rem,nochange]] = reactions to apply to the author's message when roles are
										added, removed, or no change happens (the bot must be on
										the server the emoji originates from)

		(id = the role id)
		* If multiple role options are passed, they are processed in the order above
		* t_r, add_r, rem_r, and react_r have the same functionality as above, but without the UserRole requirement

		Admin/bot-admin behavioral flags:

		[[suppress]] = suppresses output for admin/bot-admin author matches
		
		Example:  $editresponse 1 [[atuser]], this is a test!
		
		This would edit the first response trigger to respond by pinging the user and saying "this is a test!"""

		if not await Utils.is_bot_admin_reply(ctx): return
		if not response or not response_index: return await ctx.send("Usage: `{}editresponse response_index response`".format(ctx.prefix))
		# Make sure we're not allowing admin roles or equal/higher role manipulation
		roles_check = self._check_roles(ctx,response)
		if not roles_check:
			return await ctx.send("You cannot manage {} with this command!".format(
				"admin roles" if roles_check is None else "roles equal to or higher than your top role"
			))
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		# Ensure the passed index is valid
		try:
			response_index = int(response_index)
			assert 0 < response_index <= len(message_responses)
		except:
			return await ctx.send("You need to pass a valid integer from 1 to {:,}.\nYou can get a numbered list with `{}responses`".format(len(message_responses),ctx.prefix))
		# Update the response
		message_responses[list(message_responses)[response_index-1]] = response
		self.settings.setServerStat(ctx.guild,"MessageResponses",message_responses)
		return await ctx.send("Updated response at index {:,}!".format(response_index))

	@commands.command(aliases=["listresponses"])
	async def responses(self, ctx):
		"""Lists the response triggers and their responses (bot-admin only)."""
		
		if not await Utils.is_bot_admin_reply(ctx): return
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		entries = [{"name":"{}. ".format(i)+Nullify.escape_all(x),"value":Nullify.escape_all(message_responses[x])} for i,x in enumerate(message_responses,start=1)]
		return await PickList.PagePicker(title="Current Responses ({:,} total)".format(len(entries)),list=entries,ctx=ctx).pick()

	@commands.command(aliases=["removeresponse","deleteresponse","delresponse"])
	async def remresponse(self, ctx, *, regex_trigger_number = None):
		"""Removes the passed response trigger (bot-admin only)."""
		
		if not await Utils.is_bot_admin_reply(ctx): return
		if not regex_trigger_number: return await ctx.send("Usage: `{}remresponse regex_trigger_number`\nYou can get a numbered list with `{}responses`".format(ctx.prefix,ctx.prefix))
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		# Make sure we got a number, and it's within our list range
		try:
			regex_trigger_number = int(regex_trigger_number)
			assert 0 < regex_trigger_number <= len(message_responses)
		except:
			return await ctx.send("You need to pass a valid integer from 1 to {:,}.\nYou can get a numbered list with `{}responses`".format(len(message_responses),ctx.prefix))
		# Remove it, save, and report
		message_responses.pop(list(message_responses)[regex_trigger_number-1],None)
		self.settings.setServerStat(ctx.guild, "MessageResponses", message_responses)
		return await ctx.send("Response trigger removed!")

	@commands.command()
	async def saveresponses(self, ctx):
		"""Saves the responses dictionary to a json file and uploads."""

		if not await Utils.is_bot_admin_reply(ctx): return
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		message = await ctx.send("Saving responses and uploading...")
		temp = tempfile.mkdtemp()
		temp_json = os.path.join(temp,"Responses.json")
		try:
			json.dump(message_responses,open(temp_json,"w"),indent=2)
			await ctx.send(file=discord.File(temp_json))
		except:
			return await message.edit(content="Could not save or upload responses :(")
		finally:
			shutil.rmtree(temp,ignore_errors=True)
		await message.edit(content="Uploaded Responses.json! ({:,})".format(len(message_responses)))

	@commands.command(aliases=["addresponses"])
	async def loadresponses(self, ctx, url=None):
		"""Loads the passed json attachment or URL into the responses dictionary."""

		if not await Utils.is_bot_admin_reply(ctx): return
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not isinstance(message_responses,dict):
			message_responses = {} # Clear it out if it's malformed
		if url is None and len(ctx.message.attachments) == 0:
			return await ctx.send("Usage: `{}loadresponses [url or attachment]`".format(ctx.prefix))
		if url is None:
			url = ctx.message.attachments[0].url
		message = await ctx.send("Downloading and parsing...")
		try:
			items = await DL.async_json(url.strip("<>"))
		except:
			return await message.edit(content="Could not serialize data :(")
		if not items:
			return await message.edit(content="Json data is empty :(")
		if not isinstance(items,dict):
			return await message.edit(content="Malformed json data :(")
		# At this point - we should have a valid json file with our data - let's add it.
		added = 0
		updated = 0
		skipped = 0
		for x,i in enumerate(items,start=1):
			# Make sure it's valid regex
			try: re.compile(i)
			except:
				skipped += 1
				continue # Skip it
			# Make sure we're not allowing admin roles or equal/higher role manipulation
			if not self._check_roles(ctx,items[i]):
				skipped += 1
				continue
			if i in message_responses:
				updated += 1
			else:
				added += 1
			message_responses[i] = items[i]
		# Save the results
		self.settings.setServerStat(ctx.guild, "MessageResponses", message_responses)
		if added and updated:
			msg = "Added {:,} new and updated {:,} existing response{} out of {:,} passed!".format(
				added,updated,"" if updated == 1 else "s",len(items)
			)
		elif added:
			msg = "Added {:,} new response{} out of {:,} passed!".format(added,"" if added == 1 else "s",len(items))
		elif updated:
			msg = "Updated {:,} existing response{} out of {:,} passed!".format(updated,"" if updated == 1 else "s",len(items))
		else:
			msg = "No responses added or updated out of {:,} passed!".format(len(items))
		if skipped:
			msg += " ({:,} skipped)".format(skipped)
		await message.edit(content=msg)

	@commands.command(aliases=["clrresponses"])
	async def clearresponses(self, ctx):
		"""Removes all response triggers (bot-admin only)."""

		if not await Utils.is_bot_admin_reply(ctx): return
		self.settings.setServerStat(ctx.guild, "MessageResponses", {})
		return await ctx.send("All response triggers removed!")

	@commands.command(aliases=["moveresponse"])
	async def mvresponse(self, ctx, response_index = None, target_index = None):
		"""Moves the passed response index to the target index (bot-admin only)."""

		if not await Utils.is_bot_admin_reply(ctx): return
		if response_index == None or target_index == None:
			return await ctx.send("Usage: `{}mvresponse [response_index] [target_index]`\nYou can get a numbered list with `{}responses`".format(ctx.prefix,ctx.prefix))
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		# Make sure our indices are within the proper range
		try:
			response_index = int(response_index)
			target_index = int(target_index)
			assert all((0 < x <= len(message_responses) for x in (response_index,target_index)))
		except:
			return await ctx.send("Both `response_index` and `target_index` must be valid intergers from 1 to {:,}.\nYou can get a numbered list with `{}responses`".format(len(message_responses),ctx.prefix))
		if response_index == target_index: return await ctx.send("Both indices are the same - nothing to move!")
		# Let's get the keys in a list - remove the target, add it to the desired index, then build a new dict with the elements
		keys = list(message_responses)
		keys.insert(target_index-1,keys.pop(response_index-1))
		ordered_responses = {}
		for key in keys: ordered_responses[key] = message_responses[key]
		self.settings.setServerStat(ctx.guild,"MessageResponses",ordered_responses)
		return await ctx.send("Moved response from {:,} to {:,}!".format(response_index,target_index))

	@commands.command(aliases=["checkresponse"])
	async def chkresponse(self, ctx, *, check_string = None):
		"""Reports a breakdown of the first match (if any) in the responses for the passed check string (bot-admin only)."""

		if not await Utils.is_bot_admin_reply(ctx): return
		if check_string == None: return await ctx.send("Usage: `{}checkresponse [check_string]`\nYou can get a numbered list with `{}responses`".format(ctx.prefix,ctx.prefix))
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		response = await self._get_response(ctx,check_string,check_chan=False)
		catastrophies = None
		if response.get("catastrophies"):
			catastrophies = "\n".join(["**{}.** {}".format(i,Nullify.escape_all(x)) for i,x in enumerate(response["catastrophies"],start=1)])
		if not response.get("matched"):
			if catastrophies:
				return await PickList.PagePicker(
					title="No Matches",
					description="The following timed out (>{:,} second{}) while checking - likely due to catastrophic backtracking ({:,} total):\n\n{}".format(
						self.match_time,
						"" if self.match_time==1 else "s",
						len(response["catastrophies"]),
						catastrophies
					),
					ctx=ctx,
					footer="All checks took {:,} ms".format(response["total_time_ms"]) if "total_time_ms" in response else None
				).pick()
			return await Message.Embed(
				title="No Matches",
				description="No triggers matched the passed message",
				color=ctx.author,
				footer="All checks took {:,} ms".format(response["total_time_ms"]) if "total_time_ms" in response else None
			).send(ctx)
		# Got a match - let's print out what it will do
		description = Nullify.escape_all(response.get("matched","Unknown match"))
		entries = []
		# Let's walk the reponse and add values
		entries.append({"name":"Output Suppressed for Admin/Bot-Admin:","value":"Yes" if response.get("suppress") else "No"})
		if response.get("channels"):
			entries.append({"name":"Limited To:","value":"\n".join([x.mention for x in response["channels"]])})
		if response.get("action") == "mute":
			mute_time = "indefinitely" if not response.get("mute_time") else "for {:,} second{}".format(response["mute_time"],"" if response["mute_time"]==1 else "s")
			entries.append({"name":"Action:","value":"Mute {}".format(mute_time)})
		else:
			entries.append({"name":"Action:","value":str(response.get("action")).capitalize()})
		entries.append({"name":"Delete:","value":"Yes" if response.get("delete") else "No"})
		entries.append({"name":"Output Message:","value":"None" if not response.get("message","").strip() else response["message"]})
		if response.get("user_roles_added"):
			entries.append({"name":"UserRoles Added:","value":"\n".join([x.mention for x in response["user_roles_added"]])})
		if response.get("user_roles_removed"):
			entries.append({"name":"UserRoles Removed:","value":"\n".join([x.mention for x in response["user_roles_removed"]])})
		if response.get("roles_added"):
			entries.append({"name":"Roles Added:","value":"\n".join([x.mention for x in response["roles_added"]])})
		if response.get("roles_removed"):
			entries.append({"name":"Roles Removed:","value":"\n".join([x.mention for x in response["roles_removed"]])})
		if response.get("user_roles_react"):
			entries.append({"name":"UserRole Reactions","value":"".join([str(x) for x in response["user_roles_react"]])})
		if response.get("user_roles_react"):
			entries.append({"name":"Role Reactions","value":"".join([str(x) for x in response["roles_react"]])})
		if response.get("outputs",[]):
			entries.append({"name":"Output Targets:","value":"\n".join([x.mention for x in response["outputs"]])})
		if catastrophies:
			entries.append({"name":"Catastrophically Backtracked ({:,} total):".format(len(response["catastrophies"])),"value":catastrophies})
		return await PickList.PagePicker(title="Matched Response",description=description,list=entries,ctx=ctx,footer="Matched in {:,} ms (total checks took {:,} ms)".format(response["match_time_ms"],response["total_time_ms"])).pick()

	@commands.command(aliases=["getresponse"])
	async def viewresponse(self, ctx, response_index = None):
		"""Displays the response in full which corresponds to the target index (bot-admin only)."""

		if not await Utils.is_bot_admin_reply(ctx): return
		if response_index == None: return await ctx.send("Usage: `{}viewresponse [response_index]`\nYou can get a numbered list with `{}responses`".format(ctx.prefix,ctx.prefix))
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		# Make sure we got a number, and it's within our list range
		try:
			response_index = int(response_index)
			assert 0 < response_index <= len(message_responses)
		except:
			return await ctx.send("You need to pass a valid integer from 1 to {:,}.\nYou can get a numbered list with `{}responses`".format(len(message_responses),ctx.prefix))
		return await Message.EmbedText(
			title="Response at index {:,}".format(response_index),
			description=Nullify.escape_all(message_responses[list(message_responses)[response_index-1]]),
			color=ctx.author
		).send(ctx)

	@commands.command(aliases=["gettrigger"])
	async def viewtrigger(self, ctx, response_index = None):
		"""Displays the regex trigger in full which corresponds to the target index (bot-admin only)."""

		if not await Utils.is_bot_admin_reply(ctx): return
		if response_index == None: return await ctx.send("Usage: `{}viewtrigger [response_index]`\nYou can get a numbered list with `{}responses`".format(ctx.prefix,ctx.prefix))
		message_responses = self.settings.getServerStat(ctx.guild, "MessageResponses", {})
		if not message_responses: return await ctx.send("No responses setup!  You can use the `{}addresponse` command to add some.".format(ctx.prefix))
		# Make sure we got a number, and it's within our list range
		try:
			response_index = int(response_index)
			assert 0 < response_index <= len(message_responses)
		except:
			return await ctx.send("You need to pass a valid integer from 1 to {:,}.\nYou can get a numbered list with `{}responses`".format(len(message_responses),ctx.prefix))
		return await Message.EmbedText(
			title="Trigger at index {:,}".format(response_index),
			description=Nullify.escape_all(list(message_responses)[response_index-1]),
			color=ctx.author
		).send(ctx)
