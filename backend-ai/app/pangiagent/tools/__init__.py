# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Domain tool functions for PangIA connector sub-agents.

Each module in this package exposes one or more LangChain ``@tool``-decorated
functions that wrap the low-level database / API clients.  These tools are
used as the ``tools`` field of deepagents ``SubAgent`` specs, giving each
sub-agent direct access to its data source.
"""
