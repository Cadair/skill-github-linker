An opsdroid skill for Linking to GitHub Issues
==============================================

This skill is used to provide links to, and information about, GitHub issues and Pull Requests when they are mentioned in a room.
It is mainly focused on matrix rooms, but should work with any supported opsdroid connector.


Getting Started
---------------

[Install opsdroid](https://docs.opsdroid.dev/en/stable/installation.html) and then use the example config file in this repo to get going.
See the documentation on [the matrix connector](https://docs.opsdroid.dev/en/stable/connectors/matrix.html) or any other connector to customise the configuration.
At this point the skill has no options.

Using the Bot
-------------

The bot should respond to the first occurance of `org/repo#number` or `#number` in a message and provide a reply with the link, title, issue number, labels and milestone information about that issue.

To make `#number` work a default repository must be set.
To do this run `!github default_repo org/repo`, if you have configured the matrix database the bot will need permissions to set the `dev.opsdroid.database` state event in the room to store this information.
