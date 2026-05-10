Nicotine+ Download Greeter

Automatic greeting on queued downloads
Configurable expiry window
Rolling expiry timer resets on new downloads
Compact JSON user history storage
Optional event logging
Per-user download tracking

Greeting Variables

Default:

Thanks for downloading, {user}.

More detailed example:

Hey {user}, thanks for checking out my files.
You will not receive another greeting for {expiry_days} days.
[{date}]

Example output sent to user:

Hey ExampleUser, thanks for checking out my files.
You will not receive another greeting for 180 days.
[2026-05-09]

Commands

/downgreet <user>
Show stored greeting information for a user.

/downgreet_forget <user>
Remove one user from the greeting database.

/downgreet_clear
Clear the entire greeting database.
