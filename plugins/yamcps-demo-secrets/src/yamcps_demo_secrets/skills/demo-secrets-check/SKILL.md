---
name: demo-secrets-check
description: Check that the demo-secrets connector has loaded token and Basic Auth credentials.
---

Call `demo_secrets_status` without arguments and report its local configuration
status. This tool does not contact an external API and does not validate account
access. Never ask the user to put secrets in the conversation or tool arguments.
Missing credentials must be configured in the user's terminal with
`yamcps secrets set --connector demo-secrets` before restarting the server.
