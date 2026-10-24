# ado — what the Azure DevOps bins (wf, wi, wp, wr, fleet, ops) share: the ADO client
# and its work items, JSON over HTTP that retries what a flaky network breaks, colours,
# time helpers, and loading another bin as a module.
#
# A bin finds this package by putting ~/.dotfiles on sys.path (see bin/wf).

from ado.net import HttpError, request
from ado.term import TTY, bold, c, cyan, dim, green, red, yellow
from ado.when import ago, ts
from ado.tracker import (ADO_RESOURCE, CHILD, DONE, HITL_TYPES, PARENT, PRED, RELATED, SUCC, Ado, Item,
                         sh)
from ado.load import load
