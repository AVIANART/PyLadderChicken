### Schedule - ADMIN ONLY
Use the command `/schedule` to post the schedule in a channel. If the schedule already exists, this will force an update. Use `force: True` to create a new schedule message. The old message will be automatically deleted.

### Savior Roles - ADMIN ONLY
Use the command `/set_all_savior_roles <@role>` to set a savior role for that archetype. Come back afterwards with `/set_savior_role <archetype> <@role>` to change a specific archetype.

### Post-Race Channel - ADMIN ONLY
Use the command `/set_postrace_channel <#channel>` to set a post-race channel. On a successfully fired race, a separator message will posted in this channel, as well as reminder to use spoiler tags.

### Set Bot Logging Channel - ADMIN ONLY
Use the command `/set_bot_logging_channel` <#channel> to set the logging channel for the bot. All messages sent with `send_message` without a `channel_id` will be sent here.

### Roll Seed
Use the command `/roll_seed <mode> <race_mode>` to roll a seed from one of the modes.